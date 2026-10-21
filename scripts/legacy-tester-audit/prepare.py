#!/usr/bin/env python3
"""Prepare, never install, a source-pinned correction to the legacy UI tester."""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
from pathlib import Path

EXPECTED_SHA256 = "b5bc8440d0afd91571c457f35deb7f288acccc39a34ab21128e9ece508d263f4"
TARGET = "/opt/kelion-brain/tester-ui.py"

HELPERS = '''
# This local adapter serves legacy files, not Caddy's authenticated portal route.
# Do not infer production acceptance from a locally rendered legacy page.
TEST_SURFACE = "legacy-static-local"
LIVE_COVERAGE_GAPS = [
    "Caddy routes /app/ to portal 8094; this adapter serves legacy index.html.",
    "Authenticated portal /app/control-api/state is not exercised by this adapter.",
]


def coverage_only(page):
    """Known adapter route gap, with all other measured checks passing.

    Keep the raw 404 and the failed page result. Only exclude this *adapter*
    failure from automatic application-repair requests; never hide other errors.
    """
    http = page.get("erori_http", [])
    console = page.get("erori_consola", [])
    return bool(
        http and all(e == {"url": "/app/control-api/state", "status": 404} for e in http)
        and all(e == "Failed to load resource: the server responded with a status of 404 (Not Found)" for e in console)
        and not page.get("cereri_esuate") and not page.get("eroare")
        and not page.get("prea_rar") and page.get("status_http") == 200
        and page.get("date_afisate_s") is not None
        and ("eveniment" not in page or (
            page.get("eveniment_ecran_s") is not None
            and page["eveniment_ecran_s"] <= TINTA_S))
    )


def describe_defect(page):
    details = [page.get("prea_rar"), page.get("eroare")]
    if page.get("erori_consola"):
        details.append("erori consola " + str(page["erori_consola"][:2]))
    if page.get("erori_http"):
        details.append("HTTP " + ", ".join(
            f"{e['status']} {e['url']}" for e in page["erori_http"]))
    if page.get("cereri_esuate"):
        details.append("cereri esuate " + str(page["cereri_esuate"][:2]))
    if "eveniment" in page and not page["ok"]:
        details.append("eveniment->ecran " + str(page.get("eveniment_ecran_s")) + " s")
    if page.get("date_afisate_s") is None:
        details.append("datele nu se afiseaza")
    if coverage_only(page):
        details.append("LIPSA ACOPERIRE ADAPTOR; endpointul LIVE nu a fost masurat")
    return page["pagina"] + ": " + "; ".join(filter(None, details))


'''


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("expected source anchor is missing or ambiguous")
    return source.replace(old, new, 1)


def transform(data: bytes) -> bytes:
    if hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        raise ValueError("source drift: SHA256 does not match the reviewed Contabo source")
    source = data.decode("utf-8")
    source = replace_once(source, '"""Tester Kelion: deschide paginile /app/ AUTENTIFICAT intr-un Chromium real (Playwright), in locul lui Adrian, si MASOARA.',
        '"""Tester Kelion: diagnostic LEGACY LOCAL in Chromium (Playwright), NU acceptanta LIVE.\n'
        'Ruta autentificata Caddy /app/ si autentificarea portalului nu sunt exercitate aici.')
    source = replace_once(source, "def main(pagini):", HELPERS + "def main(pagini):")
    source = replace_once(source,
        '    rez["ok"] = all(x["ok"] for x in rez["pagini"])',
        '    rez["surface"] = TEST_SURFACE\n'
        '    rez["coverage_gaps"] = list(LIVE_COVERAGE_GAPS)\n'
        '    rez["legacy_ok"] = all(x["ok"] for x in rez["pagini"])\n'
        '    rez["live_acceptance"] = False\n'
        '    rez["ok"] = False  # Consumers of the old field must not infer LIVE acceptance.')
    start = source.index('    defecte = sorted({f"{x[\'pagina\']}: "')
    end = source.index('    rez["defecte"] = defecte', start)
    source = source[:start] + (
        '    defecte = sorted({describe_defect(x) for x in rez["pagini"] if not x["ok"]})\n'
        '    reparabile = sorted({describe_defect(x) for x in rez["pagini"]\n'
        '                         if not x["ok"] and not coverage_only(x)})\n'
        '    rez["defecte_legacy"] = defecte\n'
        '    rez["defecte_reparabile"] = reparabile\n'
    ) + source[end:]
    source = replace_once(source,
        '    if defecte and os.environ.get("KELION_TESTER_REPARA", "1") == "1":',
        '    if reparabile and os.environ.get("KELION_TESTER_REPARA", "1") == "1":')
    source = replace_once(source,
        '"Testerul Kelion (Chromium autentificat, masurare reala la 1280 si 390 px) a gasit pe LIVE: " + " | ".join(defecte)',
        '"Testerul Kelion (Chromium, adaptor LEGACY LOCAL, NU acceptanta LIVE, 1280 si 390 px) a gasit: " + " | ".join(reparabile)')
    source = replace_once(source,
        '+ ". Repara cauza in fisierele live (copie in proiect), test.sh care ruleaza /opt/kelion-brain/tester-ui.py pe paginile atinse, "\n'
        '                "livrare DOAR prin kelion-pregateste-livrare /var/www/kelion/app ... --proba (proba = tester-ui.py pe live, tinta eveniment->ecran <= 5 s). "\n'
        '                "Nu reduce testele ca sa treaca.", sursa="Tester Kelion (automat)")',
        '+ ". Investigheaza pe copie izolata daca defectul apartine adaptorului sau aplicatiei. "\n'
        '                "Pastreaza modificarile preexistente. Nu modifica LIVE pe baza acestui diagnostic local. "\n'
        '                "Acceptanta LIVE necesita separat ruta Caddy reala si autentificare aprobata. "\n'
        '                "Nu reduce testele ca sa treaca.", sursa="Tester Kelion (automat)")')
    source = replace_once(source,
        '    linii = [f"TESTER KELION {rez[\'ora\']}: {\'TOATE OK\' if rez[\'ok\'] else \'PROBLEME\'} ({sum(x[\'ok\'] for x in rez[\'pagini\'])}/{len(rez[\'pagini\'])} pagini x latimi)"]',
        '    linii = [f"TESTER KELION {rez[\'ora\']}: LEGACY LOCAL ({sum(x[\'ok\'] for x in rez[\'pagini\'])}/{len(rez[\'pagini\'])} pagini x latimi)",\n'
        '             "Acceptanta LIVE: NEVERIFICATA; ruta Caddy si autentificarea portalului nu au fost testate."]')
    source = replace_once(source,
        '                     + (f"; eroare: {x[\'eroare\']}" if x.get("eroare") else "")',
        '                     + ("; HTTP: " + str(x["erori_http"]) if x.get("erori_http") else "")\n'
        '                     + ("; LIPSA ACOPERIRE ADAPTOR" if coverage_only(x) else "")\n'
        '                     + (f"; eroare: {x[\'eroare\']}" if x.get("eroare") else "")')
    ast.parse(source)
    return source.encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New .patch artifact, never an installed file")
    args = parser.parse_args(argv)
    if args.source.is_symlink() or not args.source.is_file():
        parser.error("source must be a regular, non-symlink file")
    if args.output.suffix != ".patch" or args.output.exists() or args.output.is_symlink():
        parser.error("output must be a new .patch file")
    before = args.source.read_bytes()
    after = transform(before)
    patch = "".join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                       fromfile=TARGET, tofile=TARGET))
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(patch)
    print("Prepared only; no server files changed.")
    print("source_sha256=" + hashlib.sha256(before).hexdigest())
    print("candidate_sha256=" + hashlib.sha256(after).hexdigest())
    print("patch_sha256=" + hashlib.sha256(patch.encode()).hexdigest())


if __name__ == "__main__":
    main()
