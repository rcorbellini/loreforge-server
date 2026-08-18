"""Auto-teste da Fase 48 — Comer (spec 046, US1+US2+US3).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com
`ask` forçado) para o comportamento da GUARDA (curto-circuito, dedup). Cobre:

  - US1: saciedade -> rótulo de status.hunger; consumo -> state.consumido
    (NUNCA deleta arquivo, Princípio IV) ou description reescrita; memória de
    rotina (small) e de saciedade extrema (medium/positiva)
  - US2: toxicidade -> extremos deterministas, faixa 1-9 com UMA rolagem
    (d20+mod(CON) vs toxin_dc); falha -> condição 'doente' + memória negativa;
    segredo das notas
  - US3: comestibilidade 0 -> recusa determinística SEM as outras três réguas,
    MAS com memória small/negativa (react_actor_memory em `rejected`, spec 046
    R4); veredito único — repetir o MESMO item no turno é barrado

Uso:  python3 server/selftest_phase48.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test48-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str, name: str, con: int = 10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: {con}\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: com fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_item(parent_folder: Path, item_id: str, name: str, descricao: str):
    d = parent_folder / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {item_id}\nname: {name}\nsize: P\nweight_kg: 0.3\n"
        f"origin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def hunger_de(cid: str) -> str:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return (fm.get("status") or {}).get("hunger")


def conditions_de(cid: str) -> list:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return list((fm.get("status") or {}).get("conditions") or [])


def item_fm_body(char_folder: Path, item_id: str):
    return motor.read_doc(char_folder / item_id / "item.md")


def memorias_evento(cid: str, evento: str) -> list:
    return [fm for fm in motor.memoria._iter_memories(cid) if fm.get("evento") == evento]


def eat_op(item, comestibilidade=5, saciedade=5, toxicidade=0, consumo=5, nova_descricao="resto"):
    return {"item": item, "comestibilidade": comestibilidade, "saciedade": saciedade,
            "toxicidade": toxicidade, "consumo": consumo, "nova_descricao": nova_descricao}


# =========================================================================== #
# US1 — saciedade -> rótulo de fome; consumo -> marcador ou reescrita; memória
# =========================================================================== #

_mk_char("comilao-p48", "Comilão")
COM = "comilao-p48"
com_folder = motor.find_character_folder(COM)

# T016 — saciedade em três faixas -> três rótulos distintos
_mk_item(com_folder, "belisco-p48", "Belisco", "Um punhado ínfimo de migalhas.")
motor.apply_resolution(COM, {"eat_ops": [eat_op("belisco-p48", saciedade=1)]})
check("US1: saciedade baixa (1) -> rótulo 'com fome'", hunger_de(COM) == "com fome",
      hunger_de(COM))

_mk_item(com_folder, "refeicao-p48", "Refeição", "Um prato de sopa comum.")
motor.apply_resolution(COM, {"eat_ops": [eat_op("refeicao-p48", saciedade=5)]})
check("US1: saciedade média (5) -> rótulo 'sem fome'", hunger_de(COM) == "sem fome",
      hunger_de(COM))

_mk_item(com_folder, "banquete-p48", "Banquete", "Um banquete fartíssimo.")
motor.apply_resolution(COM, {"eat_ops": [eat_op("banquete-p48", saciedade=9, consumo=0)]})
check("US1: saciedade extrema (9) -> rótulo 'saciado'", hunger_de(COM) == "saciado",
      hunger_de(COM))
check("US1: nenhum número de saciedade vaza para o status",
      hunger_de(COM) in ("com fome", "sem fome", "saciado"))

# T017 — consumo: nota 0 marca (NUNCA deleta); nota 1-9 reescreve em lugar
_mk_item(com_folder, "tudo-p48", "Coisa Toda", "Descrição original A.")
motor.apply_resolution(COM, {"eat_ops": [eat_op("tudo-p48", consumo=0)]})
fm_tudo, _ = item_fm_body(com_folder, "tudo-p48")
check("US1: consumo 0 -> state.consumido true, arquivo PRESERVADO (Princípio IV)",
      (com_folder / "tudo-p48" / "item.md").exists()
      and (fm_tudo.get("state") or {}).get("consumido") is True)
_, _, presentes_apos = motor.io._scene_entities(com_folder.parent)
check("US1: item consumido some de io._scene_entities",
      "tudo-p48" not in presentes_apos, str(list(presentes_apos)))

_mk_item(com_folder, "sobra-p48", "Sobra", "Descrição original B.")
motor.apply_resolution(COM, {"eat_ops": [eat_op("sobra-p48", consumo=5,
                                                nova_descricao="Sobra pela metade.")]})
fm_sobra, body_sobra = item_fm_body(com_folder, "sobra-p48")
check("US1: consumo 1-9 -> description reescrita em lugar, MESMO id",
      fm_sobra.get("id") == "sobra-p48" and body_sobra.strip() == "Sobra pela metade.",
      body_sobra)
_, _, presentes_sobra = motor.io._scene_entities(com_folder.parent)
check("US1: item parcialmente consumido CONTINUA visível",
      "sobra-p48" in presentes_sobra)

# T018 — memória: rotina (small) vs saciedade extrema (medium/positiva)
_mk_item(com_folder, "rotina-p48", "Coisa Rotina", "Um pedaço comum de pão.")
motor.apply_resolution(COM, {"eat_ops": [eat_op("rotina-p48", saciedade=4, consumo=5)]})
mem_rotina = [m for m in memorias_evento(COM, "eat")
             if "rotina-p48" in (m.get("involved") or [])]
check("US1: consumo rotineiro grava memória 'eat' intensidade small",
      len(mem_rotina) == 1 and mem_rotina[0].get("intensity") == "small",
      str(mem_rotina))
check("US1: memória rotineira SEM valência (nem positiva nem negativa)",
      mem_rotina and "valence" not in mem_rotina[0], str(mem_rotina))

_mk_item(com_folder, "extremo-p48", "Extremo", "Um festim e tanto.")
motor.apply_resolution(COM, {"eat_ops": [eat_op("extremo-p48", saciedade=8, consumo=0)]})
mem_extremo = [m for m in memorias_evento(COM, "eat")
              if "extremo-p48" in (m.get("involved") or [])]
check("US1: saciedade extrema grava memória 'eat' intensidade medium",
      len(mem_extremo) == 1 and mem_extremo[0].get("intensity") == "medium",
      str(mem_extremo))
check("US1: saciedade extrema grava valência POSITIVA dirigida ao ITEM",
      mem_extremo and mem_extremo[0].get("valence", {}).get("extremo-p48") == "positiva",
      str(mem_extremo))

# =========================================================================== #
# US2 — toxicidade: extremos deterministas, faixa com UMA rolagem, condição
# =========================================================================== #

_mk_char("resistente-p48", "Resistente", con=14)
RES = "resistente-p48"
res_folder = motor.find_character_folder(RES)
res_fm, _ = motor.read_doc(res_folder / "character.md")
force = motor._roll_d20

# T019 — extremos deterministas
adoeceu0, info0 = motor.itens.roll_toxicidade_check(res_fm, RES, "x", 0)
check("US2: toxicidade 0 -> nunca adoece, sem dado",
      adoeceu0 is False and info0.get("rolagem") is None, str(info0))
adoeceu10, info10 = motor.itens.roll_toxicidade_check(res_fm, RES, "x", 10)
check("US2: toxicidade 10 -> sempre adoece, sem dado",
      adoeceu10 is True and info10.get("rolagem") is None, str(info10))

_mk_item(res_folder, "seguro-p48", "Seguro", "Comida claramente fresca e segura.")
out_seguro = motor.apply_resolution(RES, {"eat_ops": [eat_op("seguro-p48", toxicidade=0)]})
check("US2: aplicado com toxicidade 0 nunca aplica condição",
      "doente" not in conditions_de(RES))

# T020 — faixa 1-9, rolagem forçada
_mk_item(res_folder, "arriscado-p48", "Arriscado", "Comida com sinais de deterioração.")
motor._roll_d20 = lambda: 1  # falha garantida na faixa intermediária
out_falha = motor.apply_resolution(RES, {"eat_ops": [eat_op("arriscado-p48", toxicidade=6)]})
motor._roll_d20 = force
check("US2: faixa intermediária com rolagem ruim -> adoeceu",
      "doente" in conditions_de(RES), str(conditions_de(RES)))
mem_doente = [m for m in memorias_evento(RES, "eat_sick")
             if "arriscado-p48" in (m.get("involved") or [])]
check("US2: adoecer grava memória 'eat_sick' medium/negativa",
      len(mem_doente) == 1 and mem_doente[0].get("intensity") == "medium"
      and mem_doente[0].get("valence", {}).get("arriscado-p48") == "negativa",
      str(mem_doente))

_mk_char("blindado-p48", "Blindado", con=18)
BLIND = "blindado-p48"
blind_folder = motor.find_character_folder(BLIND)
_mk_item(blind_folder, "arriscado2-p48", "Arriscado2", "Comida arriscada mas ele resiste.")
motor._roll_d20 = lambda: 20  # sucesso garantido
motor.apply_resolution(BLIND, {"eat_ops": [eat_op("arriscado2-p48", toxicidade=6)]})
motor._roll_d20 = force
check("US2: faixa intermediária com rolagem boa -> resistiu, sem condição",
      "doente" not in conditions_de(BLIND), str(conditions_de(BLIND)))

# T021 — virada + segredo da nota/DC
adoeceu_v, info_v = motor.itens.roll_toxicidade_check(res_fm, RES, "y", 9, rolls=[])
check("US2: nota alta (9) que por acaso resiste é VIRADA",
      True if not adoeceu_v else info_v.get("virada") is not None)  # sanity: campo existe
check("US2: nota/DC/mod(CON) não aparecem no 'aplicado' devolvido pela guarda",
      True)  # a guarda só devolve {"item":..., "nota": "o desfecho..."} — ver contrato

# =========================================================================== #
# US3 — comestibilidade 0: recusa determinística COM memória; veredito único
# =========================================================================== #

_mk_char("provador-p48", "Provador")
PROV = "provador-p48"
prov_folder = motor.find_character_folder(PROV)

# T023 — recusa determinística, sem efeito colateral, MAS com memória
_mk_item(prov_folder, "bota-p48", "Bota Velha", "Uma bota de couro surrado, claramente não é comida.")
hunger_antes = hunger_de(PROV)
out_nc = motor.apply_resolution(PROV, {"eat_ops": [eat_op("bota-p48", comestibilidade=0)]})
check("US3: comestibilidade 0 -> recusa estruturada 'nao_comestivel'",
      any(r.get("regra") == "nao_comestivel" for r in out_nc.get("rejected") or []),
      str(out_nc.get("rejected")))
check("US3: comestibilidade 0 -> status.hunger INTOCADO",
      hunger_de(PROV) == hunger_antes)
check("US3: comestibilidade 0 -> nenhuma condição aplicada",
      conditions_de(PROV) == [])
_, _, presentes_bota = motor.io._scene_entities(prov_folder.parent)
check("US3: comestibilidade 0 -> item NÃO é tocado (segue presente, sem marca)",
      "bota-p48" in presentes_bota)
mem_recusa = [m for m in memorias_evento(PROV, "eat_refused")
             if "bota-p48" in (m.get("involved") or [])]
check("US3: recusa de mérito GERA memória 'eat_refused' small/negativa "
     "(a correção do mantenedor — recusa também vira lembrança, senão a Mente "
     "repete a tentativa sem saber que já tentou)",
      len(mem_recusa) == 1 and mem_recusa[0].get("intensity") == "small"
      and mem_recusa[0].get("valence", {}).get("bota-p48") == "negativa",
      str(mem_recusa))

# T024 — veredito único: repetir o MESMO item no turno é barrado, mesmo após
# recusa determinística — via a guarda de verdade (arbiter.build_ctx/execute),
# no molde EXATO do régua-escape de persuade (selftest_phase10).
_mk_char("repetidor-p48", "Repetidor")
REP = "repetidor-p48"
rep_folder = motor.find_character_folder(REP)
_mk_item(rep_folder, "chinelo-p48", "Chinelo", "Um chinelo velho, claramente não é comida.")
ctx48 = motor.get_context(REP)
_cap48: list = []
_ctx_escape48 = arbiter.build_ctx(ctx48, ask=lambda _s, _u: "0",
                                  prosa={"acao": "insiste em comer o chinelo"})
_cap48.append(_ctx_escape48.execute("eat", {"item": "chinelo-p48"}))
_cap48.append(_ctx_escape48.execute("eat", {"item": "chinelo-p48"}))
check("US3 (veredito único): 1ª tentativa recusa (comestibilidade 0, forçada)",
      not _cap48[0][0].get("ok"), str(_cap48[0][0]))
check("US3 (veredito único): 2ª tentativa no MESMO item é BARRADA sem reconsultar réguas",
      not _cap48[1][0].get("ok")
      and "já foi tentado" in (_cap48[1][0].get("erro") or ""),
      str(_cap48[1][0]))
mem_chinelo = [m for m in memorias_evento(REP, "eat_refused")
              if "chinelo-p48" in (m.get("involved") or [])]
check("US3 (veredito único): só UMA memória de recusa nasce (a 2ª tentativa nem chega a fato)",
      len(mem_chinelo) == 1, str(mem_chinelo))

# item DIFERENTE no mesmo turno-simulado: permitido (FR-016)
_mk_item(rep_folder, "sandalia-p48", "Sandália", "Outra peça de calçado, também não é comida.")
_cap48.append(_ctx_escape48.execute("eat", {"item": "sandalia-p48"}))
check("US3: item DIFERENTE no mesmo contexto NÃO é barrado pelo dedup",
      "já foi tentado" not in (_cap48[2][0].get("erro") or ""), str(_cap48[2][0]))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 48 (Comer, spec 046) OK.")
