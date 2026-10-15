import { createWriteStream, mkdirSync, statSync, readFileSync, openSync, closeSync, unlinkSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { randomBytes, createHash } from 'node:crypto';

// Authenticated chunk store; no claim of model analysis until an actual adapter exists.
export function createAttachmentStore(db, prepared, root) {
  mkdirSync(root, { recursive: true, mode: 0o700 });
  db.exec(`CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY, owner TEXT NOT NULL, filename TEXT NOT NULL,
    size INTEGER NOT NULL, received INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL, sha256 TEXT, created INTEGER NOT NULL
  );`);
  const max = 512 * 1024 * 1024;
  const validId = id => typeof id === 'string' && /^att-[a-f0-9]{32}$/.test(id);
  const file = id => join(root, id + '.bin');
  const begin = (owner, name, size) => {
    if (typeof name !== 'string' || !name.trim() || name.length > 240 || /[\x00-\x1f\x7f]/.test(name) || name.includes('/') || name.includes('\\'))
      throw Error('Invalid filename');
    if (!Number.isSafeInteger(size) || size < 1 || size > max) throw Error('File exceeds configured server quota');
    const id = 'att-' + randomBytes(16).toString('hex');
    prepared('INSERT INTO attachments(id,owner,filename,size,received,state,created) VALUES(?,?,?,?,0,?,?)')
      .run(id,owner,name,size,'receiving',Date.now());
    return { id, received: 0, max_size: max };
  };
  const info = (owner,id) => {
    if (!validId(id)) throw Error('Invalid attachment identifier');
    const row = prepared('SELECT * FROM attachments WHERE id=? AND owner=?').get(id,owner);
    if (!row) throw Error('Attachment not found');
    return row;
  };
  const chunk = async (owner,id,offset,req) => {
    const row = info(owner,id);
    if (row.state !== 'receiving' || offset !== row.received) throw Error('Attachment offset mismatch');
    const length = Number(req.headers['content-length']);
    if (!Number.isSafeInteger(length) || length < 1 || length > 2 * 1024 * 1024 || row.received + length > row.size)
      throw Error('Invalid chunk length');
    const bytes = [];
    let count = 0;
    for await (const part of req) {
      count += part.length;
      if (count > length) throw Error('Chunk length mismatch');
      bytes.push(part);
    }
    if (count !== length) throw Error('Chunk length mismatch');
    // Append only after validating the entire chunk; do not replay on uncertainty.
    const fd = openSync(file(id), row.received === 0 ? 'wx' : 'r+',
      0o600);
    try {
      const buffer = Buffer.concat(bytes);
      const { writeSync, fsyncSync } = await import('node:fs');
      let n = 0;
      while (n < buffer.length) n += writeSync(fd,buffer,n,buffer.length-n,row.received+n);
      fsyncSync(fd);
    } finally { closeSync(fd); }
    const received = row.received + count;
    prepared('UPDATE attachments SET received=? WHERE id=? AND owner=?').run(received,id,owner);
    return { id, received, size: row.size, complete: received === row.size };
  };
  const complete = (owner,id) => {
    const row = info(owner,id);
    if (row.received !== row.size || row.state !== 'receiving' || statSync(file(id)).size !== row.size)
      throw Error('Attachment not fully received');
    const hash = createHash('sha256');
    const fd = openSync(file(id),'r');
    try {
      const { readSync } = requireRead();
      const buf = Buffer.allocUnsafe(1024*1024);
      let pos = 0;
      while(pos < row.size) {
        const n = readSync(fd,buf,0,Math.min(buf.length,row.size-pos),pos);
        if (!n) throw Error('Unexpected end of attachment');
        hash.update(buf.subarray(0,n));pos+=n;
      }
    } finally { closeSync(fd); }
    const sha256 = hash.digest('hex');
    prepared('UPDATE attachments SET state=?,sha256=? WHERE id=? AND owner=?').run('stored',sha256,id,owner);
    return { id, filename: row.filename, size: row.size, sha256, state:'stored', analyzed: false };
  };
  const status = (owner,id) => {
    const row = info(owner,id);
    return { id, filename:row.filename, size:row.size, received:row.received,
      state:row.state, sha256:row.sha256, analyzed:false };
  };
  return { begin, chunk, complete, status };
}
function requireRead() { return {readSync: readBuffer}; }
import { readSync as readBuffer, writeSync } from 'node:fs';