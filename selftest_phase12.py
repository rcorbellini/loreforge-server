"""Auto-teste da Fase 12 — Velocidade de Viagem por Item Vestido (spec 009).

Feature determinística: nenhuma rolagem envolvida.

Cobre:
  - unidades de speed_multiplier_of: sem item, um item, vários (MAIOR, nunca
    produto), guardado, na mão, valores inertes (≤ 1, texto, booleano)
  - núcleo (SC-001): rota base 9 + capa 3x ⇒ 3
  - ordem (FR-004): fadiga alta atrasa PRIMEIRO, divisão depois
  - arredondamento: round() bancário (9/2 ⇒ 4, não 5)
  - piso (SC-005): nunca 0 quando havia tempo; base 0 continua 0
  - só o VESTIDO conta (SC-003) e zero regressão sem itens (SC-004)
  - persuadido viaja com os PRÓPRIOS itens (SC-006)
  - fotografia na partida (FR-007) e pureza narrativa (SC-007)

Cenário: taverna → forja pela rota portao-lateral (travel_time_base 20);
bota-do-mensageiro (2x, pes) e capa-do-vento (3x, costas) soltas na taverna.

Uso:  python3 server/selftest_phase12.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402
import motor  # noqa: E402

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
ROTA, TAVERNA_ID, FORJA_ID = "portao-lateral", "taverna-do-gancho", "forja-de-ferro"
BOTA, CAPA = "bota-do-mensageiro", "capa-do-vento"
MOCHILA = "mochila-de-couro"
BASE = 20  # travel_time_base da rota na fixture


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def char_folder(cid) -> Path:
    return motor.find_character_folder(cid)


def set_status(cid, **fields) -> None:
    folder = char_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status.update(fields)
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def set_route_base(valor: int) -> None:
    folder, fm, body = motor.find_route(ROTA)
    fm["travel_time_base"] = valor
    motor.write_doc(folder / "route.md", fm, body)


def item_folder(item_id) -> Path:
    return motor.find_entity(item_id)[0].parent


def wear(cid, item_id, slot=None) -> None:
    """Veste o item no personagem (montagem de cenário)."""
    folder = item_folder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    destino = slot or (fm.get("wearable") or {}).get("slot")
    state = dict(fm.get("state") or {})
    state["slot"] = destino
    fm["state"] = state
    motor.write_doc(folder / "item.md", fm, body)
    dest = char_folder(cid) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def stow_in(item_id, container_id) -> None:
    """Guarda o item dentro de um contêiner (sem slot: está guardado)."""
    folder = item_folder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    fm.pop("state", None)
    motor.write_doc(folder / "item.md", fm, body)
    os.replace(folder, item_folder(container_id) / folder.name)


def drop(item_id) -> None:
    """Devolve o item ao chão da taverna, sem slot."""
    folder = item_folder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    fm.pop("state", None)
    motor.write_doc(folder / "item.md", fm, body)
    dest = motor.WORLD_DIR / TAVERNA_ID / folder.name
    if folder != dest:
        os.replace(folder, dest)


def set_multiplier(item_id, valor) -> None:
    folder = item_folder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    wearable = dict(fm.get("wearable") or {})
    if valor is None:
        wearable.pop("speed_multiplier", None)
    else:
        wearable["speed_multiplier"] = valor
    fm["wearable"] = wearable
    motor.write_doc(folder / "item.md", fm, body)


def travel_of(cid) -> int:
    """Entra na rota, lê o tempo aplicado e devolve o personagem à taverna."""
    result = motor.enter_route(cid, ROTA)
    assert result.get("moved"), result
    tempo = result["travel_time"]
    bring_back(cid)
    return tempo


def bring_back(cid) -> None:
    child = motor.WORLD_DIR / "routes" / ROTA / cid
    fm, body = motor.read_doc(child / "character.md")
    fm.pop("transit", None)
    motor.write_doc(child / "character.md", fm, body)
    os.replace(child, motor.WORLD_DIR / TAVERNA_ID / cid)


def res(**parts):
    base = {"narrative_hint": "convence a partir", "movement": None,
            "mutations": [], "item_transfers": [], "equip_ops": [],
            "lock_ops": [], "persuade_ops": [], "attack_ops": [], "memories": []}
    base.update(parts)
    return base


try:
    set_route_base(BASE)

    # --- unidades de speed_multiplier_of ------------------------------------- #
    check("sem item vestido: multiplicador 1.0",
          motor.speed_multiplier_of(char_folder(TORVIN)) == 1.0)

    wear(TORVIN, CAPA)
    check("capa 3x vestida: multiplicador 3.0",
          motor.speed_multiplier_of(char_folder(TORVIN)) == 3.0)

    wear(TORVIN, BOTA)
    check("FR-003: bota 2x + capa 3x ⇒ 3.0 (MAIOR, nunca 6.0)",
          motor.speed_multiplier_of(char_folder(TORVIN)) == 3.0,
          str(motor.speed_multiplier_of(char_folder(TORVIN))))

    drop(CAPA)
    check("retirada a capa, resta a bota ⇒ 2.0",
          motor.speed_multiplier_of(char_folder(TORVIN)) == 2.0)

    # guardado e na mão não contam (FR-002)
    wear(TORVIN, MOCHILA)
    wear(TORVIN, CAPA)
    stow_in(CAPA, MOCHILA)
    check("SC-003: capa GUARDADA na mochila não acelera ⇒ 2.0 (só a bota)",
          motor.speed_multiplier_of(char_folder(TORVIN)) == 2.0)

    wear(TORVIN, CAPA, slot=motor.HAND_SLOT)
    check("SC-003: capa NA MÃO não acelera ⇒ 2.0 (só a bota)",
          motor.speed_multiplier_of(char_folder(TORVIN)) == 2.0)

    # valores inertes (FR-006). Só números positivos existem no mundo: texto,
    # booleano, zero e negativo são barrados pelo validador na ESCRITA (checado na
    # seção do validador, no fim) — por isso aqui só cabem 1 e 0.5.
    wear(TORVIN, CAPA)
    for valor in (1, 0.5):
        set_multiplier(CAPA, valor)
        check(f"FR-006: speed_multiplier {valor} é inerte ⇒ 2.0 (só a bota)",
              motor.speed_multiplier_of(char_folder(TORVIN)) == 2.0,
              str(motor.speed_multiplier_of(char_folder(TORVIN))))
    set_multiplier(CAPA, 3)

    # defesa em profundidade: um .md editado à mão FORA do validador (o autor mexe
    # no arquivo direto) não pode derrubar o cálculo da viagem
    capa_md = item_folder(CAPA) / "item.md"
    capa_md.write_text(
        "---\ntype: item\nid: capa-do-vento\nname: Capa do Vento\n"
        "size: P\nweight_kg: 1\nwearable:\n  slot: costas\n"
        "  speed_multiplier: rapido\norigin: editorial\nstate:\n  slot: costas\n"
        "---\n\nUm tecido leve demais para o próprio tamanho.\n",
        encoding="utf-8")
    check("leitor tolera valor não-numérico escrito à mão ⇒ 2.0 (só a bota)",
          motor.speed_multiplier_of(char_folder(TORVIN)) == 2.0,
          str(motor.speed_multiplier_of(char_folder(TORVIN))))
    set_multiplier(CAPA, 3)

    # vestível SEM o campo não acelera
    drop(CAPA); drop(BOTA); drop(MOCHILA)
    wear(TORVIN, "calca-de-la")
    check("vestível sem speed_multiplier não acelera ⇒ 1.0",
          motor.speed_multiplier_of(char_folder(TORVIN)) == 1.0)
    drop("calca-de-la")

    # --- núcleo: o tempo de viagem (US1) -------------------------------------- #
    set_route_base(9)
    check("SC-004: sem item, tempo = base (zero regressão)", travel_of(TORVIN) == 9)

    wear(TORVIN, CAPA)
    check("SC-001: rota base 9 + capa 3x ⇒ 3", travel_of(TORVIN) == 3)

    drop(CAPA); wear(TORVIN, BOTA)
    check("arredondamento: 9 / 2 = 4.5 ⇒ 4 (round bancário, não 5)",
          travel_of(TORVIN) == 4, str(travel_of(TORVIN)))

    # ordem (FR-004): fadiga alta atrasa PRIMEIRO (+50%), divisão depois
    #
    # A FADIGA AQUI É NÚMERO, e essa mudança tem história (2026-08-12). Este
    # teste passava `fatigue="alto"` — o formato de RÓTULO que a spec 030
    # aposentou —, e `_travel_modifier` comparava com essa string. Resultado: a
    # regra funcionava NO TESTE e nunca no jogo, porque o mundo grava número
    # desde então. O teste mantinha vivo um código morto.
    #
    # Agora os dois falam a mesma língua, e o corte é o mesmo de
    # `fatigue_penalty`: as duas faixas mais altas ("muito cansado" a partir de
    # 75%, "exausto" em 100%).
    drop(BOTA); wear(TORVIN, CAPA)
    set_route_base(6)
    set_status(TORVIN, fatigue=100, fatigue_max=100)      # exausto
    check("FR-004: base 6 + exausto (⇒9) + capa 3x ⇒ 3, não 2",
          travel_of(TORVIN) == 3, str(travel_of(TORVIN)))

    # e o contrário: cansado (50%) NÃO atrasa — só as duas faixas do topo
    set_status(TORVIN, fatigue=50, fatigue_max=100)
    check("FR-004: cansado (50%) NÃO atrasa — base 6 + capa 3x ⇒ 2",
          travel_of(TORVIN) == 2, str(travel_of(TORVIN)))

    # e o formato de rótulo LEGADO lê como descansado, como manda a spec 030
    # (FR-001) — o que este teste antes escondia
    set_status(TORVIN, fatigue="alto")
    check("rótulo legado ('alto') NÃO atrasa: lê como descansado (spec 030 FR-001)",
          travel_of(TORVIN) == 2, str(travel_of(TORVIN)))
    set_status(TORVIN, fatigue=0, fatigue_max=100)

    # piso (SC-005)
    set_route_base(2)
    set_multiplier(CAPA, 1000)
    check("SC-005: base 2 + multiplicador 1000 ⇒ 1, nunca 0",
          travel_of(TORVIN) == 1, str(travel_of(TORVIN)))

    set_route_base(0)
    check("piso não inventa viagem: base 0 continua 0", travel_of(TORVIN) == 0)
    set_multiplier(CAPA, 3)

    # --- US2: não empilha, com tempo real ------------------------------------- #
    set_route_base(9)
    wear(TORVIN, BOTA)  # capa 3x + bota 2x
    check("SC-002: capa 3x + bota 2x ⇒ tempo 3 (÷3), nunca 2 (÷6)",
          travel_of(TORVIN) == 3, str(travel_of(TORVIN)))
    drop(BOTA)

    # --- US4: o persuadido viaja com os PRÓPRIOS itens (SC-006) --------------- #
    drop(CAPA)
    wear(ELGA, CAPA)          # a capa é do ALVO
    sozinha = travel_of(ELGA)
    persuadida = motor.apply_resolution(TORVIN, res(
        persuade_ops=[{"personagem": ELGA, "rota": ROTA, "vontade": 10}]))
    tempo_persuadida = persuadida["persuade_ops_applied"][0]["travel_time"]
    check("SC-006: persuadida viaja no MESMO tempo que partindo sozinha",
          sozinha == tempo_persuadida == 3,
          f"sozinha={sozinha} persuadida={tempo_persuadida}")
    bring_back(ELGA)

    # o item de quem PERSUADE não conta
    drop(CAPA)
    wear(TORVIN, CAPA)        # agora a capa é do persuasor
    persuadida2 = motor.apply_resolution(TORVIN, res(
        persuade_ops=[{"personagem": ELGA, "rota": ROTA, "vontade": 10}]))
    check("SC-006: capa do PERSUASOR não acelera o alvo ⇒ tempo normal 9",
          persuadida2["persuade_ops_applied"][0]["travel_time"] == 9,
          str(persuadida2["persuade_ops_applied"][0]["travel_time"]))
    bring_back(ELGA)

    # --- FR-007: fotografia na partida ---------------------------------------- #
    drop(CAPA)
    motor.enter_route(TORVIN, ROTA)          # parte SEM a capa (tempo 9)
    em_rota = motor.WORLD_DIR / "routes" / ROTA / TORVIN
    fm_antes, _ = motor.read_doc(em_rota / "character.md")
    arrive_antes = fm_antes["transit"]["arrive_ts"]
    capa_folder = item_folder(CAPA)           # veste a capa JÁ na estrada
    fm_capa, body_capa = motor.read_doc(capa_folder / "item.md")
    fm_capa["state"] = {"slot": "costas"}
    motor.write_doc(capa_folder / "item.md", fm_capa, body_capa)
    os.replace(capa_folder, em_rota / capa_folder.name)
    fm_depois, _ = motor.read_doc(em_rota / "character.md")
    check("FR-007: vestir a capa já em viagem não muda o arrive_ts gravado",
          fm_depois["transit"]["arrive_ts"] == arrive_antes)
    os.replace(em_rota / capa_folder.name, motor.WORLD_DIR / TAVERNA_ID / capa_folder.name)
    bring_back(TORVIN)
    drop(CAPA)

    # --- SC-007: nada de sistema desce ao player ------------------------------ #
    wear(TORVIN, CAPA)
    out = motor.apply_resolution(TORVIN, res(movement={"enter_route": ROTA}))
    payload = json.dumps({
        "narrative_hint": out.get("narrative_hint"),
        "failed_effects": server_app.inworld_failures(out.get("rejected") or []),
    }, ensure_ascii=False)
    check("SC-007: nenhum termo de sistema na narrativa da viagem acelerada",
          "speed_multiplier" not in payload and "multiplicador" not in payload
          and "travel" not in payload)
    bring_back(TORVIN)

    # --- validador ------------------------------------------------------------ #
    import validator  # noqa: E402
    ok = {"type": "item", "id": "x", "name": "X",
          "wearable": {"slot": "pes", "speed_multiplier": 2}}
    check("validador: speed_multiplier positivo é válido", validator.validate(ok) == [])
    sem = {"type": "item", "id": "x", "name": "X", "wearable": {"slot": "pes"}}
    check("validador: wearable sem speed_multiplier continua válido",
          validator.validate(sem) == [])
    for ruim in (0, -1, "rapido", True, None):
        mau = {"type": "item", "id": "x", "name": "X",
               "wearable": {"slot": "pes", "speed_multiplier": ruim}}
        errs = validator.validate(mau)
        check(f"validador: speed_multiplier {ruim!r} é rejeitado",
              any("speed_multiplier" in e for e in errs), str(errs))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 12 (spec 009) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
