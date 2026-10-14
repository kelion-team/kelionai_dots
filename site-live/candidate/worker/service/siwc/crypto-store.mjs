import { createCipheriv, createDecipheriv, randomBytes, randomUUID, generateKeyPairSync, createPublicKey, createPrivateKey, diffieHellman, hkdfSync, createHash } from 'node:crypto';
import { promises as fs, constants } from 'node:fs';
import path from 'node:path';
import { requireValue, uuidOK, SiwcError } from './oauth.mjs';

const b64 = x => Buffer.from(x).toString('base64url');
const unb64 = x => { requireValue(typeof x === 'string' && /^[A-Za-z0-9_-]+$/.test(x), 'invalid_envelope'); return Buffer.from(x, 'base64url'); };
export const fingerprint = publicPem => createHash('sha256').update(createPublicKey(publicPem).export({ type: 'spki', format: 'der' })).digest('hex');
export function generateRecipient(hostId = randomUUID()) {
  requireValue(uuidOK(hostId), 'invalid_host_id');
  const { publicKey, privateKey } = generateKeyPairSync('x25519');
  const publicPem = publicKey.export({ type: 'spki', format: 'pem' });
  return { public: { schema: 1, host_id: hostId, public_key: publicPem, fingerprint: fingerprint(publicPem) }, privateKey: privateKey.export({ type: 'pkcs8', format: 'pem' }) };
}
function seal(plaintext, key, aad) {
  requireValue(key.length === 32, 'invalid_encryption_key');
  const iv = randomBytes(12), c = createCipheriv('aes-256-gcm', key, iv);
  c.setAAD(Buffer.from(aad));
  return { iv: b64(iv), ciphertext: b64(Buffer.concat([c.update(plaintext), c.final()])), tag: b64(c.getAuthTag()) };
}
function unseal(envelope, key, aad) {
  try { const iv = unb64(envelope.iv), tag = unb64(envelope.tag); requireValue(iv.length === 12 && tag.length === 16, 'invalid_envelope'); const c = createDecipheriv('aes-256-gcm', key, iv); c.setAAD(Buffer.from(aad)); c.setAuthTag(tag); return Buffer.concat([c.update(unb64(envelope.ciphertext)), c.final()]); }
  catch { throw new SiwcError('decryption_failed'); }
}
export function encryptTransfer(credentials, recipient, verifiedFingerprint, now = Date.now()) {
  requireValue(recipient.schema === 1 && uuidOK(recipient.host_id) && fingerprint(recipient.public_key) === verifiedFingerprint && recipient.fingerprint === verifiedFingerprint, 'recipient_not_authenticated');
  const remote = createPublicKey(recipient.public_key);
  requireValue(remote.asymmetricKeyType === 'x25519', 'invalid_recipient_key');
  const ephemeral = generateKeyPairSync('x25519'), salt = randomBytes(32);
  const metadata = { schema: 1, type: 'KelionAI-SIWC-transfer', id: randomUUID(), host_id: recipient.host_id, recipient: verifiedFingerprint, ephemeral: ephemeral.publicKey.export({ type: 'spki', format: 'pem' }), salt: b64(salt), created_at: now, expires_at: now + 600000 };
  const key = Buffer.from(hkdfSync('sha256', diffieHellman({ privateKey: ephemeral.privateKey, publicKey: remote }), salt, Buffer.from('KelionAI/SIWC/transfer/v1'), 32));
  const plain = Buffer.from(JSON.stringify(credentials));
  try { return { metadata, ...seal(plain, key, JSON.stringify(metadata)) }; } finally { key.fill(0); plain.fill(0); }
}
export function decryptTransfer(envelope, privatePem, expectedHostId, now = Date.now()) {
  const m = envelope.metadata;
  requireValue(m?.schema === 1 && m.type === 'KelionAI-SIWC-transfer' && uuidOK(m.id) && m.host_id === expectedHostId && Number.isInteger(m.created_at) && Number.isInteger(m.expires_at) && m.created_at <= now + 5000 && m.expires_at > now && m.expires_at - m.created_at <= 600000, 'invalid_transfer_metadata');
  const privateKey = createPrivateKey(privatePem), publicKey = createPublicKey(m.ephemeral);
  requireValue(privateKey.asymmetricKeyType === 'x25519' && publicKey.asymmetricKeyType === 'x25519' && fingerprint(createPublicKey(privateKey).export({ type: 'spki', format: 'pem' })) === m.recipient, 'wrong_recipient');
  const key = Buffer.from(hkdfSync('sha256', diffieHellman({ privateKey, publicKey }), unb64(m.salt), Buffer.from('KelionAI/SIWC/transfer/v1'), 32));
  let plain;
  try { plain = unseal(envelope, key, JSON.stringify(m)); const record = JSON.parse(plain); record.ext_agent_host_id = expectedHostId; return record; }
  catch { throw new SiwcError('decryption_failed'); } finally { key.fill(0); plain?.fill(0); }
}

export function checkPosixStat(st, { directory = false, uid = process.getuid?.() } = {}) {
  requireValue(st.uid === uid && !(st.mode & 0o077) && (directory ? st.isDirectory() : st.isFile()) && !st.isSymbolicLink() && (directory || st.nlink === 1), 'private_permissions_required');
}
export async function assertPrivateDirectory(root) {
  requireValue(process.platform !== 'win32', 'windows_private_storage_requires_verified_dpapi_and_acl');
  requireValue(path.isAbsolute(root) && await fs.realpath(root) === path.resolve(root), 'private_path_required');
  checkPosixStat(await fs.lstat(root), { directory: true });
  // Parent directories may be public to traverse but must not permit replacement.
  let parent = path.dirname(root);
  for (;;) { const st = await fs.lstat(parent); requireValue(st.isDirectory() && !st.isSymbolicLink() && (!(st.mode & 0o022) || (st.uid === 0 && (st.mode & 0o1000))), 'unsafe_private_parent'); if (parent === path.dirname(parent)) break; parent = path.dirname(parent); }
}
export async function readPrivate(file) {
  await assertPrivateDirectory(path.dirname(file));
  const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW);
  try { const st = await handle.stat(); checkPosixStat(st); requireValue(st.size <= 1048576, 'private_file_too_large'); return await handle.readFile(); } finally { await handle.close(); }
}
export async function writePrivate(file, data) {
  const root = path.dirname(file); await assertPrivateDirectory(root);
  const temp = path.join(root, `.pending-${randomUUID()}`);
  let h;
  try { h = await fs.open(temp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600); await h.writeFile(data); await h.sync(); await h.close(); h = null; await fs.rename(temp, file); const dir = await fs.open(root, constants.O_RDONLY); try { await dir.sync(); } finally { await dir.close(); } }
  finally { if (h) await h.close(); await fs.unlink(temp).catch(() => {}); }
}

// A process crash leaves the lock in place: explicit reconciliation must clear it.
export class Vault {
  constructor(root, key) { this.root = path.resolve(root); this.key = Buffer.from(key); requireValue(this.key.length === 32, 'invalid_encryption_key'); }
  async lock(fn) {
    await assertPrivateDirectory(this.root);
    const lock = path.join(this.root, 'session.lock'); let h;
    try { h = await fs.open(lock, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600); } catch { throw new SiwcError('session_locked_requires_reconciliation'); }
    try { await h.writeFile(JSON.stringify({ pid: process.pid, started_at: new Date().toISOString() })); await h.sync(); return await fn(); } finally { await h.close(); await fs.unlink(lock); }
  }
  async read() {
    const envelope = JSON.parse(await readPrivate(path.join(this.root, 'session.enc')));
    const plain = unseal(envelope, this.key, 'KelionAI/SIWC/vault/v1');
    try { return JSON.parse(plain); } finally { plain.fill(0); }
  }
  async write(state) {
    const plain = Buffer.from(JSON.stringify(state));
    try { await writePrivate(path.join(this.root, 'session.enc'), JSON.stringify(seal(plain, this.key, 'KelionAI/SIWC/vault/v1'))); } finally { plain.fill(0); }
  }
  close() { this.key.fill(0); }
}
