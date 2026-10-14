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


CODE_PROFILES = {"dots_reparator", "dots_programare", "dots_teste_reparatii", "dots_loguri", "dots_lansare",
                 "dots_defecte_git", "dots_cautare_cod", "dots_harta_sectiuni_cod", "dots_context_cod",
                 "dots_editare_fisiere", "dots_extrage_sarcini_git", "dots_evalueaza_reparari_teste_ascunse",
                 "dots_determinism_date", "dots_analiza_traiectorii", "dots_verificare_logici_temporare"}


def route(task, profiles=None):
    """Alege suprafața, dificultatea (1..4), efortul și profilul DOTS pentru o cerere."""
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
    profile = None
    if profiles is not None and len(profiles):
        profile, pwhy, _ = profiles.pick(task)
        if profile:
            why += "; profil " + profile + " (" + pwhy + ")"
            if profile in CODE_PROFILES and surface == "chat":
                surface = "codex"
    effort = EFFORTS[min(difficulty - 1, EFFORTS.index(MAX_EFFORT[surface]))]
    plan = {"surface": surface, "difficulty": difficulty, "effort": effort, "reason": why}
    if profile:
        plan["profile"] = profile
    return plan


def escalate(plan, outcome):
    """Următorul plan după un rezultat nesatisfăcător, sau None dacă nu mai există pas."""
    status = outcome.get("status")
    if status == "completed":
        return None
    if status == "needs_code" and plan["surface"] != "codex":
        return {**plan, "surface": "codex", "effort": "high", "reason": "rezultatul cere cod"}
    if status == "needs_tools" and plan["surface"] in ("chat", "codex"):
        return {**plan, "surface": "work", "effort": "high", "reason": "rezultatul cere unelte"}
    # Economic: raționament mai mare (mai scump) doar când răspunsul a fost insuficient.
    # Un eșec tehnic (cotă, login, model, canal indisponibil) nu se repetă mai scump pe același canal.
    level = EFFORTS.index(plan["effort"])
    if status == "insufficient" and level < EFFORTS.index(MAX_EFFORT[plan["surface"]]):
        return {**plan, "effort": EFFORTS[level + 1], "reason": "raționament mai mare"}
    nxt = NEXT_SURFACE[plan["surface"]]
    if nxt is None:
        return None
    # Canalul următor pornește de la nivelul economic al cererii (după dificultate), nu direct de la maxim.
    base = EFFORTS[min(plan.get("difficulty", 1) - 1, EFFORTS.index(MAX_EFFORT[nxt]))]
    effort = base if status in ("failed", "unavailable") else max(base, plan["effort"], key=EFFORTS.index)
    effort = EFFORTS[min(EFFORTS.index(effort), EFFORTS.index(MAX_EFFORT[nxt]))]
    return {**plan, "surface": nxt, "effort": effort, "reason": "suprafață superioară"}


def run(task_id, task, backends, record=lambda entry: None, progress=lambda entry: None, clock=time.monotonic, profiles=None):
    """Execută cererea pe magistrală, cu escaladare. backends[surface](task_id, task, plan) -> outcome."""
    plan = route(task, profiles)
    if plan.get("profile"):
        # Cererea pleacă spre backend cu instrucțiunile profilului DOTS ales (faza work).
        _, _, clean = profiles.pick(task)
        task = profiles.compose(plan["profile"], clean, task_id)
    hops = []
    for _ in range(MAX_HOPS):
        backend = backends.get(plan["surface"])
        progress({"task_id": task_id, "surface": plan["surface"], "effort": plan["effort"],
                  "reason": plan["reason"], "status": "running", "profile": plan.get("profile")})
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
        if plan.get("profile"):
            hop["profile"] = plan["profile"]
        if outcome.get("status") != "completed" and outcome.get("detail"):
            hop["detail"] = str(outcome["detail"])[-300:]  # motivul real al eșecului, vizibil în monitor
        hops.append(hop)
        record(hop)
        if outcome.get("status") == "completed" and isinstance(outcome.get("output"), str) and outcome["output"].strip():
            return {"status": "completed", "output": outcome["output"], "final": plan, "hops": hops}
        plan = escalate(plan, outcome)
        if plan is None:
            break
    return {"status": "blocked", "output": None, "hops": hops,
            "detail": "nicio suprafață disponibilă nu a produs un rezultat"}
