"""S5 (22.10.2026): verificarea independentă a unei lucrări, IZOLATĂ. Instalat în /opt/kelion-brain, chemat de coada-lucru.valideaza().

Testele scrise de executant nu rulează în procesul părinte: rulează pe o COPIE a proiectului, în bubblewrap, fără rețea, fără
/opt, /var, /home, /etc/kelion*, cu limită de timp și cu ieșirea limitată (nu se ține în memorie mai mult de LIMITA_IESIRE).
Copia nu conține .git și nici fișiere cu secrete (.env, chei, credențiale): testul executantului nu le poate citi.

VERIFICAT doar cu dovada «roșu → verde» (22.10, recenzia Codex la #88): aceleași teste PICĂ pe codul de dinainte de lucrare
(base_commit din receipt) și TREC pe codul lucrării (commit). Un test care trece și fără schimbare nu dovedește reparația.
Verdictul e primul cuvânt: VERIFICAT / ESUAT / PARTIAL (...) / INDISPONIBIL. Ce ține de live se dovedește la livrare.
"""
import collections
import json
import os
import shutil
import subprocess
import tempfile
import time

LIMITA_S = int(os.environ.get("KELION_VERIF_LIMITA_S", "300"))
LIMITA_OCTETI = int(os.environ.get("KELION_VERIF_MAX_OCTETI", str(1536 * 1024 * 1024)))
LIMITA_IESIRE = 64 * 1024
ETC = ("/etc/alternatives", "/etc/ssl", "/etc/ca-certificates", "/etc/passwd", "/etc/group", "/etc/nsswitch.conf", "/etc/hosts",
       "/etc/ld.so.cache", "/etc/localtime", "/etc/mime.types", "/etc/python3", "/etc/python3.12", "/etc/bash.bashrc")
INDICIU = "test.sh ruleaza izolat (copie, fara retea, fara /opt /var /etc/kelion*); verificarile pe live merg in proba-live.sh"
DIRS_EXCLUSE = {".kelion", "__pycache__", ".git", ".ssh", ".gnupg", ".aws", ".config"}
NUME_SENSIBILE = {"auth.json", "credentials.json", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".netrc", ".git-credentials",
                  ".pypirc", ".npmrc"}
EXT_SENSIBILE = (".pem", ".key", ".p12", ".pfx", ".keystore")


def sensibil(cale):
    n = os.path.basename(cale)
    return n in NUME_SENSIBILE or n == ".env" or n.startswith(".env.") or n.lower().endswith(EXT_SENSIBILE)


def _ignora(director, nume):
    return {n for n in nume if n in DIRS_EXCLUSE or sensibil(os.path.join(director, n))}


def comanda_test(d):
    """Aceeași ordine ca verifica_lucrare din brain.py: test.sh, apoi npm test, apoi pytest."""
    if os.path.isfile(os.path.join(d, "test.sh")):
        return ["/usr/bin/bash", "test.sh"]
    pj = os.path.join(d, "package.json")
    if os.path.isfile(pj) and '"test"' in open(pj, encoding="utf-8", errors="replace").read():
        return ["/usr/bin/env", "npm", "test", "--silent"]
    if any(f.startswith("test_") and f.endswith(".py") for f in os.listdir(d)) or os.path.isdir(os.path.join(d, "tests")):
        return ["/usr/bin/python3", "-m", "pytest", "-q"]
    return None


def marime(d):
    total = 0
    for r, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in DIRS_EXCLUSE]
        for f in files:
            try:
                total += os.lstat(os.path.join(r, f)).st_size
            except OSError:
                pass
    return total


def argv_bwrap(copie, cmd):
    a = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
         "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
         "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
         "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--bind", copie, "/work", "--chdir", "/work",
         "--setenv", "HOME", "/tmp", "--setenv", "TMPDIR", "/tmp", "--setenv", "LANG", "C.UTF-8",
         "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin", "--setenv", "KELION_VERIFICARE_IZOLATA", "1"]
    for e in ETC:
        a += ["--ro-bind-try", e, e]
    return a + cmd


def ruleaza_limitat(argv, timeout=LIMITA_S, env=None, **_):
    """Ca subprocess.run, dar ține doar ultimii LIMITA_IESIRE octeți din ieșire (un test care scrie la nesfârșit nu umple memoria)."""
    coada, total = collections.deque(), 0
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    termen = time.monotonic() + timeout
    try:
        import selectors
        sel = selectors.DefaultSelector()
        sel.register(p.stdout, selectors.EVENT_READ)
        while True:
            ramas = termen - time.monotonic()
            if ramas <= 0:
                p.kill(); p.wait()
                raise subprocess.TimeoutExpired(argv, timeout, output=b"".join(coada))
            if not sel.select(timeout=min(ramas, 1.0)):
                if p.poll() is not None:
                    break
                continue
            bucata = os.read(p.stdout.fileno(), 65536)
            if not bucata:
                break
            coada.append(bucata); total += len(bucata)
            while total - len(coada[0]) >= LIMITA_IESIRE:
                total -= len(coada.popleft())
        p.wait(timeout=max(1, termen - time.monotonic()))
    finally:
        if p.poll() is None:
            p.kill(); p.wait()
        p.stdout.close()
    return subprocess.CompletedProcess(argv, p.returncode, b"".join(coada)[-LIMITA_IESIRE:].decode("utf-8", "replace"), "")


def _git_env():
    return {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "LC_ALL": "C"}


def _git(d, *a):
    r = subprocess.run(["git", "-C", d, "-c", "core.hooksPath=/dev/null", *a], capture_output=True, timeout=120, env=_git_env())
    if r.returncode:
        raise RuntimeError(f"git {a[0]}: {r.stderr.decode(errors='replace').strip()[:160]}")
    return r.stdout


def _receipt(d, lid):
    for nume in (lid + ".receipt.json", lid + ".json"):
        try:
            with open(os.path.join(d, ".kelion", "lucrari", nume), encoding="utf-8") as h:
                r = json.load(h)
            if r.get("base_commit") and r.get("commit"):
                return r["base_commit"], r["commit"]
        except (OSError, ValueError, AttributeError):
            pass
    return None, None


def _e_test(cale):
    """Teste și tot ce le susține (conftest, fixture-uri, date de test): se pun peste codul vechi la proba «roșu»."""
    parti = cale.split("/")
    n = parti[-1]
    return (n in ("test.sh", "conftest.py", "pytest.ini") or n.startswith("test_")
            or n.endswith(("_test.py", ".test.js", ".spec.js", ".test.ts", ".spec.ts"))
            or any(p in ("test", "tests", "__tests__", "fixtures", "testdata") for p in parti[:-1]))


def _extrage(d, rev, tinta):
    """git archive <rev> | tar -x, în flux (fără să țină arhiva în memorie); apoi fără .git, secrete și legături."""
    os.makedirs(tinta)
    g = subprocess.Popen(["git", "-C", d, "-c", "core.hooksPath=/dev/null", "archive", "--format=tar", rev],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_git_env())
    t = subprocess.run(["tar", "-x", "-C", tinta], stdin=g.stdout, capture_output=True, timeout=300)
    g.stdout.close()
    err = g.stderr.read().decode(errors="replace")[:160]; g.stderr.close()
    if g.wait(timeout=60) or t.returncode:
        raise RuntimeError(f"git archive {rev[:10]}: {err or t.stderr.decode(errors='replace')[:160]}")
    for r, dirs, files in os.walk(tinta, topdown=True):
        for x in [x for x in dirs if x in DIRS_EXCLUSE]:
            shutil.rmtree(os.path.join(r, x), ignore_errors=True)
        dirs[:] = [x for x in dirs if x not in DIRS_EXCLUSE]
        for f in files:
            if sensibil(f) or os.path.islink(os.path.join(r, f)):
                os.unlink(os.path.join(r, f))
    # dependențele instalate (node_modules) nu sunt în git și sandboxul n-are rețea: se iau din proiect, ca testele să poată rula
    nm = os.path.join(d, "node_modules")
    if os.path.isdir(nm) and not os.path.islink(nm):
        shutil.copytree(nm, os.path.join(tinta, "node_modules"), symlinks=True)


def _pune_testele(cap, baza, schimbate):
    for rel in schimbate:
        if not _e_test(rel) or sensibil(rel) or ".." in rel.split("/"):
            continue
        src, dst = os.path.join(cap, rel), os.path.join(baza, rel)
        if os.path.isfile(src) and not os.path.islink(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        elif os.path.lexists(dst):
            os.unlink(dst)


# un «roșu» care vine din pregătire (import, colectare, fișier lipsă), nu din aserțiune, nu dovedește reparația
PREGATIRE = ("ModuleNotFoundError", "ImportError", "SyntaxError", "IndentationError", "No such file or directory",
             "command not found", "ERROR collecting", "errors during collection", "fixture '", "Cannot find module",
             "MODULE_NOT_FOUND", "not found in rootdir", "Permission denied")


def _rosu_din_pregatire(cmd, cod, iesire):
    if cmd[-2:] == ["pytest", "-q"] and cod in (2, 3, 4, 5):
        return True
    return any(m in iesire for m in PREGATIRE)


def _ruleaza(rulare, copie, cmd, limita):
    if limita <= 0:
        return 124, "timpul verificarii s-a terminat inainte de aceasta rulare"
    try:
        p = rulare(argv_bwrap(copie, cmd), capture_output=True, text=True, timeout=limita, env={"PATH": "/usr/bin:/bin"})
        return p.returncode, " ".join(((p.stdout or "") + (p.stderr or "")).split())[-700:]
    except subprocess.TimeoutExpired as e:
        out = e.output.decode("utf-8", "replace") if isinstance(e.output, bytes) else (e.output or "")
        return 124, f"depasit {limita} s; " + " ".join(out.split())[-400:]


def verifica(d, lid="", limita=LIMITA_S, rulare=ruleaza_limitat):
    """Un rând: verdictul, apoi dovada. Nu ridică excepții pentru proiecte fără teste sau prea mari.
    Cu receipt: «verde» se rulează pe commitul din receipt (nu pe directorul de lucru, care se poate schimba), «roșu» pe
    base_commit + testele din același commit. O singură limită de timp pentru ambele rulări."""
    t0 = time.monotonic()
    termen = t0 + limita
    if not os.path.isdir(d):
        return f"INDISPONIBIL: proiectul {d} nu exista"
    cmd = comanda_test(d)
    if not cmd:
        return f"PARTIAL (fara teste): nu exista test.sh / npm test / pytest in proiect; {INDICIU}"
    m = marime(d)
    if m > LIMITA_OCTETI:
        return f"PARTIAL (proiect prea mare pentru copia izolata: {m // 1048576} MB > {LIMITA_OCTETI // 1048576} MB)"
    baza, commit = _receipt(d, lid)
    tmp = tempfile.mkdtemp(prefix="kelion-verif-")
    try:
        cap = os.path.join(tmp, "cap")
        try:
            if commit:
                _extrage(d, commit, cap)
            else:
                shutil.copytree(d, cap, symlinks=True, ignore=_ignora)
            cmd = comanda_test(cap) or cmd
            cod, iesire = _ruleaza(rulare, cap, cmd, termen - time.monotonic())
        except OSError as e:
            return f"INDISPONIBIL: bwrap nu a putut porni ({type(e).__name__}: {str(e)[:120]})"
        except (RuntimeError, subprocess.SubprocessError) as e:
            return f"INDISPONIBIL: commitul {str(commit)[:10]} nu s-a putut extrage ({str(e)[:120]})"
        dur = round(time.monotonic() - t0, 1)
        if cod != 0:
            return f"ESUAT (izolat, lucrarea {lid}): teste cod {cod} in {dur} s; {INDICIU}; iesire: {iesire}"
        if not baza:
            return (f"PARTIAL (fara dovada rosu->verde: receiptul lucrarii {lid} nu are base_commit/commit): testele trec "
                    f"in {dur} s, dar nu se poate arata ca picau inainte; iesire: {iesire}")
        try:
            schimbate = [os.fsdecode(x) for x in _git(d, "diff", "--name-only", "-z", baza, commit).split(b"\0") if x]
            _extrage(d, baza, os.path.join(tmp, "baza"))
            _pune_testele(cap, os.path.join(tmp, "baza"), schimbate)
            cmd_baza = comanda_test(os.path.join(tmp, "baza")) or cmd
            cod_b, iesire_b = _ruleaza(rulare, os.path.join(tmp, "baza"), cmd_baza, termen - time.monotonic())
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            return f"PARTIAL (fara dovada rosu->verde: codul de dinainte ({baza[:10]}) nu s-a putut pregati: {type(e).__name__}: {str(e)[:120]})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    dur = round(time.monotonic() - t0, 1)
    if cod_b == 0:
        return (f"PARTIAL (testele trec si pe codul de dinainte {baza[:10]}: nu dovedesc reparatia; adauga un test care pica fara ea) "
                f"lucrarea {lid}; iesire: {iesire}")
    if cod_b == 124:
        return f"PARTIAL (pe codul de dinainte {baza[:10]} testele au depasit timpul: dovada rosu->verde neconcludenta) lucrarea {lid}"
    if _rosu_din_pregatire(cmd_baza, cod_b, iesire_b):
        return (f"PARTIAL (pe codul de dinainte {baza[:10]} testele pica la pregatire, nu la verificare: dovada rosu->verde "
                f"neconcludenta) lucrarea {lid}; iesire: {iesire_b[-300:]}")
    if os.path.isdir(os.path.join(d, "node_modules")):
        # (recenzia Codex la #93) dependențele instalate nu sunt legate de niciun commit: executantul le-ar putea fi schimbat
        # după receipt, deci un «verde» cu ele nu e dovadă despre commit
        return (f"PARTIAL (rosu->verde obtinut cu node_modules din proiect, nelegat de commit: dependentele pot fi modificate de "
                f"executant) lucrarea {lid}; pica pe {baza[:10]} (cod {cod_b}), trec pe {commit[:10]}; iesire: {iesire}")
    return (f"VERIFICAT (izolat, rosu->verde, lucrarea {lid}): teste '{' '.join(cmd[-2:])}' pica pe {baza[:10]} (cod {cod_b}) si trec pe "
            f"{commit[:10]} (cod 0), in {dur} s pe copii fara retea si fara secrete; iesire: {iesire} "
            "| NEVERIFICAT aici: comportamentul pe live (proba-live.sh la livrare) si paginile (tester)")
