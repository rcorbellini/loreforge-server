"""Auto-teste da Fase 4 — autoria editorial por arquivos .md (US4).

Cobre:
  - mundo-semente é íntegro (validate_world == [])
  - character válido criado à mão passa a existir (cenário US4 #1)
  - route inválida (sem 'from') é rejeitada com motivo legível e não corrompe o mundo (US4 #2)
  - character inválido é ignorado no jogo e não se pode guiá-lo, com motivo (FR-010, SC-006)
  - mover a PASTA do personagem reloca-o com itens e memórias (cenário US4 #3)

Roda sobre uma CÓPIA temporária do mundo. Uso:  python3 server/selftest_phase4.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")

sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import validator  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def author(relpath: str, text: str) -> None:
    p = motor.WORLD_DIR / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def problem_paths():
    return {p["path"] for p in motor.validate_world()}


try:
    # --- mundo-semente é íntegro ------------------------------------------- #
    check("mundo-semente sem problemas de schema", motor.validate_world() == [],
          str(motor.validate_world()))

    # --- US4 #1: character válido criado à mão passa a existir -------------- #
    author("forja-de-ferro/aprendiz-goro/character.md",
           "---\n"
           "type: character\n"
           "id: aprendiz-goro\n"
           "name: Goro, o Aprendiz\n"
           "controlled_by: player_local\n"
           "attributes:\n  STR: 12\n  DEX: 13\n  CON: 12\n  INT: 10\n  WIS: 9\n  CHA: 11\n"
           "skills:\n  ferraria: 2\n"
           "status:\n  hp: 80\n  hp_max: 80\n  hunger: saciado\n  fatigue: baixo\n"
           "  action: martelar uma ferradura\n  mood: concentrado\n  conditions: []\n"
           "origin: editorial\n"
           "---\n\nGoro aprende o ofício com Torvin há dois anos.\n")
    ids = {c["id"] for c in motor.list_characters()}
    check("US4#1: novo character aparece no seletor", "aprendiz-goro" in ids)
    ctx_goro = motor.get_context("aprendiz-goro")
    check("US4#1: novo character na location certa",
          ctx_goro["location"]["id"] == "forja-de-ferro")
    check("US4#1: mundo continua íntegro", motor.validate_world() == [])

    # --- US4 #2: route inválida (sem 'from') rejeitada com motivo ----------- #
    author("routes/rota-quebrada/route.md",
           "---\n"
           "type: route\n"
           "id: rota-quebrada\n"
           "name: Rota Quebrada\n"
           "to: forja-de-ferro\n"
           "travel_time_base: 10\n"
           "bidirectional: false\n"
           "prerequisites: []\n"
           "origin: teste\n"
           "---\n\nUma rota mal formada.\n")
    probs = motor.validate_world()
    quebrada = [p for p in probs if "rota-quebrada" in p["path"]]
    check("US4#2: route inválida é reportada", len(quebrada) == 1, str(probs))
    check("US4#2: motivo legível cita o campo 'from'",
          bool(quebrada) and any("from" in e for e in quebrada[0]["errors"]),
          str(quebrada))
    # não corrompe: rota quebrada não aparece como saída da taverna
    taverna_routes = {r["id"] for r in motor.get_context("torvin-ferreiro")["routes"]}
    check("US4#2: rota inválida fora das saídas", "rota-quebrada" not in taverna_routes)
    check("US4#2: rota válida segue disponível", "portao-lateral" in taverna_routes)

    # --- FR-010: character inválido é ignorado e não guiável --------------- #
    author("taverna-do-gancho/quebrado/character.md",
           "---\n"
           "type: character\n"
           "id: quebrado\n"
           "name: Personagem Quebrado\n"
           "controlled_by: player_local\n"
           "skills: {}\n"
           "status: {}\n"
           "origin: teste\n"
           "---\n\nFaltam os atributos.\n")
    ids2 = {c["id"] for c in motor.list_characters()}
    check("FR-010: character inválido fora do seletor", "quebrado" not in ids2)
    present = {c["id"] for c in motor.get_context("torvin-ferreiro")["characters_present"]}
    check("FR-010: character inválido não aparece na cena", "quebrado" not in present)
    try:
        motor.find_character_folder("quebrado")
        check("FR-010: guiar inválido levanta erro legível", False, "não levantou")
    except motor.MotorError as exc:
        check("FR-010: guiar inválido levanta erro legível", "inválido" in str(exc), str(exc))

    # --- US4 #3: mover a PASTA reloca personagem com itens e memórias ------- #
    # Torvin tem item (bolsa->frasco). Damos a ele também uma memória, e movemos a pasta.
    author("taverna-do-gancho/torvin-ferreiro/memories/mem-teste-mudanca.md",
           "---\ntype: memory\nid: mem-teste-mudanca\ntimestamp_start: 1700000000\n"
           "timestamp_end: 4102444800\nintensity: medium\nstate: active\n"
           "origin: teste\n---\n\nLembro do dia em que mudei de lugar.\n")
    origem = motor.find_character_folder("torvin-ferreiro")
    destino = (motor.WORLD_DIR / "forja-de-ferro" / "torvin-ferreiro")
    shutil.move(str(origem), str(destino))

    ctx_t = motor.get_context("torvin-ferreiro")
    check("US4#3: personagem relocado para a nova location",
          ctx_t["location"]["id"] == "forja-de-ferro")
    inv = motor.get_inventory("torvin-ferreiro")
    bag = inv["children"][0] if inv["children"] else {}
    check("US4#3: itens vieram junto (bolsa+frasco)",
          bag.get("id") == "bolsa-de-couro" and bool(bag.get("children")))
    # lê as memórias da pasta SEM o filtro de evocação da cena: o que se testa
    # aqui é que mover a pasta carried_item_ids as memórias junto, não o corte de
    # contexto da spec 013 (esta é de 2023, latente e não envolve ninguém
    # presente — por desenho, não desce ao client).
    mem_ids = {m["id"] for m in motor.get_active_memories(destino)}
    check("US4#3: memórias vieram junto", "mem-teste-mudanca" in mem_ids)
    check("US4#3: mundo íntegro após mover (só as inválidas de teste restam)",
          problem_paths() == {"routes/rota-quebrada/route.md",
                              "taverna-do-gancho/quebrado/character.md"})

finally:
    shutil.rmtree(_tmp, ignore_errors=True)

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
    sys.exit(1)
print("todos os checks da Fase 4 passaram.")
