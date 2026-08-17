"""Auto-teste da Fase 13 — Carregar e Arrastar Personagem (spec 010).

Cobre, com rolagem forçada (motor._roll_d20 injetável):
  - unidades: body_weight_of (declarado/padrão), total_weight_of (corpo + tudo
    que veste/carried_item_ids), resist_dc (10 + mod STR do alvo)
  - regime PESO (alvo caído): cabe nos braços ⇒ "carregado" sem dado; acima
    disso ⇒ "arrastado" com teste de força; além de 2x o arrasto ⇒
    peso_excede_arrasto SEM dado (SC-006)
  - regime DISPUTA (alvo de pé): d20 + mod(STR ator) vs 10 + mod(STR alvo);
    subir o STR do alvo vira sucesso em alvo_resistiu (SC-004)
  - independência dos regimes: no peso a força do alvo é irrelevante (SC-003);
    na disputa o peso do alvo é irrelevante
  - transporte conjunto (SC-001): mesmo destino e MESMO arrive_ts; chegada junta
  - velocidade (FR-008): a capa do CARREGADO não acelera; a do carregador sim
  - falhas distintas (SC-002) e pureza narrativa (SC-008)
  - FR-012: persuadir alvo caído/morto nega com alvo_desacordado
  - D8: quem chega caído não "se ambienta ao lugar"

Cenário: taverna → forja por portao-lateral. Torvin STR 16 (carried_item_ids 112,
arrasta 224, impossível > 448), peso 95; Elga STR 11 (carried_item_ids 77), peso 68.

Uso:  python3 server/selftest_phase13.py
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

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402
server_app.CONFIG["server"]["stream"] = True  # testa o STREAMING, indep. do config local
import arbiter  # noqa: E402
import motor  # noqa: E402
import selftest_helpers  # noqa: E402

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
ROTA, TAVERNA_ID, FORJA_ID = "portao-lateral", "taverna-do-gancho", "forja-de-ferro"
ARCA, BIGORNA, CAPA = "arca-de-ferro", "bigorna-de-pedra", "capa-do-vento"


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def force_roll(value):
    motor._roll_d20 = lambda: value


def forbid_roll():
    def _boom():
        raise AssertionError("rolagem não deveria acontecer aqui")
    motor._roll_d20 = _boom


def res(**parts):
    base = {"narrative_hint": "levanta o corpo", "movement": None,
            "mutations": [], "item_transfers": [], "equip_ops": [],
            "lock_ops": [], "persuade_ops": [], "attack_ops": [],
            "carry_ops": [], "memories": []}
    base.update(parts)
    return base


def carry(actor, alvo, rota=ROTA):
    return motor.apply_resolution(actor, res(
        carry_ops=[{"alvo": alvo, "rota": rota}]))


def cfolder(cid) -> Path:
    return motor.find_character_folder(cid)


def cfm(cid) -> dict:
    fm, _ = motor.read_doc(cfolder(cid) / "character.md")
    return fm


def patch_char(cid, **fields) -> None:
    folder = cfolder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    fm.update(fields)
    motor.write_doc(folder / "character.md", fm, body)


def set_status(cid, **fields) -> None:
    folder = cfolder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    fm["status"] = {**(fm.get("status") or {}), **fields}
    motor.write_doc(folder / "character.md", fm, body)


def knock_down(cid, morto=False) -> None:
    conds = ["incapacitado"] + (["morto"] if morto else [])
    set_status(cid, hp=0, conditions=conds)


def stand_up(cid) -> None:
    set_status(cid, hp=50, conditions=[])


def give_item(cid, item_id, slot="costas") -> None:
    folder = motor.find_entity(item_id)[0].parent
    fm, body = motor.read_doc(folder / "item.md")
    fm["state"] = {**(fm.get("state") or {}), "slot": slot}
    motor.write_doc(folder / "item.md", fm, body)
    dest = cfolder(cid) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def drop_item(item_id) -> None:
    folder = motor.find_entity(item_id)[0].parent
    fm, body = motor.read_doc(folder / "item.md")
    fm.pop("state", None)
    motor.write_doc(folder / "item.md", fm, body)
    dest = motor.WORLD_DIR / TAVERNA_ID / folder.name
    if folder != dest:
        os.replace(folder, dest)


def in_route(cid) -> bool:
    return (motor.WORLD_DIR / "routes" / ROTA / cid).is_dir()


def transit_of(cid) -> dict:
    child = motor.WORLD_DIR / "routes" / ROTA / cid
    fm, _ = motor.read_doc(child / "character.md")
    return fm.get("transit") or {}


def bring_back(cid) -> None:
    child = motor.WORLD_DIR / "routes" / ROTA / cid
    if not child.is_dir():
        return
    fm, body = motor.read_doc(child / "character.md")
    fm.pop("transit", None)
    motor.write_doc(child / "character.md", fm, body)
    os.replace(child, motor.WORLD_DIR / TAVERNA_ID / cid)


try:
    # --- unidades ------------------------------------------------------------ #
    check("body_weight_of: declarado vence o padrão",
          motor.body_weight_of({"weight_kg": 95}) == 95.0)
    check("body_weight_of: ausente ⇒ 70 (mundo antigo intacto)",
          motor.body_weight_of({}) == 70.0
          and motor.body_weight_of({"weight_kg": "pesado"}) == 70.0)
    check("total_weight_of: corpo + o que veste/carried_item_ids",
          abs(motor.total_weight_of(cfolder(ELGA)) - 68.0) < 5.0,
          str(motor.total_weight_of(cfolder(ELGA))))
    check("resist_dc = 10 + mod(STR do alvo): Torvin (16) 13, Elga (11) 10",
          motor.resist_dc(cfm(TORVIN)) == 13 and motor.resist_dc(cfm(ELGA)) == 10)

    # o limiar de arrasto trivial é EXATAMENTE a capacidade de carregar
    check("física: 0.5 × arrasto == capacidade de carregar (não há arrasto trivial)",
          motor.push_capacity(cfm(TORVIN)) * motor.PUSH_TRIVIAL_RATIO
          == motor.carry_capacity(cfm(TORVIN)))

    # --- regime PESO (US1) ---------------------------------------------------- #
    knock_down(ELGA)
    forbid_roll()
    out = carry(TORVIN, ELGA)
    check("caído leve: modo 'carregado', SEM dado",
          out["carry_ops_applied"]
          and out["carry_ops_applied"][0]["modo"] == "carregado"
          and out["rolls"] == [] and in_route(ELGA) and in_route(TORVIN))

    # SC-001: mesmo destino e MESMO arrive_ts
    t_ator, t_alvo = transit_of(TORVIN), transit_of(ELGA)
    check("SC-001: carregador e carregado com MESMO arrive_ts e destino",
          t_ator["arrive_ts"] == t_alvo["arrive_ts"]
          and t_ator["destination"] == t_alvo["destination"] == FORJA_ID,
          f"{t_ator.get('arrive_ts')} vs {t_alvo.get('arrive_ts')}")
    bring_back(TORVIN); bring_back(ELGA)

    # SC-003: no regime peso, a força do alvo é irrelevante
    forbid_roll()
    patch_char(ELGA, attributes={**cfm(ELGA)["attributes"], "STR": 20})
    out_forte = carry(TORVIN, ELGA)
    check("SC-003: alvo caído com STR 20 ⇒ mesmo desfecho (peso é que manda)",
          out_forte["carry_ops_applied"]
          and out_forte["carry_ops_applied"][0]["modo"] == "carregado"
          and out_forte["rolls"] == [])
    bring_back(TORVIN); bring_back(ELGA)
    patch_char(ELGA, attributes={**cfm(ELGA)["attributes"], "STR": 11})

    # arrasto com rolagem: Elga (carried_item_ids 77) levando Torvin (95) — 77 < 95 <= 308
    knock_down(TORVIN); stand_up(ELGA)
    force_roll(20)
    out_drag = carry(ELGA, TORVIN)
    check("caído pesado demais p/ os braços ⇒ 'arrastado' com teste de força",
          out_drag["carry_ops_applied"]
          and out_drag["carry_ops_applied"][0]["modo"] == "arrastado"
          and out_drag["rolls"] and out_drag["rolls"][0]["regime"] == "peso")
    bring_back(ELGA); bring_back(TORVIN)

    force_roll(1)
    out_fail = carry(ELGA, TORVIN)
    check("arrasto com dado ruim ⇒ teste_de_forca_falhou, ninguém se move",
          any(r.get("regra") == "teste_de_forca_falhou" for r in out_fail["rejected"])
          and not in_route(TORVIN) and not in_route(ELGA))

    # SC-006: além de 2× o arrasto de Elga (308) — carried_item_ids a bigorna (500) nele
    give_item(TORVIN, BIGORNA, "costas")
    forbid_roll()
    out_imp = carry(ELGA, TORVIN)
    check("SC-006: peso além do arrasto ⇒ peso_excede_arrasto, SEM dado",
          any(r.get("regra") == "peso_excede_arrasto" for r in out_imp["rejected"])
          and out_imp["rolls"] == [] and not in_route(TORVIN))
    drop_item(BIGORNA)

    # --- regime DISPUTA (US2) ------------------------------------------------- #
    stand_up(TORVIN)
    # Elga (STR 11, mod 0) tentando levar Torvin de pé (resist_dc 13): d20 >= 13
    force_roll(15)
    out_win = carry(ELGA, TORVIN)
    check("alvo DE PÉ com dado bom ⇒ levado, modo 'arrastado', regime disputa",
          out_win["carry_ops_applied"]
          and out_win["carry_ops_applied"][0]["modo"] == "arrastado"
          and out_win["rolls"][0]["regime"] == "disputa" and in_route(TORVIN))
    bring_back(ELGA); bring_back(TORVIN)

    # SC-004: MESMO dado, subindo o STR do alvo ⇒ vira falha.
    # Elga tem mod 0, então o total é o próprio d20 (15). STR 22 ⇒ dc 16 > 15.
    # (STR 20 daria dc 15, que EMPATA e passa — o empate é sucesso.)
    patch_char(TORVIN, attributes={**cfm(TORVIN)["attributes"], "STR": 22})
    force_roll(15)
    out_lose = carry(ELGA, TORVIN)
    check("SC-004: mesmo dado, alvo mais forte ⇒ alvo_resistiu",
          any(r.get("regra") == "alvo_resistiu" for r in out_lose["rejected"])
          and not in_route(TORVIN),
          str([r.get("regra") for r in out_lose["rejected"]]))

    # na disputa o PESO do alvo é irrelevante
    give_item(TORVIN, ARCA, "costas")
    force_roll(15)
    out_peso = carry(ELGA, TORVIN)
    check("disputa ignora o peso: mesmo dado e alvo mais pesado ⇒ mesma falha",
          any(r.get("regra") == "alvo_resistiu" for r in out_peso["rejected"]))
    drop_item(ARCA)
    patch_char(TORVIN, attributes={**cfm(TORVIN)["attributes"], "STR": 16})
    bring_back(ELGA); bring_back(TORVIN)

    # --- velocidade (FR-008) -------------------------------------------------- #
    knock_down(ELGA)
    give_item(ELGA, CAPA, "costas")          # a capa é do CARREGADO
    forbid_roll()
    com_capa_no_alvo = carry(TORVIN, ELGA)["carry_ops_applied"][0]["travel_time"]
    bring_back(TORVIN); bring_back(ELGA)
    drop_item(CAPA)
    forbid_roll()
    sem_capa = carry(TORVIN, ELGA)["carry_ops_applied"][0]["travel_time"]
    bring_back(TORVIN); bring_back(ELGA)
    check("FR-008: a capa de QUEM É CARREGADO não acelera a viagem",
          com_capa_no_alvo == sem_capa,
          f"com={com_capa_no_alvo} sem={sem_capa}")

    give_item(TORVIN, CAPA, "costas")        # agora a capa é do CARREGADOR
    forbid_roll()
    com_capa_no_ator = carry(TORVIN, ELGA)["carry_ops_applied"][0]["travel_time"]
    check("FR-008: a capa de QUEM CARREGA acelera normalmente",
          com_capa_no_ator < sem_capa,
          f"ator={com_capa_no_ator} sem={sem_capa}")
    bring_back(TORVIN); bring_back(ELGA)
    drop_item(CAPA)

    # --- chegada conjunta e D8 ------------------------------------------------ #
    knock_down(ELGA)
    forbid_roll()
    carry(TORVIN, ELGA)
    for cid in (TORVIN, ELGA):                # força o prazo a vencer
        child = motor.WORLD_DIR / "routes" / ROTA / cid
        fm, body = motor.read_doc(child / "character.md")
        fm["transit"] = {**fm["transit"], "arrive_ts": int(time.time()) - 1}
        motor.write_doc(child / "character.md", fm, body)
    motor.get_context(TORVIN)                 # dispara a chegada preguiçosa
    chegou = (motor.WORLD_DIR / FORJA_ID / TORVIN).is_dir() and \
             (motor.WORLD_DIR / FORJA_ID / ELGA).is_dir()
    check("chegada conjunta: os dois chegam ao destino", chegou)
    acao_caido = (cfm(ELGA).get("status") or {}).get("action") or ""
    check("D8: quem chega CAÍDO não 'se ambienta ao lugar'",
          "ambientando" not in acao_caido, acao_caido)
    acao_ator = (cfm(TORVIN).get("status") or {}).get("action") or ""
    check("D8: quem chega DE PÉ mantém o texto de sempre",
          "ambientando" in acao_ator, acao_ator)

    # devolve os dois à taverna
    for cid in (TORVIN, ELGA):
        os.replace(motor.WORLD_DIR / FORJA_ID / cid, motor.WORLD_DIR / TAVERNA_ID / cid)

    # --- FR-012: persuadir caído --------------------------------------------- #
    forbid_roll()
    out_p = motor.apply_resolution(TORVIN, res(
        persuade_ops=[{"personagem": ELGA, "rota": ROTA, "vontade": 10}]))
    check("FR-012: persuadir alvo CAÍDO nega com alvo_desacordado, sem dado",
          any(r.get("regra") == "alvo_desacordado" for r in out_p["rejected"])
          and not out_p["persuade_ops_applied"] and not in_route(ELGA))

    knock_down(ELGA, morto=True)
    forbid_roll()
    out_pm = motor.apply_resolution(TORVIN, res(
        persuade_ops=[{"personagem": ELGA, "rota": ROTA, "vontade": 10}]))
    check("FR-012: persuadir alvo MORTO também nega",
          any(r.get("regra") == "alvo_desacordado" for r in out_pm["rejected"]))

    stand_up(ELGA)
    forbid_roll()
    out_pok = motor.apply_resolution(TORVIN, res(
        persuade_ops=[{"personagem": ELGA, "rota": ROTA, "vontade": 10}]))
    check("FR-012: persuadir alvo DE PÉ continua idêntico (zero regressão)",
          out_pok["persuade_ops_applied"] and in_route(ELGA))
    bring_back(ELGA)

    # --- falhas distintas (SC-002) e pureza (SC-008) -------------------------- #
    knock_down(ELGA)
    out_inac = carry(TORVIN, "ninguem-aqui")
    out_rota = carry(TORVIN, ELGA, rota="rota-que-nao-existe")
    regras = set()
    for o in (out_fail, out_imp, out_lose, out_inac, out_rota, out_p):
        regras |= {r.get("regra") for r in o["rejected"] if r.get("regra")}
    check("SC-002: causas de falha distintas e não intercambiáveis",
          {"teste_de_forca_falhou", "peso_excede_arrasto", "alvo_resistiu",
           "personagem_inacessivel", "rota_indisponivel",
           "alvo_desacordado"} <= regras, str(sorted(regras)))

    # SC-008 vale para o TEXTO que a Mente narra. Os `valores`/`rolagem`
    # estruturados carregam peso, capacidade e DC de propósito desde a spec 004 —
    # são a matéria-prima da narração e morrem na Mente (Princípio V).
    frases = [f["o_que_falhou"] for f in server_app.inworld_failures(
        out_imp["rejected"] + out_lose["rejected"] + out_p["rejected"])
        if isinstance(f, dict)]
    frases += [t["o_que"] for t in server_app.fate_twists(out_lose["rolls"])]
    check("SC-008: nenhum número ou nome de campo nas FRASES in-world",
          frases and not any(any(ch.isdigit() for ch in f) for f in frases)
          and not any(termo in f for f in frases for termo in
                      ("capacidade", "peso_", "dc", "regra", "status")),
          str(frases))
    check("contrato preservado: os valores estruturados seguem com os números",
          any(r.get("valores", {}).get("peso_alvo") is not None
              for r in out_imp["rejected"]))

    # --- guarda do Árbitro ---------------------------------------------------- #
    stand_up(ELGA)
    ctx = motor.get_context(TORVIN)
    tools = {t["name"]: t for t in arbiter.build_tools(ctx)}
    check("manifest: tool 'carry' presente, com alvo e rota nos enums",
          "carry" in tools
          and ELGA in tools["carry"]["parameters"]["properties"]["alvo"]["enum"]
          and TORVIN not in tools["carry"]["parameters"]["properties"]["alvo"]["enum"])

    # spec 020: resolve_with_tools APLICA por-op (fase única); carry rola (disputa)
    # e move ATOR e ALVO — injeta-se dado válido e devolvem-se ambos à cena.
    force_roll(15)
    r_self = selftest_helpers.resolve_scripted(
        {"action": "carried_item_ids a si mesmo"}, ctx,
        [("carry", {"alvo": TORVIN, "rota": ROTA})])
    check("guarda: alvo == ator é recusado", not (r_self.get("carry_ops") or []))

    r_dup = selftest_helpers.resolve_scripted(
        {"action": "carried_item_ids duas vezes"}, ctx,
        [("carry", {"alvo": ELGA, "rota": ROTA}),
         ("carry", {"alvo": ELGA, "rota": ROTA})])
    check("guarda: segunda tentativa no mesmo alvo é ignorada",
          len(r_dup.get("carry_ops") or []) == 1)
    bring_back(TORVIN); bring_back(ELGA)  # o carry moveu os dois

    knock_down(ELGA)
    ctx_caida = motor.get_context(TORVIN)
    r_pers = selftest_helpers.resolve_scripted(
        {"action": "convence a caída"}, ctx_caida,
        [("persuade", {"personagem": ELGA, "rota": ROTA, "vontade": 10})])
    check("guarda: persuade recusa alvo caído já no Árbitro",
          not (r_pers.get("persuade_ops") or []))

    # --- movement não descarta carry_ops -------------------------------------- #
    # apply_resolution tem um early-return para `movement.enter_route`. Se o turno
    # pedir carregar E mover, o carry tem de vencer — carregar já é mover.
    knock_down(ELGA)
    forbid_roll()
    out_amb = motor.apply_resolution(TORVIN, res(
        movement={"enter_route": ROTA},
        carry_ops=[{"alvo": ELGA, "rota": ROTA}]))
    check("movement + carry no mesmo turno: o carry vence (alvo vai junto)",
          out_amb.get("carry_ops_applied") and in_route(ELGA) and in_route(TORVIN),
          str(out_amb.get("carry_ops_applied")))
    bring_back(TORVIN); bring_back(ELGA)

    out_so_mov = motor.apply_resolution(TORVIN, res(
        movement={"enter_route": ROTA}))
    check("movement sozinho continua sendo deslocamento simples",
          out_so_mov.get("movement", {}).get("moved") and in_route(TORVIN))
    bring_back(TORVIN)

    # --- gente não é item: a guarda redireciona para carry -------------------- #
    stand_up(ELGA)
    ctx_p = motor.get_context(TORVIN)
    r_take = selftest_helpers.resolve_scripted(
        {"action": "pega Elga no colo"}, ctx_p,
        [("take", {"item": ELGA})])
    check("guarda: `take` num personagem não vira transferência de item",
          not (r_take.get("item_transfers") or []))

    # --- o deslocamento não contorna mais o Árbitro (HISTÓRICO) --------------- #
    # Este teste guardava um atalho em `_handle_act` que resolvia
    # `intent.movement.enter_route` direto no Motor, ignorando o resto da
    # intenção livre (`{"action": ..., "target": ..., "movement": {...}}`).
    #
    # Spec 045 aposentou `/api/act` e o modelo de intenção livre inteiro — no
    # guichê único (`resolver_proposta`) não existe "uma intenção com um campo
    # movement embutido": `enter_route` é só mais uma capacidade nomeada, sem
    # atalho nenhum pra burlar (TODA capacidade passa pelo MESMO guard antes do
    # Árbitro — ver `resolver_proposta`, `app.py`). O bug que este teste travava
    # não tem mais como existir na forma antiga; a parte que ainda importa —
    # "personagem caído com `enter_route` continua barrado ANTES do Árbitro" —
    # já está coberta em `selftest_phase11.py` ("caído: enter_route também é
    # abortado pela mesma guarda"), contra o guichê único de verdade.
    stand_up(TORVIN)

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 13 (spec 010) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
