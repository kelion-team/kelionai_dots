"""Stage a pinned official Linux release in a NEW directory. Never activates it.

No npm lifecycle scripts, global package changes, credentials, model requests,
service restart, or privilege changes. Archives remain alongside provenance.
On failure the partial destination is retained, never retried or overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent


def download(url, destination, expected):
    if not url.startswith('https://github.com/openai/codex/releases/download/'):
        raise ValueError('Official pinned release required')
    h = hashlib.sha256(); total = 0
    with urllib.request.urlopen(url, timeout=60) as source, destination.open('xb') as target:
        if not source.url.startswith(('https://github.com/', 'https://release-assets.githubusercontent.com/')):
            raise ValueError('Unexpected release redirect')
        while block := source.read(1024 * 1024):
            total += len(block)
            if total > 200 * 1024 * 1024:
                raise ValueError('Release size limit')
            h.update(block); target.write(block)
        target.flush(); os.fsync(target.fileno())
    if h.hexdigest() != expected:
        raise ValueError('Official release archive digest mismatch')


def extract_binary(archive, destination, name):
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        for member in members:
            p = PurePosixPath(member.name)
            if p.is_absolute() or '..' in p.parts or member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe release archive member')
        candidates = [m for m in members if m.isfile() and (PurePosixPath(m.name).name == name or PurePosixPath(m.name).name.startswith(name + '-'))]
        if len(candidates) != 1 or not 0 < candidates[0].size < 400 * 1024 * 1024:
            raise ValueError('Unique release executable required')
        with source.extractfile(candidates[0]) as f, destination.open('xb') as out:
            while block := f.read(1024 * 1024): out.write(block)
            out.flush(); os.fsync(out.fileno())
        destination.chmod(0o700)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != 'linux': raise ValueError('Linux installer only')
    if not args.destination.is_absolute(): raise ValueError('Absolute destination required')
    destination = args.destination
    if destination.exists() or destination.is_symlink(): raise ValueError('New destination required')
    pins = json.loads((HERE / 'linux-release-pins.json').read_text())
    arch = platform.machine()
    if arch not in pins['assets']: raise ValueError('Unsupported Linux architecture')
    destination.mkdir(mode=0o700)
    binary = destination / 'bin'; binary.mkdir(mode=0o700)
    for name, asset in pins['assets'][arch].items():
        url = f"https://github.com/openai/codex/releases/download/rust-v{pins['version']}/{asset['name']}"
        archive = destination / asset['name']
        download(url, archive, asset['sha256'])
        extract_binary(archive, binary / name, name)
    private_home = destination / 'verification-home'; private_home.mkdir(mode=0o700)
    env = {k:v for k,v in os.environ.items() if k in ('LANG','LC_ALL','TMPDIR')}
    env.update(PATH=str(binary) + ':/usr/bin:/bin', HOME=str(private_home), CODEX_HOME=str(private_home))
    codex = binary / 'codex'
    version = subprocess.run([str(codex),'--version'],env=env,capture_output=True,text=True,check=True,timeout=20).stdout.strip()
    if version != 'codex-cli ' + pins['version']: raise ValueError('Installed CLI version mismatch')
    schemas = destination / 'protocol'
    subprocess.run([str(codex),'app-server','generate-json-schema','--out',str(schemas)],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
    expected = json.loads((HERE/'protocol-pins.json').read_text())
    actual = {name:hashlib.sha256((schemas/name).read_bytes()).hexdigest() for name in expected}
    if actual != expected: raise ValueError('Generated Linux protocol differs from reviewed pinned protocol; staged only')
    manifest = {'version':version,'architecture':arch,'official_release':pins['release'],'assets':pins['assets'][arch], 'codex_executable':str(codex),'codex_sha256':hashlib.sha256(codex.read_bytes()).hexdigest(),'protocol_directory':str(schemas),'protocol_sha256':actual,'worker_activated':False,'oauth_performed':False,'model_turns':0,'credential_isolation_tested':False}
    (destination/'installation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))


if __name__ == '__main__': main()
