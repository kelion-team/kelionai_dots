"""Leagă grupurile WhatsApp (whatsapp_grupuri.py) de /opt/kelion-brain/whatsapp.py — reparație exactă, cu probă.

  python3 repara_grupuri.py SURSA DESTINATIE   (SURSA = directorul cu whatsapp.py; scrie whatsapp.py reparat în DESTINATIE)
Fiecare text trebuie găsit exact cum e așteptat; altfel nu se scrie nimic.
"""
import ast
import os
import py_compile
import sys

MARCAJ = "import whatsapp_grupuri as GR"

EXACTE = [
    ("import modul grupuri",
     "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n",
     "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n\nimport whatsapp_grupuri as GR   # grupuri WhatsApp (Adrian, 21.10.2026)\n"),
    ("group_id din webhook",
     """                x["nume_profil"] = re.sub(r"[\\[\\]\\n\\r]", " ", profil.get(x["de_la"], ""))[:40].strip()\n""",
     """                x["nume_profil"] = re.sub(r"[\\[\\]\\n\\r]", " ", profil.get(x["de_la"], ""))[:40].strip()\n"""
     """                x["grup"] = str(m.get("group_id") or "")   # mesaj dintr-un grup WhatsApp (Groups API)\n"""),
    ("filtru grup + ruta izolata",
     """        adrian = m["de_la"] in cfg["permisi"]
        if adrian:
            noteaza_adrian(phone_id=m["phone_id"])   # deschide fereastra de 24 h (pe numarul pe care a scris) pentru confirmari
        m["oaspete"] = not adrian and (m["de_la"] in cfg["oaspeti"] or m["phone_id"] in cfg["publice"])
""",
     """        grup = m.get("grup")
        adrian = m["de_la"] in cfg["permisi"] and not grup   # in grup nici Adrian nu deschide datele lui private
        if adrian:
            noteaza_adrian(phone_id=m["phone_id"])   # deschide fereastra de 24 h (pe numarul pe care a scris) pentru confirmari
        m["oaspete"] = not adrian and (m["de_la"] in cfg["oaspeti"] or m["phone_id"] in cfg["publice"] or bool(grup))
        if grup:   # GRUP (Adrian 21.10.2026): Kelion raspunde DOAR cand e chemat pe nume cu o cerere; mereu pe ruta izolata
            cerere = GR.cerere_pentru_kelion(m["text"]) if m["tip"] == "text" else None
            if cerere is None:
                jurnal(ev="grup_ignorat", id=m["id"], grup=GR.scurt(grup))
                continue
            m["text"] = cerere
"""),
    ("trimitere in grup sau persoanei",
     """        corp = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": catre, "type": "text",
                "text": {"preview_url": False, "body": parti[i]}}
""",
     """        corp = GR.corp_mesaj(catre, parti[i])   # «grup:<id>» -> recipient_type group; altfel persoana
"""),
    ("comenzi de grup pentru Adrian",
     """    if not vocal and comanda_restaurare(cfg, m):
        return
""",
     """    if not vocal and comanda_restaurare(cfg, m):
        return
    if not vocal and GR.executa_admin(cfg, m, GR.Meta(cfg["token"], GRAPH, GRAPH_VER), STARE, trimite_text, jurnal):
        return   # «grup nou <nume>» / «grupuri»
"""),
]

# în trateaza_oaspete: răspunsul pleacă în grup, iar memoria izolată e a grupului
IN_TRATEAZA_OASPETE = [
    ('trimite_text(cfg, m["de_la"],', 'trimite_text(cfg, GR.destinatar(m),'),
    ('oaspete_openai(m["de_la"], ', 'oaspete_openai(GR.cheie_istoric(m), '),
    ('tine_minte_oaspete(m["de_la"], ', 'tine_minte_oaspete(GR.cheie_istoric(m), '),
]


def aplica(text):
    for nume, vechi, nou in EXACTE:
        n = text.count(vechi)
        if n != 1:
            raise SystemExit(f"OPRIT: «{nume}» găsit de {n} ori (trebuie exact 1). Nu s-a scris nimic.")
        text = text.replace(vechi, nou)
    start = text.find("\ndef trateaza_oaspete(cfg, m):")
    if start < 0:
        raise SystemExit("OPRIT: trateaza_oaspete lipsă. Nu s-a scris nimic.")
    sfarsit = text.find("\n\n\n", start + 1)
    corp = text[start:sfarsit]
    for vechi, nou in IN_TRATEAZA_OASPETE:
        if vechi not in corp:
            raise SystemExit(f"OPRIT: în trateaza_oaspete lipsește «{vechi}». Nu s-a scris nimic.")
        corp = corp.replace(vechi, nou)
    return text[:start] + corp + text[sfarsit:]


def proba(cale):
    cod = open(cale, encoding="utf-8").read()
    arbore = ast.parse(cod)
    f = {n.name: ast.get_source_segment(cod, n) for n in ast.walk(arbore) if isinstance(n, ast.FunctionDef)}
    assert 'm["de_la"]' not in "".join(l for l in f["trateaza_oaspete"].splitlines(True) if "trimite_text(" in l), \
        "un răspuns de invitat/grup ar pleca tot la persoană"
    p = f["primeste"]
    assert p.index("if grup:") < p.index("inbox_pune(m)"), "filtrul de grup trebuie aplicat înainte de coadă"
    assert "GR.corp_mesaj(catre" in f["trimite_text"]
    assert "GR.executa_admin(" in cod and "import whatsapp_grupuri as GR" in cod
    return "grup: doar «Kelion»+cerere, ruta izolată, răspuns în grup, memorie de grup; comenzi «grup nou»/«grupuri» pentru Adrian"


if __name__ == "__main__":
    sursa, destinatie = sys.argv[1], sys.argv[2]
    original = open(os.path.join(sursa, "whatsapp.py"), encoding="utf-8").read()
    if MARCAJ in original:
        raise SystemExit("DEJA APLICAT.")
    os.makedirs(destinatie, exist_ok=True)
    cale = os.path.join(destinatie, "whatsapp.py")
    with open(cale, "w", encoding="utf-8") as h:
        h.write(aplica(original))
    py_compile.compile(cale, doraise=True)
    print("OK: legătura grupurilor aplicată pe copie, compilare reușită.")
    print("OK proba:", proba(cale))
