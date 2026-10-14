import { createPublicKey, verify, createHash, randomBytes } from 'node:crypto';

export const hash = value => createHash('sha256').update(value).digest('hex');
export const random = () => randomBytes(32).toString('base64url');
export class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
export function googleKeys() {
  let cached, until = 0, pending, refreshed = 0;
  return async kid => {
    const now = Date.now();
    if (!cached || now > until || (!cached.some(k => k.kid === kid) && now - refreshed > 60000)) {
      pending ??= (async () => {
        const response = await fetch('https://www.googleapis.com/oauth2/v3/certs', {
          redirect: 'error', signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new HttpError(503, 'Google keys unavailable');
        const raw = await response.text();
        if (raw.length > 65536) throw new HttpError(503, 'Invalid Google keys');
        const keys = JSON.parse(raw).keys;
        if (!Array.isArray(keys) || keys.length > 20) throw new HttpError(503, 'Invalid Google keys');
        cached = keys; refreshed = Date.now();
        until = refreshed + Math.min(3600, Number(response.headers.get('cache-control')?.match(/max-age=(\d+)/)?.[1] ?? 300)) * 1000;
      })().finally(() => { pending = null; });
      await pending;
    }
    return cached.find(k => k.kid === kid && k.kty === 'RSA' && k.alg === 'RS256' && k.use === 'sig');
  };
}

export async function verifyGoogle(token, { clientId, nonce, keys, now = Math.floor(Date.now() / 1000) }) {
  const invalid = () => new HttpError(401, 'Invalid Google credential');
  if (typeof token !== 'string' || token.length > 16000) throw invalid();
  const parts = token.split('.');
  // Node's decoder tolerates nonzero unused padding bits; JWT segments must be canonical.
  if (parts.length !== 3 || parts.some(p => !/^[A-Za-z0-9_-]+$/.test(p) || Buffer.from(p, 'base64url').toString('base64url') !== p)) throw invalid();
  let header, claim;
  try { header = JSON.parse(Buffer.from(parts[0], 'base64url')); claim = JSON.parse(Buffer.from(parts[1], 'base64url')); } catch { throw invalid(); }
  if (!header || header.alg !== 'RS256' || typeof header.kid !== 'string' || header.kid.length > 200 || header.crit) throw invalid();
  const key = await keys(header.kid);
  if (!key || key.kty !== 'RSA' || key.alg !== 'RS256' || key.use !== 'sig' || key.kid !== header.kid) throw invalid();
  try {
    if (!verify('RSA-SHA256', Buffer.from(parts.slice(0, 2).join('.')), createPublicKey({ key, format: 'jwk' }), Buffer.from(parts[2], 'base64url'))) throw invalid();
  } catch { throw invalid(); }
  if (!claim || !['https://accounts.google.com', 'accounts.google.com'].includes(claim.iss)
    || claim.aud !== clientId || (claim.azp !== undefined && claim.azp !== clientId)
    || !Number.isInteger(claim.exp) || claim.exp <= now
    || !Number.isInteger(claim.iat) || claim.iat > now + 30 || claim.exp - claim.iat > 7200
    || (claim.nbf !== undefined && (!Number.isInteger(claim.nbf) || claim.nbf > now))
    || claim.nonce !== nonce || claim.email_verified !== true
    || typeof claim.sub !== 'string' || !/^[A-Za-z0-9_-]{1,255}$/.test(claim.sub)
    || typeof claim.email !== 'string' || claim.email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(claim.email)) throw invalid();
  return { sub: claim.sub, email: claim.email.toLowerCase() };
}
