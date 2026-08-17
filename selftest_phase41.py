"""Auto-teste da Fase 41 — Polish do item 038 (T080/T081): o mecanismo genérico.

Prova, sem LLM real, as garantias que sustentam "acrescentar coisa toca um lugar":
  - T080 (OBSERVER): uma reação transversal NOVA (`@fatos.reacao(kinds="*")`)
    dispara para todo ato, sem tocar em NENHUMA tool — open/closed do barramento.
  - T081: uma tool declarada por DADO é oferecida (FACE) e recusa corrigível com
    `validos`; a reação-fato GRAVA a memória do ator; o batch-path aplica na ORDEM
    DA RESOLUÇÃO (sem `_TURN_STEPS`), preservando o bracket de contêiner.

Roda sobre uma cópia temporária do mundo de teste. Uso: python3 server/selftest_phase41.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-p41-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import arbiter  # noqa: E402
import motor  # noqa: E402
from motor import fatos  # noqa: E402

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


TOR = "torvin-ferreiro"

# ---- T080: OBSERVER — reação transversal nova, zero toque em tool ----------------
observados: list[str] = []


@fatos.reacao(kinds="*")
def _observer(fato, actor_folder, present):
    observados.append(fato.kind)
    return []   # não grava nada; só observa (prova o open/closed do barramento)


# um item ao alcance do ator para exercitar o pipeline
ctx = motor.get_context(TOR)
tools = {t["name"]: t for t in arbiter.build_tools(ctx)}
take_enum = tools.get("take", {}).get("parameters", {}).get("properties", {}) \
    .get("item", {}).get("enum", [])
check("T081: a tool declarada `take` é oferecida (FACE derivada)", bool(take_enum))
item = take_enum[0]

out = motor.apply_resolution(TOR, {"item_transfers": [{"item": item, "to": TOR}]},
                             ensure_action=False)
check("T080: Observer (kinds='*') disparou sem tocar nenhuma tool",
      "item_transfers" in observados, str(observados))

# ---- T081: a reação-fato GRAVA a memória do ator (caminho legado) ----------------
mem_ev = [m for m in (out.get("memories_created") or [])
          if isinstance(m, dict) and m.get("event") in ("transfer", "emprestimo")]
check("T081: a reação react_actor_memory gravou a memória do ato (transfer)",
      bool(mem_ev), str(out.get("memories_created")))

# ---- T081: recusa CORRIGÍVEL com validos (tool declarada) ------------------------
idx = arbiter._scene_index(motor.get_context(TOR))
capt = {}


def _loop(system, user, tools_, execute, max_calls):
    r, _ = execute("take", {"item": "item-que-nao-existe-xyz"})
    capt["take"] = r
    execute("narrate", {"narrative_hint": "x"})
    return {"stopped": "narrate", "text": None, "calls": 2}


arbiter.resolve_with_tools({"action": "pega algo", "target": None},
                           motor.get_context(TOR), _loop)
r = capt.get("take") or {}
check("T081: item inválido → recusa corrigível com `validos`",
      r.get("ok") is False and bool(r.get("validos")), str(r)[:200])

# ---- T081: batch-path aplica na ORDEM DA RESOLUÇÃO (bracket de contêiner) --------
# abrir um contêiner E guardar dentro no MESMO lote, com item_transfers ANTES de
# lock_ops na ordem do dict: o bracket (open primeiro) tem de vencer a ordem escrita.
_alvo_cont = None
for iid, e in idx["items"].items():
    if e.get("container") and (e["container"] or {}).get("fechado") \
            and e["porter"] in (None, idx["actor_id"]):
        _alvo_cont = iid
        break
if _alvo_cont:
    guardavel = next((i for i, e in idx["items"].items()
                      if not e.get("container") and e["porter"] == TOR), None)
    if guardavel:
        ob = motor.apply_resolution(TOR, {
            "item_transfers": [{"item": guardavel, "to": _alvo_cont, "mode": "stow"}],
            "lock_ops": [{"op": "open", "target": _alvo_cont}],
        }, ensure_action=False)
        # o open bracketou: a guarda entrou (aplicada) apesar de item_transfers vir antes
        check("T081: bracket de contêiner sobrevive à ordem de inserção (open primeiro)",
              bool(ob.get("lock_ops_applied")) and bool(ob.get("item_transfers_applied")),
              str({"lock": ob.get("lock_ops_applied"),
                   "transf": ob.get("item_transfers_applied")}))
    else:
        check("T081: bracket de contêiner (sem item guardável no fixture — pulado)", True)
else:
    check("T081: bracket de contêiner (sem contêiner fechado no fixture — pulado)", True)

# ---- T081/SC-003: caminho GENÉRICO de memória — tool nova grava SEM editar reação -
# Publica um FATO sintético de um canal INÉDITO (não legado) com o contrato de
# memória embutido no applied; a reação react_actor_memory (genérica) o grava via o
# sink `remember`, sem canal hardcoded nem entrada em tabela. É a prova do SC-003
# para uma tool futura, sem precisar de nenhuma tool-fixture no repositório.
_af = motor.find_character_folder(TOR)
_present, _o, _i = motor.io._scene_entities(_af.parent)
_criadas = fatos.publish(
    fatos.Fato(kind="canal_inedito_ops", actor=TOR, canal="canal_inedito_ops",
               status="applied",
               payload={"memory": {"content": "um ato de um canal jamais visto",
                                   "intensity": "small", "involved": [],
                                   "event": "demo038"}}),
    _af, _present)
check("SC-003: contrato de memória no fato grava via react_actor_memory (canal inédito)",
      any(isinstance(m, dict) and m.get("event") == "demo038" for m in _criadas),
      str(_criadas))

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S):", ", ".join(FAILS))
    sys.exit(1)
print("Fase 41 (Polish 038 — Observer + regressões do genérico) OK.")
