"""Explicit Linux-only dependency/source preparation; never starts worker/models.

Run in an empty destination. No sudo, user management, service enable or restart.
The original six recovered files are copied byte-for-byte; upstream packages
must pass their exact original version and module hashes before installation
is reported ready. Preserve the original source licenses and package metadata.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recovered-source',type=Path,required=True)
    p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--install-dependencies',action='store_true')
    args=p.parse_args()
    if sys.platform!='linux':raise ValueError('Original framework requires Linux fcntl')
    pins=json.loads((HERE/'magentic-source-pins.json').read_text())
    for name,h in pins.items():
        if hashlib.sha256((args.recovered_source/name).read_bytes()).hexdigest()!=h:raise ValueError('Recovered source hash mismatch')
    registry=HERE.parent/'core/orchestration/native_roles.json'
    if hashlib.sha256(registry.read_bytes()).hexdigest()!='c9c5ec7f3f3f4f816b0e0620f2dc115740ee068a97e1806cc9c8c355b3e53109':raise ValueError('Original registry hash mismatch')
    destination=args.destination.resolve()
    destination.mkdir(mode=0o700,parents=False,exist_ok=False)
    source=destination/'source';module=source/'orchestration/magentic_candidate';module.mkdir(parents=True,mode=0o700)
    for name in pins:shutil.copyfile(args.recovered_source/name,module/name)
    shutil.copyfile(registry,source/'orchestration/native_roles.json')
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','TMPDIR')}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    if args.install_dependencies:
        subprocess.run([sys.executable,'-m','venv',str(destination/'venv')],check=True,env=env)
        python=destination/'venv/bin/python'
        subprocess.run([str(python),'-m','pip','install','--index-url','https://pypi.org/simple','--disable-pip-version-check','--no-input','agent-framework-core==1.21.0','agent-framework-orchestrations==1.3.1'],check=True,env=env)
        subprocess.run([str(python),'-c','from orchestration.magentic_candidate.runtime import verify_versions; verify_versions()'],cwd=source,env=env,check=True)
    print(json.dumps({'sources_copied_and_verified':True,'upstream_modules_verified':args.install_dependencies,'worker_started':False,'oauth_performed':False,'model_turns':0,'source_root':str(source),'python':str(destination/'venv/bin/python') if args.install_dependencies else None}))

if __name__=='__main__':main()
