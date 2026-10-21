"""Grupuri WhatsApp cu Kelion (Adrian, 21.10.2026).

Reguli:
  * În grup, Kelion răspunde DOAR când un mesaj scris îl cheamă pe nume ȘI are o cerere («Kelion, ce vreme e mâine?»).
    «Kelion» singur, cuvinte care doar conțin numele (kelionai.app) și mesajele vocale din grup sunt ignorate.
  * În grup, Kelion răspunde mereu pe ruta IZOLATĂ (ca pentru invitați): fără datele, memoria sau uneltele private ale lui
    Adrian, chiar dacă scrie Adrian. Istoricul e al grupului, nu al fiecărei persoane.
  * Adrian, în conversația 1-la-1 cu Kelion: «grup nou Familie» creează un grup (cu link de invitație), «grupuri» le listează.

Limite Meta (Groups API, verificate 21.10.2026): numărul trebuie să fie Official Business Account; maximum 8 participanți
pe grup (inclusiv Kelion); intrarea doar prin link de invitație; apelurile de voce nu există în grupuri.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

NUME_KELION = re.compile(r"(?<![\w.@/-])@?kelion(?![\w.-]*\w)", re.I)
CMD_NOU = re.compile(r"^\s*grup\s+nou\s+(?P<nume>[^\n]{1,60}?)\s*[.!]*\s*$", re.I)
CMD_LISTA = re.compile(r"^\s*grupuri\s*[.!?]*\s*$", re.I)
GRUPURI_IMPLICITE = ("Familie", "Prieteni")
MAX_PARTICIPANTI = 8


def cerere_pentru_kelion(text):
    """None dacă mesajul nu-l cheamă pe Kelion cu o cerere; altfel cererea, fără numele lui."""
    t = text or ""
    m = NUME_KELION.search(t)
    if not m:
        return None
    cerere = re.sub(r"\s{2,}", " ", (t[:m.start()] + " " + t[m.end():])).strip(" \t\n,.:;!?-–—")
    return cerere if len(re.sub(r"\W", "", cerere)) >= 2 else None


def comanda_admin(text):
    """('nou', nume) | ('lista', None) | None — doar pentru mesajele lui Adrian, 1-la-1."""
    t = text or ""
    m = CMD_NOU.match(t)
    if m:
        nume = re.sub(r"[\x00-\x1f]", "", m.group("nume")).strip()
        return ("nou", nume) if nume else None
    return ("lista", None) if CMD_LISTA.match(t) else None


def scurt(group_id):
    return str(group_id or "")[-6:]


def cheie_istoric(m):
    """Istoricul (memoria izolată) e al grupului, nu al persoanei care scrie."""
    return ("grup:" + m["grup"]) if m.get("grup") else m["de_la"]


def destinatar(m):
    """Unde pleacă răspunsul: în grup (prefixul «grup:» îl înțelege trimite_text) sau persoanei."""
    return ("grup:" + m["grup"]) if m.get("grup") else m["de_la"]


def corp_mesaj(catre, text):
    """Corpul de trimitere Meta pentru o persoană sau pentru un grup («grup:<id>»)."""
    catre = str(catre)
    grup = catre.startswith("grup:")
    return {"messaging_product": "whatsapp", "recipient_type": "group" if grup else "individual",
            "to": catre[5:] if grup else catre, "type": "text", "text": {"preview_url": False, "body": text}}


# ------------------------------------------------------------------ Meta
class Meta:
    """Apelurile Graph API pentru grupuri. Tokenul pleacă doar spre gazda Graph configurată, fără redirectări."""

    def __init__(self, token, graph="https://graph.facebook.com", ver="v23.0", deschide=None):
        self.token, self.graph, self.ver = token, graph.rstrip("/"), ver
        self.deschide = deschide or urllib.request.build_opener(_FaraRedirectari()).open

    def cere(self, metoda, cale, corp=None, interogare=None):
        url = f"{self.graph}/{self.ver}/{cale.lstrip('/')}"
        if interogare:
            url += "?" + urllib.parse.urlencode(interogare)
        date = json.dumps(corp).encode() if corp is not None else None
        req = urllib.request.Request(url, data=date, method=metoda,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with self.deschide(req, timeout=20) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}
        except (OSError, ValueError) as e:
            return 0, {"error": {"message": type(e).__name__}}

    def creeaza_grup(self, phone_id, nume, descriere=""):
        corp = {"messaging_product": "whatsapp", "subject": nume[:128], "join_approval_mode": "auto_approve"}
        if descriere:
            corp["description"] = descriere[:2048]
        return self.cere("POST", f"{phone_id}/groups", corp)

    def link_invitatie(self, group_id):
        st, d = self.cere("GET", f"{group_id}/invite_link")
        return d.get("invite_link") if st == 200 else None

    def grupuri(self, phone_id, limita=50):
        st, d = self.cere("GET", f"{phone_id}/groups", interogare={"limit": limita})
        return (d.get("data") or []) if st == 200 else None, (d.get("error") or {}) if st != 200 else None

    def info(self, group_id):
        st, d = self.cere("GET", str(group_id), interogare={"fields": "subject,total_participant_count"})
        return d if st == 200 else {}


class _FaraRedirectari(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


# ------------------------------------------------------------------ registrul local (nume -> id, link)
def _registru(stare):
    return os.path.join(stare, "grupuri.json")


def citeste_registru(stare):
    try:
        with open(_registru(stare), encoding="utf-8") as h:
            return json.load(h)
    except (OSError, ValueError):
        return {}


def scrie_registru(stare, reg):
    os.makedirs(stare, exist_ok=True)
    tmp = _registru(stare) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as h:
        json.dump(reg, h, ensure_ascii=False, indent=1)
    os.replace(tmp, _registru(stare))


def eroare_text(err):
    cod, msg = (err or {}).get("code"), (err or {}).get("message") or "eroare necunoscută"
    if cod in (100, 131000, 200, 10) or "official" in str(msg).lower() or "permission" in str(msg).lower():
        return (f"Meta nu permite grupuri pentru acest număr ({cod}: {msg[:120]}). "
                "Condiția Meta: numărul să fie Official Business Account.")
    return f"Meta a răspuns cu eroare ({cod}: {msg[:160]})."


def creeaza(meta, phone_id, nume, stare):
    """Creează grupul și întoarce textul pentru Adrian (cu linkul de invitație, dacă Meta îl dă imediat)."""
    reg = citeste_registru(stare)
    for gid, g in reg.items():
        if g.get("nume", "").lower() == nume.lower() and g.get("phone_id") == phone_id:
            link = meta.link_invitatie(gid) or g.get("link")
            return f"Grupul «{nume}» există deja.\nLink de invitație: {link or 'încă indisponibil'}"
    st, d = meta.creeaza_grup(phone_id, nume, f"Grupul «{nume}» cu Kelion. Scrie «Kelion» și ce vrei, ca să-ți răspundă.")
    if st != 200:
        return eroare_text(d.get("error"))
    gid = str(d.get("id") or d.get("group_id") or "")
    link = meta.link_invitatie(gid) if gid else None
    if gid:
        reg[gid] = {"nume": nume, "phone_id": phone_id, "creat": time.strftime("%Y-%m-%d %H:%M"), "link": link}
        scrie_registru(stare, reg)
    return (f"Am creat grupul «{nume}» (maximum {MAX_PARTICIPANTI} persoane, cu tot cu mine).\n"
            f"Link de invitație: {link or 'vine în câteva secunde; scrie «grupuri» ca să-l vezi'}\n"
            "În grup răspund doar când cineva scrie «Kelion» și ce vrea.")


def listeaza(meta, phone_id, stare):
    date, err = meta.grupuri(phone_id)
    if date is None:
        return eroare_text(err)
    if not date:
        return "Nu există încă grupuri. Scrie «grup nou Familie» ca să creez unul."
    reg = citeste_registru(stare)
    linii = []
    for g in date[:20]:
        gid = str(g.get("id") or "")
        inf = meta.info(gid)
        link = meta.link_invitatie(gid)
        nume = inf.get("subject") or (reg.get(gid) or {}).get("nume") or gid
        if gid:
            reg[gid] = dict(reg.get(gid) or {}, nume=nume, phone_id=phone_id, link=link)
        linii.append(f"• {nume} — {inf.get('total_participant_count', '?')}/{MAX_PARTICIPANTI} persoane — {link or 'fără link'}")
    scrie_registru(stare, reg)
    return "Grupurile tale cu Kelion:\n" + "\n".join(linii)


def executa_admin(cfg, m, meta, stare, trimite_text, jurnal=lambda **k: None):
    """True dacă mesajul lui Adrian a fost o comandă de grup și a fost tratat aici."""
    c = comanda_admin(m.get("text"))
    if not c:
        return False
    phone_id = m.get("phone_id") or cfg.get("phone_id")
    r = creeaza(meta, phone_id, c[1], stare) if c[0] == "nou" else listeaza(meta, phone_id, stare)
    trimite_text(cfg, m["de_la"], r, m.get("id"))
    jurnal(ev="grup_comanda", tip=c[0], id=m.get("id"))
    return True
