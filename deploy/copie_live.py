"""Copia codului live pentru executanți (22.10.2026; Kelion: «citirea registrului și a surselor și copierea în spațiul de lucru,
fără secrete ori date personale, fără modificări pe server»; Adrian: «alocă-i ce trebuie»).

Executanții (OpenAI Codex în lucrare.py) lucrează închiși în proiect, fără /opt/kelion-brain și fără rețea: de aceea nicio
reparație a live-ului nu se putea diagnostica. Bariera rămâne neatinsă; în schimb, înainte de fiecare lucrare coada pune în
<proiect>/.kelion/live/ o COPIE PROASPĂTĂ, doar de citit, a codului live:
  opt-kelion-brain/   codul din /opt/kelion-brain (fără work/, cariera/, modele/, venv/, tunnel/, backup*, jurnale, baze, .env)
  var-www-kelion/     site-ul (/var/www/kelion)
  senzori/            rezultatele verificatorului și testerului (verificare-site.json, tester-ui.json)
Doar fișiere text de cod (extensii permise, sub 2 MB); un fișier care seamănă a secret (cheie, token, parolă) nu se copiază și e
numit în INDEX.md. .kelion/ nu intră niciodată în commituri (lucrare.py îl exclude).
"""
import fnmatch
import os
import re
import shutil
import time

SURSE = (("/opt/kelion-brain", "opt-kelion-brain"), ("/var/www/kelion", "var-www-kelion"))
SENZORI = ("/var/lib/kelion-senzori/verificare-site.json", "/var/lib/kelion-senzori/tester-ui.json")
DIRS_EXCLUSE = {"work", "cariera", "modele", "venv", ".venv", "node_modules", "__pycache__", "tunnel", ".git", ".kelion", "capturi",
                "descarcari", "media", "uploads"}
EXTENSII = {".py", ".js", ".mjs", ".cjs", ".ts", ".html", ".css", ".json", ".md", ".sh", ".txt", ".toml", ".yaml", ".yml",
            ".service", ".timer", ".path", ".conf", ".sql", ".svg"}
NUME_EXCLUSE = ("*.env", "*.env.*", ".env*", "*secret*", "*token*", "*.key", "*.pem", "noutati*", "*.sqlite*", "*.jsonl",
                "auth*.json", "credentials*", "*parol*", "*password*", "aprobari*")
MAX_OCTETI = 2 * 1024 * 1024
SECRET = re.compile(rb"(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[bap]-[A-Za-z0-9-]{10,}|"
                    rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})")


def _dir_exclus(nume):
    return nume in DIRS_EXCLUSE or nume.startswith("backup")


def _fisier_permis(nume):
    if any(fnmatch.fnmatch(nume.lower(), m) for m in NUME_EXCLUSE):
        return False
    return os.path.splitext(nume)[1].lower() in EXTENSII


def copiaza(sursa, tinta, sarite):
    n = 0
    for r, dirs, files in os.walk(sursa):
        dirs[:] = sorted(d for d in dirs if not _dir_exclus(d) and not os.path.islink(os.path.join(r, d)))
        for f in sorted(files):
            src = os.path.join(r, f)
            rel = os.path.relpath(src, sursa)
            if os.path.islink(src) or not _fisier_permis(f):
                continue
            try:
                if os.path.getsize(src) > MAX_OCTETI:
                    continue
                with open(src, "rb") as h:
                    date = h.read()
            except OSError:
                continue
            if SECRET.search(date):
                sarite.append(os.path.join(os.path.basename(tinta), rel))
                continue
            dst = os.path.join(tinta, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as h:
                h.write(date)
            os.chmod(dst, 0o444)
            n += 1
    return n


def sincronizeaza(proiect, surse=SURSE, senzori=SENZORI):
    """Copia proaspătă în <proiect>/.kelion/live/. Întoarce nota pentru executant."""
    kelion = os.path.join(proiect, ".kelion")
    live = os.path.join(kelion, "live")
    # (22.10, recenzia Codex la #89) o legătură simbolică pusă de executant în loc de .kelion sau .kelion/live ar face ca
    # chmod/rmtree să lucreze ÎN AFARA proiectului: legătura se scoate, nu se urmează
    for c in (kelion, live):
        if os.path.islink(c):
            os.unlink(c)
    os.makedirs(kelion, exist_ok=True)
    if os.path.lexists(live):
        for r, dirs, files in os.walk(live, followlinks=False):
            if not os.path.islink(r):
                os.chmod(r, 0o755)
        shutil.rmtree(live)
    os.makedirs(live)
    sarite, total = [], 0
    for sursa, nume in surse:
        if os.path.isdir(sursa):
            total += copiaza(sursa, os.path.join(live, nume), sarite)
    os.makedirs(os.path.join(live, "senzori"), exist_ok=True)
    for f in senzori:   # (22.10) și senzorii trec prin filtrul de secrete (un mesaj de eroare poate conține o cheie)
        try:
            with open(f, "rb") as h:
                date = h.read(MAX_OCTETI + 1)
        except OSError:
            continue
        if len(date) > MAX_OCTETI or SECRET.search(date):
            sarite.append(os.path.join("senzori", os.path.basename(f)))
            continue
        dst = os.path.join(live, "senzori", os.path.basename(f))
        with open(dst, "wb") as h:
            h.write(date)
        os.chmod(dst, 0o444)
        total += 1
    ora = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(live, "INDEX.md"), "w", encoding="utf-8") as h:
        h.write(f"# Copia live ({ora})\n\nDoar de citit. {total} fișiere. Baza pentru diagnostic și pentru livrare.json "
                "(kelion-pregateste-livrare compară cu live-ul de la livrare).\n\n"
                + ("Fișiere neincluse fiindcă seamănă a secrete:\n" + "\n".join(f"- {x}" for x in sarite) + "\n" if sarite else ""))
    return (f"COPIA LIVE ({ora}): in .kelion/live/ ai codul live DOAR DE CITIT ({total} fisiere): opt-kelion-brain/ = /opt/kelion-brain, "
            "var-www-kelion/ = /var/www/kelion, senzori/ = verificare-site.json si tester-ui.json. Fara secrete si fara date personale. "
            "Diagnosticheaza pe ea; reparatia o faci in proiect si o livrezi prin kelion-pregateste-livrare (baza = fisierul live). "
            "Nu scrie in .kelion/live/ si nu o copia in commit.")
