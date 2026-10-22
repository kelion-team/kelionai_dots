"""R32 (22.10.2026): pași rămași «in executie» cu procesul mort.

Pe server (doar citire, 03:53): pasul 7737 al cererii C20261021-173810-8ebf71 (o sarcină pusă de bucla testerului,
oprită de PR #81) e «in executie» din 21.10 17:38, cu pid 161755 care nu mai există. Nimic nu-l mai închide, deci R32
pică la fiecare verificare. Îl marcăm «esuat» cu motivul scris în «dovada»; nu se șterge nimic.

  python3 inchide_pasi_orfani.py CALE_SQLITE      (rulat ca utilizatorul brain)
"""
import os
import sqlite3
import sys
import time


def viu(pid):
    return bool(pid) and os.path.exists(f"/proc/{int(pid)}")


def inchide(cale, acum=None):
    acum = acum or time.time()
    db = sqlite3.connect(cale, timeout=30)
    with db:
        morti = [(i, c, p) for i, c, p in db.execute("SELECT id, cerere, pid FROM pasi WHERE stare='in executie'") if not viu(p)]
        for i, c, p in morti:
            db.execute("UPDATE pasi SET stare='esuat', t_sfarsit=?, dovada=? WHERE id=? AND stare='in executie'",
                       (acum, f"proces mort (pid {p}); închis la curățenia R32 din {time.strftime('%d.%m %H:%M', time.localtime(acum))}", i))
    db.close()
    return morti


if __name__ == "__main__":
    m = inchide(sys.argv[1])
    print(f"pași orfani închiși: {len(m)} {[c for _, c, _ in m][:5]}")
