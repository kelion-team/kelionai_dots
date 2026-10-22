"""R32 (22.10.2026): pași rămași «in executie» cu procesul mort.

Pe server (doar citire, 03:53): pasul 7737 al cererii C20261021-173810-8ebf71 (o sarcină pusă de bucla testerului,
oprită de PR #81) e «in executie» din 21.10 17:38, cu pid 161755 care nu mai există. Nimic nu-l mai închide, deci R32
pică la fiecare verificare. Îl marcăm «esuat»; nu se șterge nimic.

Siguranță (revizuirea lui Kelion, 22.10): se închide doar un pas pornit de peste 30 min al cărui proces NU mai există
(/proc/<pid> lipsă) și a cărui amprentă «pid:...» are același pid; un pas fără pid sau cu amprentă nepotrivită rămâne
neatins. Dovada existentă se PĂSTREAZĂ: motivul se adaugă după ea. Orice eroare SQLite iese cu cod ≠ 0.

  python3 inchide_pasi_orfani.py CALE_SQLITE      (rulat ca utilizatorul brain)
"""
import os
import sqlite3
import sys
import time


def viu(pid):
    return bool(pid) and os.path.exists(f"/proc/{int(pid)}")


def mort_sigur(pid, amprenta, t_start, acum):
    if not pid or viu(pid) or not t_start or acum - t_start < 1800:
        return False
    return str(amprenta or "").split(":", 1)[0] == str(int(pid))


def inchide(cale, acum=None):
    acum = acum or time.time()
    db = sqlite3.connect(cale, timeout=30)
    try:
        with db:
            morti = [(i, c, p, d) for i, c, p, a, t, d in
                     db.execute("SELECT id, cerere, pid, amprenta, t_start, dovada FROM pasi WHERE stare='in executie'")
                     if mort_sigur(p, a, t, acum)]
            for i, c, p, d in morti:
                motiv = f"proces mort (pid {p} lipsă în /proc); închis la curățenia R32 din {time.strftime('%d.%m %H:%M', time.localtime(acum))}"
                cur = db.execute("UPDATE pasi SET stare='esuat', t_sfarsit=?, dovada=? WHERE id=? AND stare='in executie'",
                                 (acum, (d + " | " if d else "") + motiv, i))
                if cur.rowcount != 1:
                    raise RuntimeError(f"pasul {i} s-a schimbat între timp; nimic scris")
    finally:
        db.close()
    return [(i, c, p) for i, c, p, _ in morti]


if __name__ == "__main__":
    m = inchide(sys.argv[1])
    print(f"pași orfani închiși: {len(m)} {[c for _, c, _ in m][:5]}")
