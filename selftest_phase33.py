"""Auto-teste da Fase 33 — Duração real de dormir/descansar (spec 031,
US1+US2+US3).

Sem nenhum modelo/LLM — exercita o Motor direto (`motor.apply_resolution`)
e o manifest (`arbiter.build_tools`). Cobre:

  - US1: `dormir` vira alternador (iniciar/acordar); a fadiga recuperada é
    proporcional ao tempo real decorrido entre as duas chamadas, com teto
    de recuperação plena em 8h reais (`fisica._TETO_SONO_PLENO_S`)
  - US2: enquanto descansando, o manifest só oferece `dormir`, E cada
    executor mutador recusa qualquer outra tool com os PRÓPRIOS meios —
    inclusive quando chamado DIRETO, sem passar por `arbiter.py`
  - US3: compromisso pendente (`prometer`, spec 027) só intensifica ao
    ACORDAR, e só se a fração recuperada foi >= 50% ("sono de qualidade")

Uso:  python3 server/selftest_phase33.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"
TOR, ELGA = "torvin-ferreiro", "elga-taverneira"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def fadiga_de(cid: str) -> tuple[int, int]:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return motor.ensure_fatigue(fm)


def _com_fadiga_no_arquivo(cid: str, fadiga: int):
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    teto = motor.fatigue_max(fm)
    status = dict(fm.get("status") or {})
    status["fatigue"] = fadiga
    status["fatigue_max"] = teto
    status.pop("descansando_desde", None)
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def _descansando_desde(cid: str):
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return (fm.get("status") or {}).get("descansando_desde")


def _backdate_descansando_desde(cid: str, segundos_atras: float):
    """Simula tempo real decorrido sem esperar de verdade — mesmo truque
    que testes de chegada de viagem já usam (ajustar o timestamp gravado
    pro passado, em vez de dormir de verdade no teste)."""
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status["descansando_desde"] = time.time() - segundos_atras
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def _mk_char(cid: str, name: str, con: int = 10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: {con}\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")


# =========================================================================== #
# US1 — recuperação proporcional ao tempo real decorrido
# =========================================================================== #

_com_fadiga_no_arquivo(TOR, 100)  # Torvin CON 14 -> teto 120

# 1) primeira chamada de dormir: só INICIA — fadiga intacta, timestamp gravado
fadiga_antes_iniciar, teto_tor = fadiga_de(TOR)
motor.apply_resolution(TOR, {"rest_ops": [{"op": "sleep"}]})
fadiga_apos_iniciar, _ = fadiga_de(TOR)
check("1ª chamada de dormir NÃO muda a fadiga (é o iniciar)",
      fadiga_apos_iniciar == fadiga_antes_iniciar,
      f"antes={fadiga_antes_iniciar} depois={fadiga_apos_iniciar}")
check("1ª chamada de dormir grava status.descansando_desde",
      _descansando_desde(TOR) is not None)

# 2) segunda chamada, pouco tempo depois: recupera só uma FRAÇÃO pequena
_backdate_descansando_desde(TOR, 60)  # 60s reais "decorridos"
motor.apply_resolution(TOR, {"rest_ops": [{"op": "wake_up"}]})
fadiga_apos_soneca, _ = fadiga_de(TOR)
fracao_esperada = motor.fisica.rest_fraction(60)
recuperada_esperada = round(fracao_esperada * teto_tor)
check("2ª chamada (soneca curta) recupera só uma fração pequena",
      fadiga_apos_soneca == max(0, fadiga_antes_iniciar - recuperada_esperada),
      f"obtido={fadiga_apos_soneca} esperado={max(0, fadiga_antes_iniciar - recuperada_esperada)}")
check("soneca curta apaga descansando_desde (acordou)",
      _descansando_desde(TOR) is None)

# 3) terceiro ciclo: descanso completo (>= 8h) recupera fadiga por completo
motor.apply_resolution(TOR, {"rest_ops": [{"op": "sleep"}]})  # inicia de novo
_backdate_descansando_desde(TOR, 8 * 3600 + 60)  # 8h+ atrás
motor.apply_resolution(TOR, {"rest_ops": [{"op": "wake_up"}]})  # acorda
fadiga_apos_noite_inteira, _ = fadiga_de(TOR)
check("descanso >= 8h recupera fadiga por completo",
      fadiga_apos_noite_inteira == 0, str(fadiga_apos_noite_inteira))

# =========================================================================== #
# US2 — trava enquanto descansando: manifest cosmético + validação em CADA
# executor (nunca um guard central — research.md §3)
# =========================================================================== #

_com_fadiga_no_arquivo(TOR, 50)


def _scripted_loop(script, capturados):
    def loop_fn(system, user, tools, execute, max_calls):
        calls = 0
        for name, args in script:
            calls += 1
            result, done = execute(name, args)
            capturados.append((name, result))
            if done or calls >= max_calls:
                return {"stopped": "narrate", "text": None, "calls": calls}
        return {"stopped": "limit", "text": None, "calls": calls}
    return loop_fn


# T009 — manifest, com o ator descansando, só oferece a capacidade de ACORDAR
# (item 50: era `sleep` alternador; agora é `wake_up`, capacidade própria)
motor.apply_resolution(TOR, {"rest_ops": [{"op": "sleep"}]})  # inicia (TOR descansando)
ctx_dormindo = motor.get_context(TOR)
tools_dormindo = arbiter.build_tools(ctx_dormindo)
check("US2: manifest com ator descansando tem EXATAMENTE 1 tool",
      len(tools_dormindo) == 1, str([t["name"] for t in tools_dormindo]))
check("US2: a única tool do manifest é 'wake_up'",
      tools_dormindo and tools_dormindo[0]["name"] == "wake_up",
      str([t["name"] for t in tools_dormindo]))

# T010 — mesmo que o Árbitro tente outra tool (fora do manifest, por
# imprevisibilidade — Princípio X), o dispatch de arbiter.py recusa
intent_take = {"action": "pega a agulha", "target": "agulha-de-ferro",
              "utterance": None, "movement": None, "note": ""}
capturados: list = []
fadiga_antes_take, _ = fadiga_de(TOR)
arbiter.resolve_with_tools(intent_take, ctx_dormindo, _scripted_loop([
    ("take", {"item": "agulha-de-ferro"}),
    ("narrate", {"narrative_hint": "tenta pegar algo"}),
], capturados))
take_result = next((r for n, r in capturados if n == "take"), None)
check("US2: 'take' enquanto descansando é recusado (via arbiter)",
      take_result is not None and take_result.get("ok") is False,
      str(take_result))
fadiga_depois_take, _ = fadiga_de(TOR)
check("US2: nenhuma mutação aconteceu (fadiga intacta após recusa)",
      fadiga_depois_take == fadiga_antes_take)

# T011 — A PROVA DE ATOMICIDADE: chamar o EXECUTOR direto, sem passar por
# arbiter.py NEM por turno.apply_op — a validação precisa estar DENTRO do
# executor pra sobreviver a isto (research.md §3, as duas versões
# descartadas antes desta).
tor_folder = motor.find_character_folder(TOR)
applied_direto, rejected_direto = motor.itens._apply_item_transfers(
    TOR, tor_folder, {"item_transfers": [{"item": "moeda-de-cobre", "to": TOR}]})
check("US2 (atomicidade): executor chamado DIRETO recusa por conta própria",
      any(r.get("regra") == "descansando" for r in rejected_direto),
      str(rejected_direto))
check("US2 (atomicidade): NENHUM applied quando chamado direto descansando",
      not applied_direto, str(applied_direto))

# acorda TOR pra não vazar estado pros testes seguintes
_backdate_descansando_desde(TOR, 8 * 3600 + 60)
motor.apply_resolution(TOR, {"rest_ops": [{"op": "wake_up"}]})

# =========================================================================== #
# US3 — só sono de qualidade (>= 50% recuperado) intensifica compromisso
# pendente (Frente D, spec 030) — e só ao ACORDAR, nunca ao iniciar
# =========================================================================== #

_mk_char("credor-p33", "Credor")
_mk_char("devedor-p33", "Devedor")
CREDOR33, DEVEDOR33 = "credor-p33", "devedor-p33"

motor.apply_resolution(DEVEDOR33, {"promise_ops": [
    {"para": CREDOR33, "expectativa": "que eu pague o que devo"}]})
devedor33_folder = motor.find_character_folder(DEVEDOR33)
int33_path = sorted((devedor33_folder / "intentions").glob("*.md"))[0]
int33_fm, _ = motor.read_doc(int33_path)
mem_id_compromisso33 = int33_fm.get("memoria_id")
mem33_path = devedor33_folder / "memories" / f"{mem_id_compromisso33}.md"


def _intensidade_p33():
    fm, _ = motor.read_doc(mem33_path)
    return fm.get("intensity")


check("US3: memória do compromisso nasce 'medium' (precondição)",
      _intensidade_p33() == "medium", str(_intensidade_p33()))

# T026 — descanso curto (fração < 50%) NÃO intensifica
motor.apply_resolution(DEVEDOR33, {"rest_ops": [{"op": "sleep"}]})  # inicia
_backdate_descansando_desde(DEVEDOR33, 60)  # 60s reais: fração ínfima
motor.apply_resolution(DEVEDOR33, {"rest_ops": [{"op": "wake_up"}]})  # acorda
check("US3: descanso curto (<50%) NÃO intensifica o compromisso",
      _intensidade_p33() == "medium", str(_intensidade_p33()))

# T027 — descanso de qualidade (>= 50%, ou seja >= 4h) intensifica
motor.apply_resolution(DEVEDOR33, {"rest_ops": [{"op": "sleep"}]})  # inicia
_backdate_descansando_desde(DEVEDOR33, 4 * 3600 + 60)  # >= metade do teto
motor.apply_resolution(DEVEDOR33, {"rest_ops": [{"op": "wake_up"}]})  # acorda
check("US3: descanso de qualidade (>=50%) intensifica medium -> large",
      _intensidade_p33() == "large", str(_intensidade_p33()))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 33 (Duração real de dormir/descansar, spec 031) OK.")
