"""Preluare și redistribuire automată în coada Kelion (22.10.2026). Instalat în /opt/kelion-brain, importat de coada-lucru.py.

Dovada (server, doar citire, 22.10 04:10): din 21.10 15:16 toate cele 57 de sarcini «kelion-remediere» s-au blocat în 2 minute cu
«dirty project; preserve preexisting changes»: în proiect rămăseseră fișiere necomise (diagnostic-chatgpt/…), lucrare.py refuză pe
bună dreptate un proiect murdar, iar activarea «new-only» nu reia nimic. Rezultat: nimic preluat, nimic analizat, nimic redistribuit.

1. preia_necomise: înainte de o lucrare nouă, fișierele necomise (în afară de .kelion/) se salvează într-un commit numit clar, ca să
   nu se piardă nimic; lucrarea primește nota cu ce s-a preluat. Fișierele cu nume de credențiale NU se ating și se raportează.
2. redistribuie: o sarcină blocată nu rămâne moartă: se creează o sarcină NOUĂ (prima ei execuție, compatibilă cu «new-only»), cu motivul
   blocării, istoricul și sarcina inițială, de cel mult MAX_GENERATII ori; apoi escaladare către Adrian, cu motivul exact.
"""
import os
import re
import subprocess
import time

MAX_GENERATII = int(os.environ.get("KELION_COADA_REDISTRIBUIRI", "3"))
SENSIBILE = ("auth.json", "credentials.json", "id_rsa", "id_ed25519")
FARA_REDISTRIBUIRE = ("CONECTARE NEFACUTA",)   # așteaptă o aprobare a lui Adrian: se escaladează direct, nu se rulează din nou


def _git(d, *a, intrare=None):
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/tmp"), "GIT_LITERAL_PATHSPECS": "1",
           "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C"}
    r = subprocess.run(["git", "-C", d, "-c", "core.hooksPath=/dev/null", *a], input=intrare, capture_output=True, timeout=120, env=env)
    if r.returncode:
        raise RuntimeError(f"git {a[0]}: {r.stderr.decode(errors='replace').strip()[:200]}")
    return r.stdout


def necomise(d):
    cai = set()
    for a in (("diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", "HEAD"),
              ("diff", "--cached", "--no-ext-diff", "--no-textconv", "--name-only", "-z"),
              ("ls-files", "--others", "--exclude-standard", "-z")):
        cai.update(os.fsdecode(p) for p in _git(d, *a).split(b"\0") if p)
    return sorted(p for p in cai if p != ".kelion" and not p.startswith(".kelion/"))


def sensibil(cale):
    n = os.path.basename(cale)
    return n in SENSIBILE or n == ".env" or n.startswith(".env.") or cale.split("/", 1)[0] == ".git"


def preia_necomise(d, sid):
    """(nota pentru lucrare, fișiere sensibile neatinse). Nota e goală dacă proiectul e curat sau nu e depozit git."""
    if not os.path.isdir(os.path.join(d, ".git")):
        return "", []
    toate = necomise(d)
    if not toate:
        return "", []
    sens = [p for p in toate if sensibil(p)]
    bune = [p for p in toate if p not in sens]
    pregatite = [os.fsdecode(p) for p in _git(d, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--name-only", "-z").split(b"\0") if p]
    if pregatite:
        # Indexul pregătit de altcineva nu se atinge: un «git add» ar suprascrie versiunea pregătită, iar un commit ar lua tot indexul
        # (inclusiv un .env deja pregătit). Lucrul în proiect rămâne blocat până decide Adrian.
        return (f"ATENTIE: proiectul are {len(pregatite)} fisiere deja pregatite pentru commit ({', '.join(pregatite[:8])}). "
                "Nu au fost atinse, ca sa nu se piarda versiunea pregatita si sa nu intre un secret intr-un commit. "
                "Raporteaza-i lui Adrian ce sunt; nu le citi continutul."), sorted(set(sens) | set(pregatite))
    nota = ""
    if bune:
        lista = b"\0".join(os.fsencode(p) for p in bune)
        _git(d, "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul", intrare=lista)
        # commit doar pe căile filtrate (nu tot indexul)
        _git(d, "-c", "user.name=Kelion", "-c", "user.email=kelion@localhost", "-c", "commit.gpgsign=false", "commit", "--no-verify", "-q",
             "-m", f"Kelion: preluate {len(bune)} fișiere necomise înainte de sarcina {sid} (nimic șters)",
             "--pathspec-from-file=-", "--pathspec-file-nul", intrare=lista)
        sha = _git(d, "rev-parse", "--short=10", "HEAD").decode().strip()
        nota = (f"NOTA PRELUARE: in proiect erau {len(bune)} fisiere necomise ({', '.join(bune[:8])}{' ...' if len(bune) > 8 else ''}), "
                f"lasate de o lucrare sau un diagnostic anterior. Au fost salvate in commitul {sha} inainte de aceasta lucrare. "
                "Analizeaza-le: daca tin de sarcina, foloseste-le; altfel lasa-le asa.")
    if sens:
        nota += (" ATENTIE: fisiere cu nume de credentiale NU au fost atinse si blocheaza lucrul in proiect: " + ", ".join(sens[:8])
                 + ". Raporteaza-i lui Adrian ce sunt; nu le citi continutul.")
    return nota.strip(), sens


def redistribuie(s, motiv, adauga, noutate, salveaza, ora=None):
    """Id-ul sarcinii noi sau None (deja redistribuită / escaladată către Adrian). Nu ridică excepții pentru date lipsă."""
    ora = ora or time.strftime("%Y-%m-%d %H:%M")
    if s.get("redistribuita_in") or s.get("escaladata"):
        return None
    gen = int(s.get("generatie") or 0)
    rad = s.get("radacina") or s["id"]
    initiala = s.get("sarcina_initiala") or s.get("sarcina") or ""
    motiv = str(motiv or s.get("motiv_blocare") or "necunoscut")
    if gen >= MAX_GENERATII or motiv.startswith(FARA_REDISTRIBUIRE):
        noutate(f"ESCALADARE: sarcina {rad} nu s-a putut rezolva automat ({gen + 1} incercari)",
                f"Proiect {s.get('proiect')}. Ultimul motiv al blocarii: {motiv[:700]}. Sarcina initiala: {initiala[:600]}. "
                "Spune-i lui Adrian exact ce blocheaza si ce decizie sau actiune ii cere; nu o prezenta ca rezolvata.",
                push=True, cheie=f"coada:escaladare:{rad}")
        # marcată abia după ce anunțul a plecat: dacă anunțul pică, sarcina rămâne eligibilă și escaladarea se reîncearcă
        s["escaladata"] = time.time()
        s.setdefault("istoric", []).append(f"{ora} ESCALADATA catre Adrian dupa {gen + 1} incercari: {motiv[:300]}")
        return None
    istoric = " | ".join(str(x) for x in (s.get("istoric") or [])[-4:])
    text = (f"REDISTRIBUIRE {gen + 1}/{MAX_GENERATII} a sarcinii {rad}: incercarea {s['id']} s-a blocat.\n"
            f"MOTIVUL BLOCARII: {motiv[:600]}\n"
            f"ISTORICUL INCERCARII: {istoric[:800]}\n"
            f"ROLUL ANTERIOR: {str(s.get('rol_efectiv') or '-')[:120]}\n"
            "Pasi obligatorii: 1) afla de ce s-a blocat incercarea anterioara (fisierele ei sunt in .kelion/lucrari/ al proiectului); "
            "2) inlatura cauza sau ocoleste-o; nu repeta abordarea care a dus la blocare; "
            "3) rezolva sarcina initiala de mai jos pana la capat, cu test.sh care o dovedeste. "
            "Daca sarcina cere o decizie sau o actiune a lui Adrian, spune exact care si de ce.\n\nSARCINA INITIALA:\n" + initiala)
    n = adauga(s["proiect"], text, "redistribuire automata (coada)")
    n = {k: v for k, v in n.items() if k != "_exista"}
    n.update(generatie=gen + 1, radacina=rad, sarcina_initiala=initiala, redistribuita_din=s["id"])
    salveaza(n)
    s["redistribuita_in"] = s["inlocuita_de"] = n["id"]
    s.setdefault("istoric", []).append(f"{ora} REDISTRIBUITA in sarcina {n['id']} (generatia {gen + 1}/{MAX_GENERATII})")
    return n["id"]


def cheie_defect(s):
    """Grupează sarcinile blocate care sunt același defect. La alertele verificatorului cifrele nu contează (sunt măsurători);
    la celelalte se scot doar datele, orele și id-urile de sarcină: «portul 8001» și «portul 8002» rămân sarcini diferite."""
    t = str(s.get("sarcina_initiala") or s.get("sarcina") or "")
    m = re.search(r"a gasit o problema: (.*?) \(", t)
    if m:
        return (s.get("proiect"), re.sub(r"\d+([.,:\-]\d+)*", "#", m.group(1).lower()).strip())
    baza = t[:200].lower()
    baza = re.sub(r"\b\d{8}-\d{6}-[0-9a-f]{4}\b", "#id", baza)
    baza = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{4}\b", "#data", baza)
    baza = re.sub(r"\b\d{1,2}:\d{2}(:\d{2})?\b", "#ora", baza)
    return (s.get("proiect"), baza.strip())
