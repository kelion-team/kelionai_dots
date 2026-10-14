import { promises as fs } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { randomUUID, randomBytes, createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { createAttempt, authorizationURL, exchangeCode, requireValue, SiwcError, loadJWKS, validateIdToken, uuidOK, issuedClientOK, ISSUER } from './oauth.mjs';
import { generateRecipient, encryptTransfer, decryptTransfer, assertPrivateDirectory, writePrivate, readPrivate, Vault } from './crypto-store.mjs';
import { validateReady } from './provider.mjs';

async function readJSON(file) { const st = await fs.lstat(file); requireValue(st.isFile() && !st.isSymbolicLink() && st.size < 262144, 'invalid_input_file'); return JSON.parse(await fs.readFile(file, 'utf8')); }
async function savePublic(file, value) { await fs.writeFile(file, JSON.stringify(value, null, 2) + '\n', { flag: 'wx', mode: 0o600 }); }

export async function prepareRecipient(root, publicFile) {
  requireValue(process.platform !== 'win32', 'windows_private_storage_requires_verified_dpapi_and_acl');
  // Never repair existing ACLs or ownership. Operator supplies a private directory.
  await assertPrivateDirectory(root);
  let publicRecord;
  try { publicRecord = JSON.parse(await readPrivate(path.join(root, 'recipient.json'))); }
  catch (e) {
    if (e.code !== 'ENOENT') throw e;
    const generated = generateRecipient(); publicRecord = generated.public;
    // Exclusive creation avoids replacing a key whose public half was distributed.
    const keyPath = path.join(root, 'recipient.key');
    await fs.writeFile(keyPath, generated.privateKey, { mode: 0o600, flag: 'wx' });
    await fs.writeFile(path.join(root, 'vault.key'), randomBytes(32), { mode: 0o600, flag: 'wx' });
    await writePrivate(path.join(root, 'recipient.json'), JSON.stringify(publicRecord));
  }
  await savePublic(publicFile, publicRecord);
  return { status: 'recipient_public_exported', fingerprint: publicRecord.fingerprint, host_id: publicRecord.host_id };
}

export function registrationMetadata(record, localHostId) {
  requireValue(issuedClientOK(record.client_id) && record.issuer === ISSUER && typeof record.subject === 'string' && record.subject.length > 0 && uuidOK(localHostId), 'invalid_registration_metadata');
  // Secret-free account selector. Never include ID/access/refresh tokens or email.
  return { schema: 1, issuer: ISSUER, subject: record.subject, client_id: record.client_id, local_host_id: localHostId };
}
export async function selectRegistration(registrationFile, localHostId) {
  let saved;
  try { saved = await readJSON(registrationFile); } catch (e) { if (e.code === 'ENOENT') return null; throw e; }
  requireValue(saved.schema === 1 && saved.local_host_id === localHostId && Object.keys(saved).every(k => ['schema', 'issuer', 'subject', 'client_id', 'local_host_id'].includes(k)), 'registration_selector_mismatch');
  return registrationMetadata(saved, localHostId);
}

export async function localLogin({ recipientFile, verifiedFingerprint, hostFile, envelopeFile, registrationFile = `${hostFile}.registration.json`, announce = console.log }) {
  const recipient = await readJSON(recipientFile);
  requireValue(recipient.fingerprint === verifiedFingerprint && /^[a-f0-9]{64}$/.test(verifiedFingerprint), 'verified_recipient_fingerprint_required');
  // This file holds only a random host identifier. No DPAPI assumption or secret file.
  let hostId;
  try { hostId = (await readJSON(hostFile)).host_id; }
  catch (e) { if (e.code !== 'ENOENT') throw e; hostId = randomUUID(); await savePublic(hostFile, { host_id: hostId }); }
  requireValue(uuidOK(hostId) && hostId !== recipient.host_id, 'distinct_local_host_id_required');
  const selected = await selectRegistration(registrationFile, hostId);
  // Verify the full recipient before starting any OAuth activity.
  encryptTransfer({ recipient_check: true }, recipient, verifiedFingerprint);
  let attempt, settle, reject, processing = false;
  const completed = new Promise((resolve, fail) => { settle = resolve; reject = fail; });
  const server = createServer(async (req, res) => {
    res.setHeader('Cache-Control', 'no-store'); res.setHeader('Referrer-Policy', 'no-referrer'); res.setHeader('X-Content-Type-Options', 'nosniff'); res.setHeader('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'");
    try {
      requireValue(req.method === 'GET' && req.headers.host === `127.0.0.1:${server.address().port}` && ['127.0.0.1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress), 'invalid_callback_request');
      const u = new URL(req.url, attempt.redirectUri);
      if (u.pathname === '/' && !u.search) { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end('<!doctype html><title>KelionAI</title><h1>KelionAI</h1><a href="/start">Continue with ChatGPT</a>'); return; }
      if (u.pathname === '/start' && !u.search && !attempt.consumed) { res.writeHead(302, { Location: authorizationURL(attempt) }); res.end(); return; }
      requireValue(u.pathname === '/auth/callback' && !processing, 'invalid_callback_path');
      // Validate state before claiming the callback; unauthenticated requests cannot
      // settle the promise or trigger a token exchange.
      requireValue(u.searchParams.get('state') === attempt.state, 'state_mismatch');
      processing = true;
      const record = await exchangeCode(attempt, u.href);
      // Persist the selected client/account mapping separately from the active
      // grant, after signature and subject validation. A new account uses another
      // explicitly selected metadata path; do not silently replace a registration.
      if (!selected) await savePublic(registrationFile, registrationMetadata(record, hostId));
      const envelope = encryptTransfer(record, recipient, verifiedFingerprint);
      await savePublic(envelopeFile, envelope);
      record.access_token = ''; record.refresh_token = ''; record.id_token = '';
      res.end('KelionAI: credentials encrypted for the verified VM. You may close this tab.');
      settle({ status: 'encrypted_transfer_ready', entitlement_verified: false });
    } catch (e) { res.statusCode = 400; res.end('KelionAI: authorization was not completed.'); if (processing) reject(new SiwcError(e instanceof SiwcError ? e.code : 'login_failed')); }
  });
  server.requestTimeout = 15000; server.headersTimeout = 10000;
  await new Promise((resolve, fail) => { server.once('error', fail); server.listen(0, '127.0.0.1', resolve); });
  attempt = createAttempt({ hostId, port: server.address().port, selected });
  const timer = setTimeout(() => reject(new SiwcError('login_timeout')), 600000);
  announce(`Continue with ChatGPT: http://127.0.0.1:${server.address().port}/`);
  try { return await completed; } finally { clearTimeout(timer); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}

export async function importTransfer({ root, envelopeFile, authenticatedEnvelopeHash }) {
  const raw = await fs.readFile(envelopeFile);
  requireValue(raw.length <= 262144 && /^[a-f0-9]{64}$/.test(authenticatedEnvelopeHash) && createHash('sha256').update(raw).digest('hex') === authenticatedEnvelopeHash, 'authenticated_transfer_hash_required');
  const recipient = JSON.parse(await readPrivate(path.join(root, 'recipient.json')));
  const key = await readPrivate(path.join(root, 'vault.key'));
  const vault = new Vault(root, key); key.fill(0);
  try { return await vault.lock(async () => {
    const envelope = JSON.parse(raw);
    let state;
    try { state = await vault.read(); } catch (e) { if (e.code !== 'ENOENT') throw e; state = { schema: 1, phase: 'stopped', imported_ids: [] }; }
    requireValue(state.phase === 'stopped' && Array.isArray(state.imported_ids) && !state.imported_ids.includes(envelope.metadata?.id), 'import_requires_reconciliation_or_replayed');
    const privateKey = await readPrivate(path.join(root, 'recipient.key'));
    let record; try { record = decryptTransfer(envelope, privateKey, recipient.host_id); } finally { privateKey.fill(0); }
    validateReady(record);
    validateIdToken(record.id_token, { jwks: await loadJWKS(), clientId: record.client_id, nonce: record.oidc_nonce, expectedSubject: record.subject });
    requireValue(!state.record || (state.record.client_id === record.client_id && state.record.subject === record.subject), 'separate_registration_vault_required');
    state.record = record; state.imported_ids.push(envelope.metadata.id);
    await vault.write(state);
    return { status: 'imported', entitlement_verified: false };
  }); } finally { vault.close(); }
}

async function main(argv) {
  const [command, ...args] = argv;
  if (command === 'prepare-recipient' && args.length === 2) return prepareRecipient(path.resolve(args[0]), path.resolve(args[1]));
  if (command === 'login-export' && [4, 5].includes(args.length)) return localLogin({ recipientFile: args[0], verifiedFingerprint: args[1], hostFile: args[2], envelopeFile: args[3], ...(args[4] ? { registrationFile: args[4] } : {}) });
  if (command === 'import' && args.length === 3) return importTransfer({ root: path.resolve(args[0]), envelopeFile: args[1], authenticatedEnvelopeHash: args[2] });
  throw new SiwcError('usage_prepare-recipient_ROOT_PUBLIC_or_login-export_RECIPIENT_FINGERPRINT_HOST_ENVELOPE_optional-REGISTRATION_or_import_ROOT_ENVELOPE_HASH');
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main(process.argv.slice(2)).then(result => console.log(JSON.stringify(result))).catch(e => { console.error(JSON.stringify({ status: 'stopped', code: e instanceof SiwcError ? e.code : 'operation_failed' })); process.exitCode = 1; });
}
