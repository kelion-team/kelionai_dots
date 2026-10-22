#!/usr/bin/env python3
"""Export în două faze. Numai biblioteca standard. Nu este detector universal de secrete."""
import argparse, fnmatch, getpass, hashlib, json, os, re, shlex, shutil, stat, subprocess, sys, tempfile, uuid
from pathlib import Path
from urllib.request import Request, urlopen
ROOTS = ('opt/kelion-pod', 'opt/kelion-brain', 'opt/kelion-control')
CONFIGS = {'opt/kelion-pod/locuri.json','opt/kelion-control/platform-navigation.json', *(f'opt/kelion-control/assets/{x}.i18n.json' for x in ('portal','jobs','companion','navigation'))}
EXTS = {'.py','.sh','.js','.mjs','.css','.html'}
# Directoare de lucru/revizie (copii, candidați, teste), nu cod live: în afara copiei.
EXCLUDE_PATHS = ('opt/kelion-brain/work',)
EXCLUDE = ('*venv','__pycache__','backup*','*.backup-*','node_modules','modele','models','audit_jobs','chrome*','loc[0-9]*','capturi','.env*','*.env','.git')
TARGET = 'kelion-team/kelion-brain'
URL = f'https://github.com/{TARGET}.git'
MAX = 2*1024*1024
PATTERNS = [r'-----BEGIN [A-Z ]*PRIVATE KEY-----',r'\b(?:ghp_|github_pat_|gho_)[A-Za-z0-9_]{30,}',r'\bsk-[A-Za-z0-9_-]{20,}',r'\bEAA[A-Za-z0-9]{40,}',r'\bAIza[0-9A-Za-z_-]{35}',r'\bya29\.[0-9A-Za-z_-]{20,}',r'\bAKIA[0-9A-Z]{16}\b',r'\bxox[baprs]-[0-9A-Za-z-]{10,}',r'''(?i)["']?(?:password|parola|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)["']?\s*[:=]\s*["'][^"'\s$<{]{12,}["']''',r'[?&](?:token|key|secret|access_token)=[A-Za-z0-9._-]{20,}']
class Stop(RuntimeError): pass
def digest(b): return hashlib.sha256(b).hexdigest()
def canonical(obj): return (json.dumps(obj,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode()
def check_parents(p):
    p=Path(p).absolute()
    for q in (p,*p.parents):
        if q.is_symlink(): raise Stop(f'Legătură simbolică: {q}')
def regular_read(p):
    p=Path(p); check_parents(p)
    before=p.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1: raise Stop(f'Nu este fișier regulat unic: {p}')
    if not before.st_mode & 0o444: raise PermissionError(str(p))
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        a=os.fstat(fd)
        if (a.st_dev,a.st_ino)!=(before.st_dev,before.st_ino): raise Stop('Fișier înlocuit în timpul citirii')
        with os.fdopen(fd,'rb',closefd=False) as f: data=f.read(MAX+1)
        b=os.fstat(fd)
        if (a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(b.st_size,b.st_mtime_ns,b.st_ctime_ns): raise Stop('Fișier modificat în timpul citirii')
        if len(data)>MAX: raise Stop(f'Fișier peste 2 MiB: {p}')
        after=p.lstat()
        if (after.st_dev,after.st_ino,after.st_ctime_ns)!=(b.st_dev,b.st_ino,b.st_ctime_ns): raise Stop('Fișier înlocuit după citire')
        return data
    finally: os.close(fd)
def tree_files(root, exclusions=(), skip=()):
    root=Path(root); check_parents(root)
    if not stat.S_ISDIR(root.lstat().st_mode): raise Stop('Rădăcină invalidă')
    def visit(d):
        with os.scandir(d) as entries: items=sorted(entries,key=lambda e:e.name)
        for e in items:
            if any(fnmatch.fnmatch(e.name, pattern) for pattern in exclusions) or e.path in skip: continue
            s=e.stat(follow_symlinks=False)
            if stat.S_ISDIR(s.st_mode):
                check_parents(e.path); yield from visit(Path(e.path))
            elif stat.S_ISREG(s.st_mode) and s.st_nlink==1: yield Path(e.path)
            else: raise Stop(f'Legătură sau fișier special: {e.path}')
    yield from visit(root)
def manifest(root):
    result=[]
    for p in tree_files(root):
        b=regular_read(p)
        result.append({'path':p.relative_to(root).as_posix(),'size':len(b),'sha256':digest(b)})
    return sorted(result,key=lambda x:x['path'])
def verify(work, expected):
    work=Path(work); raw=regular_read(work/'inventar.json')
    if not re.fullmatch('[0-9a-f]{64}',expected) or digest(raw)!=expected: raise Stop('Digestul inventarului nu este cel aprobat')
    actual=canonical(manifest(work/'server'))
    if raw!=actual: raise Stop('Calea, mărimea sau conținutul diferă de inventarul aprobat')
    return json.loads(raw)
def redact(text):
    groups=[]; buf=[]
    for line in text.splitlines():
        if line.lstrip().startswith(('#',';')): continue
        buf.append(line)
        if line.endswith('\\'): continue
        groups.append(buf); buf=[]
    if buf: raise Stop('Continuare systemd neterminată')
    out=[]; values=[]
    for group in groups:
        logical=' '.join(x[:-1] if x.endswith('\\') else x for x in group)
        m=re.match(r'^\s*(Environment|UnsetEnvironment|PassEnvironment|SetCredential|SetCredentialEncrypted)\s*=\s*(.*)$',logical)
        if not m: out.extend(group); continue
        key,value=m.groups()
        # Refuz conservator: escape-uri systemd necesită un parser complet, nu presupunem semantica shell.
        if '\\' in value: raise Stop('Escape systemd neacceptat pentru redactare sigură')
        try: tokens=shlex.split(value,comments=False,posix=True)
        except ValueError as e: raise Stop('Citat systemd invalid') from e
        names=[]
        if key.startswith('SetCredential'):
            if not value.strip(): out.append(key+'='); continue
            if len(tokens)!=1 or ':' not in tokens[0]: raise Stop('Credential systemd ambiguă')
            name,secret=tokens[0].split(':',1)
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',name): raise Stop('Nume credential invalid')
            names=[name+':<redactat>']; values.append(secret)
        else:
            for token in tokens:
                name,sep,secret=token.partition('=')
                if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name): raise Stop('Nume variabilă systemd invalid')
                if sep: values.append(secret)
                names.append(name+('=<redactat>' if sep else ''))
        out.append(key+'='+' '.join(names))
    result='\n'.join(out)+'\n'
    if any(v and v!='<redactat>' and v in result for v in values): raise Stop('Valoare systemd încă prezentă după redactare')
    return result

def prepare(base, output):
    base=Path(base).absolute(); output=Path(output).absolute(); check_parents(base); check_parents(output)
    output.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='copie-contabo-',dir=output))
    try: return _prepare(base,work)
    except BaseException:
        # O pregătire oprită nu lasă în urmă o copie parțială care ar putea fi luată drept validă.
        shutil.rmtree(work,ignore_errors=True); raise

def _prepare(base, work):
    (work/'server').mkdir(mode=0o700)
    excluded=[]
    def copy(p,rel,systemd=False):
        try:
            raw=regular_read(p); text=raw.decode('utf-8','strict')
        except (OSError,UnicodeDecodeError) as e:
            if systemd: raise Stop(f'Unitate necitibilă: {rel}') from e
            excluded.append({'path':rel,'reason':type(e).__name__}); return
        if systemd: text=redact(text)
        if any(re.search(pattern,text) for pattern in PATTERNS):
            excluded.append({'path':rel,'reason':'posibil secret'}); return
        dest=work/'server'/rel; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(text.encode('utf-8')); dest.chmod(0o600)
    for root in ROOTS:
        source=base/root
        if not source.exists(): raise Stop(f'Lipsește rădăcina aprobată: {root}')
        # Excluderile sunt eliminate înainte de stat/descent; staging rămâne strict.
        for p in tree_files(source, EXCLUDE, {str(base/x) for x in EXCLUDE_PATHS}):
            rel=p.relative_to(base).as_posix(); parts=p.relative_to(source).parts
            if any(fnmatch.fnmatch(part,pat) for part in parts for pat in EXCLUDE): continue
            if p.suffix in EXTS or rel in CONFIGS: copy(p,rel)
    units=base/'etc/systemd/system'
    if not units.exists(): raise Stop('Lipsește directorul systemd')
    check_parents(units)
    # scandir, nu glob care poate ascunde erori de acces.
    with os.scandir(units) as it: entries=list(it)
    for e in entries:
        name=e.name; p=Path(e.path)
        if not name.startswith('kelion-'): continue
        if any(name.endswith(x) for x in ('.service','.timer','.path')): copy(p,p.relative_to(base).as_posix(),True)
        elif any(name.endswith(x) for x in ('.service.d','.timer.d','.path.d')):
            for q in tree_files(p):
                if q.suffix=='.conf': copy(q,q.relative_to(base).as_posix(),True)
    raw=canonical(manifest(work/'server'))
    if json.loads(raw)==[]: raise Stop('Copie goală')
    (work/'inventar.json').write_bytes(raw); (work/'excluse.json').write_bytes(canonical(excluded))
    print(f'PREGĂTIT LOCAL: {work}\nSHA256 INVENTAR: {digest(raw)}\nNu s-a folosit rețeaua. Verifică inventarul ȘI conținutul fiecărui fișier înainte de publish.')
    return work,digest(raw)

def private_repo(token):
    req=Request(f'https://api.github.com/repos/{TARGET}',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'kelion-local-export'})
    # Nu urmărim redirecționări cu Authorization către altă destinație.
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): raise Stop('API redirect refuzat')
    with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as response: info=json.load(response)
    if info.get('private') is not True or info.get('full_name')!=TARGET or not info.get('permissions',{}).get('push'): raise Stop('Depozitul țintă nu este privat sau nu ai drept de push')
    return info['default_branch']

def copy_verified(source,dest,approved):
    if dest.exists(): raise Stop('Destinația există deja')
    dest.mkdir(mode=0o700)
    for item in approved:
        rel=Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts: raise Stop('Cale invalidă')
        data=regular_read(source/rel)
        if len(data)!=item['size'] or digest(data)!=item['sha256']: raise Stop('Fișier schimbat înainte de copiere')
        p=dest/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data); p.chmod(0o600)
    if manifest(source)!=approved or manifest(dest)!=approved: raise Stop('Copie sau sursă modificată')

def publish(work,expected):
    work=Path(work).absolute(); approved=verify(work,expected)
    print(f'Depozit: {TARGET}; inventar SHA256: {expected}; {len(approved)} fișiere.\nRegexurile nu garantează lipsa secretelor sau datelor personale.')
    if input('Ai verificat conținutul tuturor fișierelor și aprobi acest inventar? Scrie DA: ')!='DA': raise Stop('Anulat; nimic urcat')
    verify(work,expected) # încă înainte de token/rețea
    if not shutil.which('git'): raise Stop('Lipsește git; nu instalez nimic')
    if not sys.stdin.isatty(): raise Stop('Tokenul cere terminal interactiv; nu accept pipe')
    token=getpass.getpass('Token GitHub (ascuns): ')
    if not token or '\n' in token or '\r' in token: raise Stop('Token invalid')
    default=private_repo(token)
    with tempfile.TemporaryDirectory(prefix='kelion-publish-') as tmp:
        tmp=Path(tmp); repo=tmp/'repo'; home=tmp/'home'; home.mkdir()
        env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':str(home),'LANG':'C.UTF-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','KELION_EXPORT_TOKEN':token}
        auth=['-c','credential.helper=','-c','credential.helper=!f() { printf "%s\\n" "username=x-access-token" "password=$KELION_EXPORT_TOKEN"; }; f','-c','core.hooksPath=/dev/null','-c','protocol.file.allow=never']
        def git(*args):
            p=subprocess.run(['git',*auth,*args],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if p.returncode: raise Stop('Comanda git a eșuat; ieșirea este ascunsă pentru protejarea tokenului')
            return p.stdout
        git('clone','--quiet','--depth','1','--',URL,str(repo))
        if token.encode() in (repo/'.git/config').read_bytes(): raise Stop('Token detectat în configurația git')
        branch='copie/contabo-'+uuid.uuid4().hex
        git('-C',str(repo),'checkout','-b',branch)
        verify(work,expected)
        dest=repo/'server'
        if os.path.lexists(dest):
            # Sincronizare repetată: copia anterioară e înlocuită integral; ștergerile intră în commit prin git add.
            if dest.is_symlink() or not dest.is_dir(): raise Stop('server/ din depozit nu este director obișnuit')
            shutil.rmtree(dest)
        copy_verified(work/'server',dest,approved)
        # Întregul conținut adăugat este cel revizuit. Nu adăugăm alte rapoarte sau fișiere.
        if manifest(repo/'server')!=approved: raise Stop('Staging schimbat înainte de git add')
        git('-C',str(repo),'add','--','server')
        entries=git('-C',str(repo),'ls-files','--stage','-z','--','server').split(b'\0')
        indexed=[]
        for entry in filter(None,entries):
            meta,name=entry.split(b'\t',1); mode,oid,stage=meta.split()
            if mode!=b'100644' or stage!=b'0': raise Stop('Tip git nepermis')
            path=name.decode('utf-8'); content=git('-C',str(repo),'cat-file','blob',oid.decode())
            indexed.append({'path':path.removeprefix('server/'),'size':len(content),'sha256':digest(content)})
        if sorted(indexed,key=lambda x:x['path'])!=approved: raise Stop('Indexul git diferă de inventarul aprobat')
        verify(work,expected)
        git('-C',str(repo),'-c','user.name=Kelion export','-c','user.email=kelion-export@localhost','commit','-m','Copie locală revizuită '+expected)
        private_repo(token)
        git('-C',str(repo),'push','origin',f'HEAD:refs/heads/{branch}')
        commit=git('-C',str(repo),'rev-parse','HEAD').decode().strip()
        print(f'URCAT: {branch}\nCOMMIT: {commit}\nLink pentru CREAREA unui PR (PR nu este creat automat): https://github.com/{TARGET}/compare/{default}...{branch}?expand=1')
    token=''

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare'); a.add_argument('--output',default='/root'); a.add_argument('--source-root',default='/',help='Doar pentru teste pe fixtures locale; producție: /')
    b=sub.add_parser('publish'); b.add_argument('work'); b.add_argument('--approved-manifest-sha256',required=True)
    args=p.parse_args()
    try:
        if args.action=='prepare': prepare(args.source_root,args.output)
        else: publish(args.work,args.approved_manifest_sha256)
    except Exception as e:
        # Nu tipărim excepții de transport care ar putea conține credențiale.
        print('OPRIT: '+(str(e) if isinstance(e,Stop) else type(e).__name__)+'. Nu presupune că publicarea a reușit.',file=sys.stderr); return 1
    return 0
if __name__=='__main__': sys.exit(main())
