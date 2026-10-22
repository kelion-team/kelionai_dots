"""S7 + S14 (22.10.2026): verificatorul site-ului (/opt/kelion-brain/verifica-site.py) raporta 3 defecte false.

- „legătura /app/cont … duce la o pagină inexistentă” (din /app/guides/ și /app/launcher/): /app/cont nu e fișier în
  /var/www; îl servește portalul kelion-control (8094), după Caddyfile @kelion_control.
- „Kitul serverului Linux … arhivă stricată”: kitul a fost RETRAS intenționat pe 20.10 (scriptul afișează RETRASA și
  iese cu 78). Nu e o arhivă stricată, e o funcție scoasă; se raportează „nu se aplică”.

  python3 repara_verificator.py SURSA DESTINATIE   (SURSA = /opt/kelion-brain)
"""
import os
import py_compile
import sys

F = "verifica-site.py"
R = [
    ("rutele portalului",
     'WWW = "/var/www/kelion"\n',
     'WWW = "/var/www/kelion"\n'
     '# Servite de portalul kelion-control (8094), nu din WWW: Caddyfile, matcher @kelion_control.\n'
     'PORTAL = ("/app", "/app/cont", "/app/whatsapp-secrete")\n'
     'PORTAL_PREFIX = ("/app/control-api/", "/app/control-assets/")\n'),
    ("legături către portal",
     '        if tinta.startswith("/app/api/"):\n            continue\n',
     '        if tinta.startswith("/app/api/"):\n            continue\n'
     '        if tinta.split("?")[0].split("#")[0].rstrip("/") in PORTAL or tinta.startswith(PORTAL_PREFIX):\n'
     '            continue\n'),
    ("kit Linux retras",
     '        if href.endswith("Kelion-Brain-Setup.run"):\n',
     '        if href.endswith("Kelion-Brain-Setup.run") and "RETRASA" in open(WWW + href, encoding="utf-8", errors="replace").read(4096):\n'
     '            return True, "nu se aplica: kitul Linux a fost retras intentionat (20.10); recuperarea se face din sursa canonica Contabo"\n'
     '        if href.endswith("Kelion-Brain-Setup.run"):\n'),
]
MARCAJ = "PORTAL_PREFIX"


def aplica(text):
    for nume, vechi, nou in R:
        n = text.count(vechi)
        if n != 1:
            raise SystemExit(f"OPRIT: {F}: «{nume}» găsit de {n} ori (trebuie exact 1). Nu s-a scris nimic.")
        text = text.replace(vechi, nou)
    return text


if __name__ == "__main__":
    sursa, dest = sys.argv[1], sys.argv[2]
    text = open(os.path.join(sursa, F), encoding="utf-8").read()
    if MARCAJ in text:
        raise SystemExit("DEJA APLICAT.")
    nou = aplica(text)
    os.makedirs(dest, exist_ok=True)
    cale = os.path.join(dest, F)
    open(cale, "w", encoding="utf-8").write(nou)
    py_compile.compile(cale, doraise=True)
    print(f"OK: {len(R)} reparații, compilare reușită.")
