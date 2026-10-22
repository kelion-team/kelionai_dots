"""S5 (22.10.2026): verificarea independentă a unei lucrări, IZOLATĂ. Instalat în /opt/kelion-brain, chemat de coada-lucru.valideaza().

Activarea «new-only» din 21.10 oprea orice lucrare după receipt («verificarea independenta in sandbox lipseste»), fiindcă testele
scrise de executant nu trebuie rulate în procesul părinte. Aici rulează pe o COPIE a proiectului, în bubblewrap: fără rețea, fără
/opt, /var, /home, /etc/kelion*, ca utilizatorul serviciului, cu limită de timp. Verdictul e primul cuvânt (formatul lui _verdict):
VERIFICAT / ESUAT / PARTIAL (fara teste) / INDISPONIBIL. Ce ține de live se dovedește la livrare (proba-live.sh, cu rollback).
"""
import os
import shutil
import subprocess
import tempfile
import time

LIMITA_S = int(os.environ.get("KELION_VERIF_LIMITA_S", "300"))
LIMITA_OCTETI = int(os.environ.get("KELION_VERIF_MAX_OCTETI", str(1536 * 1024 * 1024)))
ETC = ("/etc/alternatives", "/etc/ssl", "/etc/ca-certificates", "/etc/passwd", "/etc/group", "/etc/nsswitch.conf", "/etc/hosts",
       "/etc/ld.so.cache", "/etc/localtime", "/etc/mime.types", "/etc/python3", "/etc/python3.12", "/etc/bash.bashrc")
INDICIU = "test.sh ruleaza izolat (copie, fara retea, fara /opt /var /etc/kelion*); verificarile pe live merg in proba-live.sh"


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
        dirs[:] = [x for x in dirs if x != ".kelion"]
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


def verifica(d, lid="", limita=LIMITA_S, rulare=subprocess.run):
    """Un rând: verdictul, apoi dovada. Nu ridică excepții pentru proiecte fără teste sau prea mari."""
    t0 = time.time()
    if not os.path.isdir(d):
        return f"INDISPONIBIL: proiectul {d} nu exista"
    cmd = comanda_test(d)
    if not cmd:
        return f"PARTIAL (fara teste): nu exista test.sh / npm test / pytest in proiect; {INDICIU}"
    m = marime(d)
    if m > LIMITA_OCTETI:
        return f"PARTIAL (proiect prea mare pentru copia izolata: {m // 1048576} MB > {LIMITA_OCTETI // 1048576} MB)"
    tmp = tempfile.mkdtemp(prefix="kelion-verif-")
    try:
        copie = os.path.join(tmp, "p")
        shutil.copytree(d, copie, symlinks=True, ignore=shutil.ignore_patterns(".kelion", "__pycache__"))
        try:
            p = rulare(argv_bwrap(copie, cmd), capture_output=True, text=True, timeout=limita, env={"PATH": "/usr/bin:/bin"})
            cod, out = p.returncode, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired as e:
            cod, out = 124, f"depasit {limita} s; " + str((e.stdout or b"")[-400:] if isinstance(e.stdout, bytes) else (e.stdout or ""))[-400:]
        except OSError as e:
            return f"INDISPONIBIL: bwrap nu a putut porni ({type(e).__name__}: {str(e)[:120]})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    dur = round(time.time() - t0, 1)
    iesire = " ".join(out.split())[-700:]
    if cod == 0:
        return (f"VERIFICAT (izolat, lucrarea {lid}): teste '{' '.join(cmd[-2:])}' cod 0 in {dur} s pe o copie fara retea; iesire: {iesire} "
                "| NEVERIFICAT aici: comportamentul pe live (proba-live.sh la livrare) si paginile (tester)")
    return f"ESUAT (izolat, lucrarea {lid}): teste cod {cod} in {dur} s; {INDICIU}; iesire: {iesire}"
