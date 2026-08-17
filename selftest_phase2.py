"""Auto-teste da Fase 2 — deslocamento por rotas (US2).

Cobre:
  - entrada em rota move a pasta (rename atômico) e retira o personagem da origem
  - prerequisites em ordem: estáticos primeiro, contextuais por último; 1ª negação para (FR-019)
  - deslocamento negado ainda gera consequência ao ator (FR-014)
  - chegada preguiçosa migra ao destino; personagem nunca em dois lugares (FR-020, SC-004)
  - coexistência de dois personagens na mesma rota (FR-021)
  - movimento resolvido via apply_resolution (formato do Árbitro)

Roda sobre uma CÓPIA temporária do mundo. Uso:  python3 server/selftest_phase2.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")

sys.path.insert(0, str(SERVER_DIR))
import arbiter  # noqa: E402
import motor  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def write_route(route_id: str, body: str, prereqs_yaml: str) -> None:
    folder = motor.WORLD_DIR / "routes" / route_id
    folder.mkdir(parents=True, exist_ok=True)
    text = (
        "---\n"
        "type: route\n"
        f"id: {route_id}\n"
        f"name: {route_id}\n"
        "from: taverna-do-gancho\n"
        "to: forja-de-ferro\n"
        "travel_time_base: 5\n"
        "bidirectional: false\n"
        "prerequisites:\n"
        f"{prereqs_yaml}"
        "origin: teste\n"
        "---\n\n"
        f"{body}\n"
    )
    (folder / "route.md").write_text(text, encoding="utf-8")


def place_id(char_id: str) -> str:
    folder = motor.find_character_folder(char_id)
    place = folder.parent
    for fname in ("location.md", "route.md"):
        f = place / fname
        if f.exists():
            fm, _ = motor.read_doc(f)
            return fm.get("id")
    return "?"


def count_char_files(char_id: str) -> int:
    n = 0
    for path in motor.WORLD_DIR.rglob("character.md"):
        fm, _ = motor.read_doc(path)
        if fm.get("id") == char_id:
            n += 1
    return n


def backdate_arrival(char_id: str) -> None:
    folder = motor.find_character_folder(char_id)
    fm, body = motor.read_doc(folder / "character.md")
    fm["transit"]["arrive_ts"] = int(time.time()) - 100
    motor.write_doc(folder / "character.md", fm, body)


try:
    # rota estático-nega-primeiro: item (estático) falha antes do contextual
    write_route(
        "trilha-fechada",
        "Uma trilha bloqueada.",
        "  - id: precisa-chave\n"
        "    type: item\n"
        "    required: chave-de-ferro\n"
        "    deny_reason: DENY_ITEM\n"
        "  - id: precisa-coragem\n"
        "    type: status\n"
        "    field: mood\n"
        "    equals: corajoso\n"
        "    deny_reason: DENY_CONTEXTUAL\n",
    )
    # rota estático-passa-contextual-nega: STR ok, mood != corajoso
    write_route(
        "trilha-coragem",
        "Uma trilha que exige coragem.",
        "  - id: forca\n"
        "    type: attribute\n"
        "    attribute: STR\n"
        "    min: 5\n"
        "    deny_reason: DENY_ATTR\n"
        "  - id: precisa-coragem\n"
        "    type: status\n"
        "    field: mood\n"
        "    equals: corajoso\n"
        "    deny_reason: DENY_CONTEXTUAL\n",
    )

    # --- rotas disponíveis a partir da taverna (FR-018) -------------------- #
    ctx0 = motor.get_context("torvin-ferreiro")
    route_ids = {r["id"] for r in ctx0["routes"]}
    check("rotas: portao-lateral disponível da taverna", "portao-lateral" in route_ids)
    check("rotas: destino nomeado",
          any(r["destination_name"] == "Forja de Ferro" for r in ctx0["routes"]))

    # --- prerequisites: ordem e primeira negação (FR-019) ------------------ #
    d1 = motor.enter_route("torvin-ferreiro", "trilha-fechada")
    check("prereq: item estático nega primeiro", d1["moved"] is False and d1["reason"] == "DENY_ITEM",
          str(d1))
    d2 = motor.enter_route("torvin-ferreiro", "trilha-coragem")
    check("prereq: estático passa, contextual nega por último",
          d2["moved"] is False and d2["reason"] == "DENY_CONTEXTUAL", str(d2))
    check("prereq: negação não moveu o ator", place_id("torvin-ferreiro") == "taverna-do-gancho")

    # --- deslocamento negado via apply_resolution gera consequência (FR-014) --- #
    out_deny = motor.apply_resolution(
        "torvin-ferreiro", {"narrative_hint": "", "movement": {"enter_route": "trilha-fechada"}})
    acted = motor.find_character_folder("torvin-ferreiro")
    fm_deny, _ = motor.read_doc(acted / "character.md")
    check("negado: ação registra a tentativa (FR-014)",
          "tentou partir" in (fm_deny.get("status", {}).get("action") or ""),
          fm_deny.get("status", {}).get("action"))
    check("negado: ator continua na taverna", place_id("torvin-ferreiro") == "taverna-do-gancho")

    # --- entrada via apply_resolution (formato do Árbitro) ----------------- #
    norm = arbiter.normalize(json.dumps(
        {"narrative_hint": "", "movement": {"enter_route": "portao-lateral"}, "mutations": []}))
    check("normalize: movement parseado", norm["movement"] == {"enter_route": "portao-lateral"})
    out_move = motor.apply_resolution("torvin-ferreiro", norm)
    check("mover: apply_resolution moveu",
          any(m.get("movement") == "portao-lateral" for m in out_move["applied"]))
    check("mover: torvin agora na rota", place_id("torvin-ferreiro") == "portao-lateral")
    ctx_t = motor.get_context("torvin-ferreiro")
    check("mover: contexto marca em trânsito", ctx_t["in_transit"] is True)
    check("mover: lugar é a rota", ctx_t["location"]["name"] == "Portão Lateral")
    check("mover: nunca em dois lugares (1 arquivo)", count_char_files("torvin-ferreiro") == 1)

    # elga não deve mais ver torvin na taverna
    ctx_e = motor.get_context("elga-taverneira")
    check("mover: torvin saiu da taverna",
          all(c["id"] != "torvin-ferreiro" for c in ctx_e["characters_present"]))

    # --- coexistência na rota (FR-021) ------------------------------------- #
    motor.enter_route("elga-taverneira", "portao-lateral")
    ctx_t2 = motor.get_context("torvin-ferreiro")
    present_ids = {c["id"] for c in ctx_t2["characters_present"]}
    check("coexistência: torvin e elga juntos na rota",
          {"torvin-ferreiro", "elga-taverneira"} <= present_ids, str(present_ids))

    # --- chegada preguiçosa (FR-020, SC-004) ------------------------------- #
    backdate_arrival("torvin-ferreiro")
    backdate_arrival("elga-taverneira")
    ctx_arr = motor.get_context("torvin-ferreiro")  # dispara lazy_evaluate
    check("chegada: torvin no destino", place_id("torvin-ferreiro") == "forja-de-ferro")
    check("chegada: contexto não está mais em trânsito", ctx_arr["in_transit"] is False)
    fm_arr, _ = motor.read_doc(motor.find_character_folder("torvin-ferreiro") / "character.md")
    check("chegada: trânsito removido do arquivo", "transit" not in fm_arr)
    check("chegada: elga também chegou", place_id("elga-taverneira") == "forja-de-ferro")
    check("chegada: torvin em 1 lugar só", count_char_files("torvin-ferreiro") == 1)
    present_forja = {c["id"] for c in ctx_arr["characters_present"]}
    check("chegada: ambos presentes na forja",
          {"torvin-ferreiro", "elga-taverneira"} <= present_forja, str(present_forja))

finally:
    shutil.rmtree(_tmp, ignore_errors=True)

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
    sys.exit(1)
print("todos os checks da Fase 2 passaram.")
