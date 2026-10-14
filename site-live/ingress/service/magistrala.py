"""Magistrala Kelion: rutare automată a fiecărei cereri și escaladare.

Suprafețe: chat (ChatGPT Astra 6.1), work (ChatGPT Work), codex (Codex),
magentic (orchestratorul Microsoft Magentic cu DOTS).
Clasificarea e deterministă, fără apel AI suplimentar. Execuția se face prin
backend-uri injectate; modulul nu face apeluri de rețea.
"""
import re
import time

SURFACES = ("chat", "work", "codex", "magentic")
EFFORTS = ("low", "medium", "high", "xhigh")
MAX_EFFORT = {"chat": "high", "work": "high", "codex": "xhigh", "magentic": "xhigh"}
NEXT_SURFACE = {"chat": "work", "work": "magentic", "codex": "magentic", "magentic": None}
MAX_HOPS = 6

CODE_WORDS = ("cod", "bug", "eroare", "repo", "commit", "deploy", "script", "python",
              "javascript", "sql", "endpoint", "server", "refactor", "github", "test")
TOOL_WORDS = ("email", "gmail", "calendar", "drive", "notion", "slack", "document",
              "prezentare", "tabel", "excel", "programeaza", "rezerva", "cauta pe web")
DEEP_WORDS = ("analiza", "strategie", "arhitectura", "demonstreaza", "compara", "de ce", "plan")
MULTI_WORDS = ("proiect complet", "mai multi agenti", "orchestr", "pas cu pas", "end-to-end")


def _plain(text):
    table = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaisstt" + "AAISSTT")
    return text.translate(table).lower()


def _has(text, words):
    return [w for w in words if re.search(r"\b" + re.escape(w), text)]


def route(task):
    """Alege suprafața, dificultatea (1..4) și efortul pentru o cerere."""
    if not isinstance(task, str) or not task.strip():
        raise ValueError("Cerere goală")
    t = _plain(task)
    code, tools, deep, multi = _has(t, CODE_WORDS), _has(t, TOOL_WORDS), _has(t, DEEP_WORDS), _has(t, MULTI_WORDS)
    steps = len(re.findall(r"(?m)^\s*(\d+[.)]|-|\*)\s+", task))
    difficulty = 1 + (len(task) > 400) + bool(deep) + (steps >= 3 or len(task) > 1500)
    difficulty = min(difficulty, 4)
    if multi or (steps >= 3 and (code or tools)) or (code and tools):
        surface, why = "magentic", "sarcină în mai mulți pași / mai multe domenii"
        difficulty = max(difficulty, 3)
    elif code:
        surface, why = "codex", "cod: " + ", ".join(code[:3])
    elif tools:
        surface, why = "work", "unelte/conectori: " + ", ".join(tools[:3])
    else:
        surface, why = "chat", "conversație / răspuns direct"
    effort = EFFORTS[min(difficulty - 1, EFFORTS.index(MAX_EFFORT[surface]))]
    return {"surface": surface, "difficulty": difficulty, "effort": effort, "reason": why}


def escalate(plan, outcome):
    """Următorul plan după un rezultat nesatisfăcător, sau None dacă nu mai există pas."""
    status = outcome.get("status")
    if status == "completed":
        return None
    if status == "needs_code" and plan["surface"] != "codex":
        return {**plan, "surface": "codex", "effort": "high", "reason": "rezultatul cere cod"}
    if status == "needs_tools" and plan["surface"] in ("chat", "codex"):
        return {**plan, "surface": "work", "effort": "high", "reason": "rezultatul cere unelte"}
    level = EFFORTS.index(plan["effort"])
    if level < EFFORTS.index(MAX_EFFORT[plan["surface"]]):
        return {**plan, "effort": EFFORTS[level + 1], "reason": "raționament mai mare"}
    nxt = NEXT_SURFACE[plan["surface"]]
    if nxt is None:
        return None
    return {**plan, "surface": nxt, "effort": "high", "reason": "suprafață superioară"}


def run(task_id, task, backends, record=lambda entry: None, progress=lambda entry: None, clock=time.monotonic):
    """Execută cererea pe magistrală, cu escaladare. backends[surface](task_id, task, plan) -> outcome."""
    plan = route(task)
    hops = []
    for _ in range(MAX_HOPS):
        backend = backends.get(plan["surface"])
        progress({"task_id": task_id, "surface": plan["surface"], "effort": plan["effort"],
                  "reason": plan["reason"], "status": "running"})
        started = clock()
        if backend is None:
            outcome = {"status": "unavailable", "detail": "backend neconfigurat"}
        else:
            try:
                outcome = backend(task_id, task, dict(plan))
            except Exception as error:  # un backend căzut escaladează, nu oprește magistrala
                outcome = {"status": "failed", "detail": str(error)[:300]}
        hop = {"task_id": task_id, "surface": plan["surface"], "effort": plan["effort"],
               "reason": plan["reason"], "status": outcome.get("status"),
               "duration_ms": round((clock() - started) * 1000)}
        hops.append(hop)
        record(hop)
        if outcome.get("status") == "completed" and isinstance(outcome.get("output"), str) and outcome["output"].strip():
            return {"status": "completed", "output": outcome["output"], "final": plan, "hops": hops}
        plan = escalate(plan, outcome)
        if plan is None:
            break
    return {"status": "blocked", "output": None, "hops": hops,
            "detail": "nicio suprafață disponibilă nu a produs un rezultat"}
