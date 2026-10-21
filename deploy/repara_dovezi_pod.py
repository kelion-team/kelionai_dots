"""Prepare diagnostics-only copies; never install, restart, or touch calls.
Usage: python3 repara_dovezi_pod.py SOURCE NEW_DESTINATION
Inputs must match the methods from deploy/repara_pod.py already audited live.
Inspect diff, backup and use a separately approved idle deployment procedure.
"""
from pathlib import Path
import sys

OLD_CAPTURE = '    async def _captura_dot(self, a, motiv):\n        try:\n            pg = a.dot_page\n            if pg is None or pg.is_closed():\n                return\n            os.makedirs("/var/lib/kelion-pod/capturi", exist_ok=True)\n            baza = "/var/lib/kelion-pod/capturi/" + time.strftime("%Y%m%d-%H%M%S") + "-" + motiv\n            await asyncio.wait_for(pg.screenshot(path=baza + ".png"), 3.0)\n            text = await asyncio.wait_for(pg.evaluate("document.body.innerText.slice(-2000)"), 2.0)\n            butoane = await asyncio.wait_for(pg.evaluate(\n                "[...document.querySelectorAll(\'button[aria-label]\')].map(b => b.getAttribute(\'aria-label\')).slice(0, 80)"), 2.0)\n            with open(baza + ".txt", "w", encoding="utf-8") as h:\n                h.write(text + "\\n\\n--- butoane ---\\n" + "\\n".join(butoane))\n            jurnal(ev="captura_dot", fisier=baza, motiv=motiv)\n        except Exception as e:\n            jurnal(ev="captura_dot_esuata", motiv=type(e).__name__)\n\n'
NEW_CAPTURE = '    async def _captura_dot(self, a, motiv):\n        pg = a.dot_page\n        if pg is None or pg.is_closed():\n            return\n        try:\n            os.makedirs("/var/lib/kelion-pod/capturi", exist_ok=True)\n            baza = "/var/lib/kelion-pod/capturi/" + time.strftime("%Y%m%d-%H%M%S") + "-" + motiv\n        except Exception as e:\n            jurnal(ev="captura_dot_esuata", etapa="director", motiv=type(e).__name__)\n            return\n        try:\n            await asyncio.wait_for(pg.screenshot(path=baza + ".png"), 3.0)\n            jurnal(ev="captura_dot", fisier=baza + ".png", motiv=motiv)\n        except Exception as e:\n            jurnal(ev="captura_dot_esuata", etapa="screenshot", motiv=type(e).__name__)\n        try:\n            text = await asyncio.wait_for(pg.evaluate("document.body.innerText.slice(0, 2000)"), 2.0)\n            with open(baza + ".txt", "w", encoding="utf-8") as h:\n                h.write(text)\n            jurnal(ev="captura_dot", fisier=baza + ".txt", motiv=motiv)\n        except Exception as e:\n            jurnal(ev="captura_dot_esuata", etapa="text", motiv=type(e).__name__)\n        try:\n            butoane = await asyncio.wait_for(pg.evaluate(\n                "[...document.querySelectorAll(\'button[aria-label]\')].map(b => b.getAttribute(\'aria-label\')).slice(0, 80)"), 2.0)\n            with open(baza + ".txt", "a", encoding="utf-8") as h:\n                h.write("\\n\\n--- butoane ---\\n" + "\\n".join(butoane))\n        except Exception as e:\n            jurnal(ev="captura_dot_esuata", etapa="butoane", motiv=type(e).__name__)\n\n'
OLD_COMMAND = '    def _eroare_sunet(self, loc, ce, r):\n        eroare = ((r.stderr or "") + (r.stdout or "")).strip()[:200]\n        cheie = (loc.numar, ce, eroare)\n        if getattr(self, "_ultima_eroare_sunet", None) != cheie:\n            self._ultima_eroare_sunet = cheie\n            self.jurnal({"ev": "sunet_loc_esuat", "loc": loc.numar, "ce": ce, "cod": r.returncode, "eroare": eroare})\n        raise RuntimeError(f"sunet_loc_esuat {ce}: {eroare}")\n\n'
NEW_COMMAND = '    def _eroare_sunet(self, loc, ce, r):\n        # Emit only the known pactl grammar; never arbitrary argv or credentials.\n        import re\n        args = getattr(r, "args", None)\n        allowed = {"pactl", "list", "short", "sinks", "sources", "load-module",\n                   "module-null-sink", "module-remap-source", "rate=48000", "channels=1"}\n        pattern = r"(?:sink_name|source_name|master)=[A-Za-z0-9_.-]+|(?:sink|source)_properties=device.description=[A-Za-z0-9_.-]+"\n        command = [x if isinstance(x, str) and (x in allowed or re.fullmatch(pattern, x))\n                   else "[REDACTED]" for x in args] if isinstance(args, (list, tuple)) else ["[UNAVAILABLE]"]\n        raw = ((r.stderr or "") + (r.stdout or "")).strip()\n        raw = re.sub(r"(?i)(password|passwd|token|secret|authorization|api[_-]?key)(\\s*[=:]\\s*|\\s+)[^\\s,;]+", r"\\1=[REDACTED]", raw)\n        eroare = raw[:200]\n        cheie = (loc.numar, ce, tuple(command), eroare)\n        if getattr(self, "_ultima_eroare_sunet", None) != cheie:\n            self._ultima_eroare_sunet = cheie\n            self.jurnal({"ev": "sunet_loc_esuat", "loc": loc.numar, "ce": ce,\n                         "comanda": command, "cod": r.returncode, "eroare": eroare})\n        raise RuntimeError(f"sunet_loc_esuat {ce}: {eroare}")\n\n'
PATCHES = [("kelion_pod.py", OLD_CAPTURE, NEW_CAPTURE), ("pod_locuri/executor_server.py", OLD_COMMAND, NEW_COMMAND)]

def transform(source, old, new):
    if source.count(old) != 1:
        raise ValueError("Source drift or already applied: expected exactly one method")
    result = source.replace(old, new, 1)
    compile(result, "<patched>", "exec")
    return result


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or destination == source or source in destination.parents:
        raise ValueError("Destination must be new and outside source")
    prepared = {name: transform((source / name).read_text(), old, new)
                for name, old, new in PATCHES}
    # Validate every file before creating output. No original file is modified.
    destination.mkdir(parents=True)
    for name, text in prepared.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return list(prepared)


if __name__ == "__main__":
    print("Prepared copies only:", prepare(*sys.argv[1:]))
