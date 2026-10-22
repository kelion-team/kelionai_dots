"""A17 (curățenie): fiecare probă CDP lăsa în /tmp un director gol `playwright-artifacts-*`.

Dovadă (22.10.2026, doar citire): 2102 directoare goale, ~560/oră, utilizator brain. Sursa: proba din
pod_locuri/executor_server.py (la câteva secunde) și paznic.py (la 5 minute) ies din Playwright fără
`browser.close()`. La o conexiune CDP, `close()` doar închide conexiunea și șterge directorul; Chrome-ul
locului rămâne pornit (verificat local: vechi +3 directoare la 3 probe, nou +0, Chrome viu).

  python3 repara_curatenie_playwright.py SURSA DESTINATIE   (SURSA = /opt/kelion-pod)
"""
import os
import py_compile
import sys

R = {
    "pod_locuri/executor_server.py": [
        ("import contextlib",
         "            from playwright.sync_api import sync_playwright\n",
         "            import contextlib\n            from playwright.sync_api import sync_playwright\n"),
        ("conexiunea CDP se închide la ieșire",
         "                with sync_playwright() as pw:\n"
         "                    browser = pw.chromium.connect_over_cdp(f\"http://127.0.0.1:{loc.port_cdp}\", timeout=3000)\n",
         "                # closing(): la ieșire close() doar deconectează și șterge directorul temporar; Chrome rămâne.\n"
         "                with sync_playwright() as pw, contextlib.closing(\n"
         "                        pw.chromium.connect_over_cdp(f\"http://127.0.0.1:{loc.port_cdp}\", timeout=3000)) as browser:\n"),
    ],
    "paznic.py": [
        ("paznicul închide conexiunea CDP la orice ieșire",
         "    from playwright.async_api import async_playwright\n"
         "    async with async_playwright() as p:\n"
         "        b = await p.chromium.connect_over_cdp(CDP)\n",
         "    import contextlib\n"
         "    from playwright.async_api import async_playwright\n"
         "    # stiva se închide prima (și la excepții): close() doar deconectează și șterge directorul; Chrome rămâne\n"
         "    async with async_playwright() as p, contextlib.AsyncExitStack() as stiva:\n"
         "        b = await p.chromium.connect_over_cdp(CDP)\n"
         "        stiva.push_async_callback(b.close)\n"),
    ],
}
MARCAJ = "contextlib.closing("


def aplica(text, inlocuiri, fisier):
    for nume, vechi, nou in inlocuiri:
        n = text.count(vechi)
        if n != 1:
            raise SystemExit(f"OPRIT: {fisier}: «{nume}» găsit de {n} ori (trebuie exact 1). Nu s-a scris nimic.")
        text = text.replace(vechi, nou)
    return text


def proba(dest):
    import ast
    ex = open(os.path.join(dest, "pod_locuri/executor_server.py"), encoding="utf-8").read()
    assert "contextlib.closing(" in ex and "browser = pw.chromium.connect_over_cdp" not in ex
    pz = open(os.path.join(dest, "paznic.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(pz)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "chrome")
    src = ast.get_source_segment(pz, fn)
    assert "stiva.push_async_callback(b.close)" in src and "AsyncExitStack() as stiva" in src
    return "conexiunea CDP se închide la orice ieșire (și la excepții), în ambele locuri"


if __name__ == "__main__":
    sursa, dest = sys.argv[1], sys.argv[2]
    if MARCAJ in open(os.path.join(sursa, "pod_locuri/executor_server.py"), encoding="utf-8").read():
        raise SystemExit("DEJA APLICAT.")
    for fisier, inl in R.items():
        text = aplica(open(os.path.join(sursa, fisier), encoding="utf-8").read(), inl, fisier)
        cale = os.path.join(dest, fisier)
        os.makedirs(os.path.dirname(cale), exist_ok=True)
        open(cale, "w", encoding="utf-8").write(text)
        py_compile.compile(cale, doraise=True)
    print(f"OK: {sum(len(v) for v in R.values())} reparații, compilare reușită.")
    print("OK proba:", proba(dest))
