"""Pinned file deployment. No service changes, credentials or inference.
Atomic replacement is per file, not across the entire manifest.
Use an exclusive CLI lock; unrelated editors must still honor ownership.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe(root, relative):
    p = Path(relative)
    if p.is_absolute() or not p.parts or '..' in p.parts or p.name.endswith('.env'):
        raise ValueError('Unsafe deployment path')
    target = root
    for part in p.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError('Symlinks must not be overwritten')
    return target


def current(path):
    if path.is_symlink():
        raise ValueError('Target changed to symlink')
    return digest(path.read_bytes()) if path.exists() else None


def atomic(path, data, mode=0o644, uid=None, gid=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.kelion-stage-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            if uid is not None and (os.geteuid() == 0):
                os.fchown(stream.fileno(), uid, gid)
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def journal(backup, data):
    atomic(backup / 'transaction.json', (json.dumps(data, indent=2)+'\n').encode(), 0o600)


def apply(root, source, manifest, backup):
    root, source, backup = Path(root).resolve(), Path(source).resolve(), Path(backup).resolve()
    if backup.exists():
        raise FileExistsError('Backup already exists; reconcile prior transaction')
    if not isinstance(manifest, list) or not manifest:
        raise ValueError('Nonempty manifest required')
    seen, staged = set(), []
    for item in manifest:
        name = item['path']
        if name in seen:
            raise ValueError('Duplicate target')
        seen.add(name)
        target, src = safe(root, name), safe(source, name)
        data = src.read_bytes()
        if digest(data) != item['source_sha256']:
            raise ValueError('Source hash mismatch: '+name)
        if current(target) != item['expected_current_sha256']:
            raise ValueError('LIVE drift: '+name)
        stat = target.stat() if target.exists() else None
        entry = dict(item, mode=(stat.st_mode & 0o777) if stat else 0o644,
                     uid=stat.st_uid if stat else os.geteuid(), gid=stat.st_gid if stat else os.getegid())
        staged.append((entry, data, target.read_bytes() if stat else None))
    backup.mkdir(parents=True, mode=0o700)
    for entry, data, old in staged:
        if old is not None:
            atomic(safe(backup/'original', entry['path']), old, 0o600)
    record = {'root': str(root), 'state': 'prepared', 'files': [e for e, _, _ in staged]}
    journal(backup, record)
    try:
        record['state'] = 'applying'; journal(backup, record)
        for entry, data, old in staged:
            target = safe(root, entry['path'])
            if current(target) != entry['expected_current_sha256']:
                raise ValueError('LIVE drift during apply: '+entry['path'])
            atomic(target, data, entry['mode'], entry['uid'], entry['gid'])
            if current(target) != entry['source_sha256']:
                raise ValueError('Readback mismatch')
        record['state'] = 'verified'; journal(backup, record)
    except Exception:
        record['state'] = 'failed_reconcile_before_retry'; journal(backup, record)
        raise
    return record


def rollback(root, backup):
    root, backup = Path(root).resolve(), Path(backup).resolve()
    record = json.loads((backup/'transaction.json').read_text())
    if record['root'] != str(root):
        raise ValueError('Rollback root mismatch')
    staged = []
    for entry in record['files']:
        target = safe(root, entry['path']); actual = current(target)
        if actual not in (entry['source_sha256'], entry['expected_current_sha256']):
            raise ValueError('LIVE drift after deployment: '+entry['path'])
        old = None
        if entry['expected_current_sha256'] is not None:
            old = safe(backup/'original', entry['path']).read_bytes()
            if digest(old) != entry['expected_current_sha256']:
                raise ValueError('Backup hash mismatch')
        staged.append((entry, actual, old))
    for entry, actual, old in staged:
        target = safe(root, entry['path'])
        if current(target) != actual:
            raise ValueError('Concurrent change during rollback')
        if old is None:
            if target.exists(): target.unlink()
        else:
            atomic(target, old, entry['mode'], entry['uid'], entry['gid'])
        if current(target) != entry['expected_current_sha256']:
            raise ValueError('Rollback readback mismatch')
    record['state'] = 'rolled_back'; journal(backup, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['apply','rollback'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--source')
    parser.add_argument('--manifest')
    parser.add_argument('--lock', default='/var/lock/kelion-mask-files.lock')
    args = parser.parse_args()
    with open(args.lock, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'apply':
            if not args.source or not args.manifest:
                parser.error('apply requires --source and --manifest')
            result = apply(args.root, args.source, json.loads(Path(args.manifest).read_text()), args.backup)
        else:
            result = rollback(args.root, args.backup)
        print(json.dumps({'state': result['state'], 'files': len(result['files'])}))


if __name__ == '__main__':
    main()
