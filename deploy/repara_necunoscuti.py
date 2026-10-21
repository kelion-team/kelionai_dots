"""Pasul 3 (21.10.2026, cerința 8 din apel): ORICE număr WhatsApp primește răspuns.

Necunoscuții (nici în KELION_WA_PERMISI, nici în lista de invitați) nu mai sunt respinși: merg pe ruta IZOLATĂ de
invitați (Kelion separat, fără dot-ul lui Adrian, fără Chrome-ul și fără datele lui), cu limba detectată automat și
un salut fără nume. Dot-ul lui Adrian rămâne doar pentru numerele din KELION_WA_PERMISI. Dacă ruta de invitați e
ocupată, apelul e respins ca «ocupat» (ca până acum la invitați) și motivul intră în jurnal.

Dovadă (cod live, 21.10.2026): connect() -> ramura «respins_nepermis» respingea orice număr necunoscut.

  python3 repara_necunoscuti.py SURSA DESTINATIE   (SURSA = /opt/kelion-pod)
"""
import os
import py_compile
import shutil
import sys

R = {
    "kelion_pod.py": [
        ("necunoscutii pe ruta izolata de invitati",
         """        if not PERMISI or de_la not in PERMISI:   # numar necunoscut sau lipsa: respins (dot-ul e doar al lui Adrian)
            await self.graph({"call_id": cid, "action": "reject"})
            jurnal(ev="respins_nepermis", id=cid, de_la=masca(de_la))
            trace_emit("pod", "rejection_decision", cid, reason="unauthorized")
            return""",
         """        if not PERMISI or de_la not in PERMISI:
            # Adrian 21.10.2026: orice numar primeste raspuns. Necunoscutii merg pe ruta IZOLATA de invitati
            # (fara dot-ul, Chrome-ul sau datele lui Adrian); dot-ul ramane doar pentru KELION_WA_PERMISI.
            if de_la and not self.invitat:
                jurnal(ev="necunoscut_pe_ruta_invitat", id=cid, de_la=masca(de_la))
                trace_emit("pod", "guest_branch", cid, guest=True)
                return await self.connect_invitat(c, cid, de_la, necunoscut=True)
            await self.graph({"call_id": cid, "action": "reject"})
            jurnal(ev="respins_nepermis", id=cid, de_la=masca(de_la),
                   motiv="ruta de invitati ocupata" if de_la else "fara numar")
            trace_emit("pod", "rejection_decision", cid, reason="busy_guest" if de_la else "unauthorized")
            return"""),
        ("ruta invitat accepta un necunoscut",
         """    async def connect_invitat(self, c, cid, de_la):
        nume, limba = oaspeti()[de_la]""",
         """    async def connect_invitat(self, c, cid, de_la, necunoscut=False):
        # necunoscut: fara nume si fara limba data -> transcrierea detecteaza limba, salut fara nume
        nume, limba = ("", "") if necunoscut else oaspeti()[de_la]"""),
    ],
    "apel_invitat.py": [
        ("salut fara nume pentru necunoscuti",
         """        self.salut = f"{w.salut_ora()}, {nume}! Sunt Kelion, asistentul lui Adrian. Cu ce te pot ajuta?\"""",
         """        self.salut = (f"{w.salut_ora()}, {nume}! Sunt Kelion, asistentul lui Adrian. Cu ce te pot ajuta?" if nume else
                      f"{w.salut_ora()}! Hello! Sunt Kelion, asistentul lui Adrian. Cu ce te pot ajuta? How can I help?\")"""),
    ],
}
MARCAJ = "necunoscut_pe_ruta_invitat"


def aplica(text, inlocuiri, fisier):
    for nume, vechi, nou in inlocuiri:
        n = text.count(vechi)
        if n != 1:
            raise SystemExit(f"OPRIT: {fisier}: «{nume}» găsit de {n} ori (trebuie exact 1). Nu s-a scris nimic.")
        text = text.replace(vechi, nou)
    return text


def proba(destinatie):
    """Pe codul reparat: ramura pentru necunoscuți duce la ruta de invitați, nu la respingere; dot-ul nu e atins."""
    import ast
    cod = open(os.path.join(destinatie, "kelion_pod.py"), encoding="utf-8").read()
    arbore = ast.parse(cod)
    connect = next(n for n in ast.walk(arbore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "connect")
    sursa = ast.get_source_segment(cod, connect)
    i_nec = sursa.index("if not PERMISI or de_la not in PERMISI")
    i_ruta = sursa.index("connect_invitat(c, cid, de_la, necunoscut=True)", i_nec)
    i_reject = sursa.index('"action": "reject"', i_nec)
    assert i_ruta < i_reject, "necunoscutul ar fi respins înainte de ruta de invitați"
    assert sursa.index("self.manager.aloca") > i_reject, "un necunoscut nu trebuie să ajungă la locurile dot ale lui Adrian"
    ci = next(n for n in ast.walk(arbore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "connect_invitat")
    assert "necunoscut" in [a.arg for a in ci.args.args] and ci.args.defaults, "connect_invitat(necunoscut=False) lipsă"
    return "necunoscut -> ruta izolată de invitați (înaintea respingerii); locurile dot rămân doar pentru numerele permise"


if __name__ == "__main__":
    sursa, destinatie = sys.argv[1], sys.argv[2]
    with open(os.path.join(sursa, "kelion_pod.py"), encoding="utf-8") as h:
        if MARCAJ in h.read():
            raise SystemExit("DEJA APLICAT.")
    os.makedirs(destinatie, exist_ok=True)
    for fisier, inlocuiri in R.items():
        with open(os.path.join(sursa, fisier), encoding="utf-8") as h:
            text = aplica(h.read(), inlocuiri, fisier)
        cale = os.path.join(destinatie, fisier)
        with open(cale, "w", encoding="utf-8") as h:
            h.write(text)
        py_compile.compile(cale, doraise=True)
    print(f"OK: {sum(len(v) for v in R.values())} reparații, compilare reușită.")
    print("OK proba:", proba(destinatie))
