"""Auto-teste da Fase 34 — Cura e socorro (spec 032, US1+US2+US3).

Sem nenhum modelo/LLM — exercita o Motor direto (`motor.apply_resolution`,
e o executor `motor.cura._apply_cura_ops` direto para a prova de
atomicidade). Cobre:

  - US1: `curar` é ação arbitrada de 3 bandas (baixa/media/alta) por
    margem de rolagem — extremos (nota 0/10) sem dado; remove
    `incapacitado` e recupera fração de HP nas bandas de sucesso; cobra
    fadiga em toda tentativa exceto na recusa de alvo inválido
  - US2: a fração de HP recuperada escala com o nível de proficiência do
    socorrista no domínio `cura` (`proficiencies_for`, spec 029)
  - US3: o custo de memória — `esquecida` é MAIS DEFINITIVA que
    `expired` (peso zero, nunca revive) nos quatro pontos que a
    consomem; memória nova nasce nos dois lados; leque de testemunha;
    nenhuma intenção nasce

Uso:  python3 server/selftest_phase34.py
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


def _mk_char(cid: str, name: str, con: int = 10, wis: int = 10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: {con}\n  INT: 10\n  WIS: {wis}\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")


def hp_de(cid: str) -> tuple[int, int]:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return motor.ensure_hp(fm)


def condicoes_de(cid: str) -> list:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return list((fm.get("status") or {}).get("conditions") or [])


def fadiga_de(cid: str) -> tuple[int, int]:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return motor.ensure_fatigue(fm)


def _derrubar(cid: str, hp_max: int = 50):
    """Deixa cid em hp=0, incapacitado — sem passar por combate de verdade
    (o QUE causou a derrota não importa pros testes desta fase, só QUE
    ele está derrubado)."""
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status["hp"] = 0
    status["hp_max"] = hp_max
    conds = [c for c in (status.get("conditions") or []) if c not in (motor.INCAPACITATED, motor.DEAD)]
    conds.append(motor.INCAPACITATED)
    status["conditions"] = conds
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def _matar(cid: str):
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    conds = [c for c in (status.get("conditions") or []) if c != motor.INCAPACITATED]
    conds.append(motor.DEAD)
    status["conditions"] = conds
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def _por_de_pe(cid: str, hp: int = 30, hp_max: int = 50):
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status["hp"], status["hp_max"] = hp, hp_max
    status["conditions"] = [c for c in (status.get("conditions") or [])
                            if c not in (motor.INCAPACITATED, motor.DEAD)]
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


# =========================================================================== #
# US1 — três bandas por margem, extremos sem dado, fadiga sempre cobrada
# =========================================================================== #

_mk_char("curador-p34", "Curador")
_mk_char("caido-p34", "Caído")
CURADOR, CAIDO = "curador-p34", "caido-p34"
curador_fm, _ = motor.read_doc(motor.find_character_folder(CURADOR) / "character.md")

force = motor._roll_d20

# T005 — nota 0: banda baixa, sem dado
banda0, info0 = motor.cura.roll_cura_check(curador_fm, curador_fm, 0)
check("US1: nota 0 -> banda baixa, sem dado",
      banda0 == "baixa" and info0.get("rolagem") is None, f"{banda0} {info0}")

# T006 — nota 10: banda alta, sem dado
banda10, info10 = motor.cura.roll_cura_check(curador_fm, curador_fm, 10)
check("US1: nota 10 -> banda alta, sem dado",
      banda10 == "alta" and info10.get("rolagem") is None, f"{banda10} {info10}")

# T007 — nota 5 (dc=10, mod(WIS10)=0): d20=10 -> media (margem 0); d20=20 -> alta (margem 10); d20=5 -> baixa
motor._roll_d20 = lambda: 10
banda_media, _ = motor.cura.roll_cura_check(curador_fm, curador_fm, 5)
motor._roll_d20 = lambda: 20
banda_alta, _ = motor.cura.roll_cura_check(curador_fm, curador_fm, 5)
motor._roll_d20 = lambda: 5
banda_baixa, _ = motor.cura.roll_cura_check(curador_fm, curador_fm, 5)
motor._roll_d20 = force
check("US1: nota 5, margem pequena (d20=10) -> media", banda_media == "media", banda_media)
check("US1: nota 5, margem grande (d20=20) -> alta", banda_alta == "alta", banda_alta)
check("US1: nota 5, falhou (d20=5) -> baixa", banda_baixa == "baixa", banda_baixa)

# T008 — banda baixa: nada muda no caído, fadiga do curador sobe
_derrubar(CAIDO)
fadiga_antes, _ = fadiga_de(CURADOR)
motor._roll_d20 = lambda: 5  # força banda baixa (nota 5, ver T007)
out_baixa = motor.apply_resolution(CURADOR, {"cura_ops": [{"alvo": CAIDO, "vantagem": 5}]})
motor._roll_d20 = force
check("US1: banda baixa não remove incapacitado",
      motor.INCAPACITATED in condicoes_de(CAIDO))
check("US1: banda baixa não muda HP do caído",
      hp_de(CAIDO)[0] == 0, str(hp_de(CAIDO)))
fadiga_depois, _ = fadiga_de(CURADOR)
check("US1: banda baixa AINDA cobra fadiga do curador",
      fadiga_depois > fadiga_antes, f"antes={fadiga_antes} depois={fadiga_depois}")

# T009 — banda media/alta: remove incapacitado, HP sobe fração (não ao máximo)
_derrubar(CAIDO)
motor._roll_d20 = lambda: 20  # força banda alta (nota 5, ver T007)
out_alta = motor.apply_resolution(CURADOR, {"cura_ops": [{"alvo": CAIDO, "vantagem": 5}]})
motor._roll_d20 = force
check("US1: banda alta aconteceu (precondição)",
      bool(out_alta.get("cura_ops_applied")), str(out_alta))
check("US1: banda alta remove incapacitado",
      motor.INCAPACITATED not in condicoes_de(CAIDO), str(condicoes_de(CAIDO)))
hp_apos_alta, hp_max_caido = hp_de(CAIDO)
check("US1: banda alta recupera HP SEM chegar ao máximo",
      0 < hp_apos_alta < hp_max_caido, f"hp={hp_apos_alta} max={hp_max_caido}")

# T010 — alvo não caído / morto: recusa, NUNCA cobra fadiga
_por_de_pe(CAIDO)
fadiga_antes_recusa, _ = fadiga_de(CURADOR)
out_nao_caido = motor.apply_resolution(CURADOR, {"cura_ops": [{"alvo": CAIDO, "vantagem": 5}]})
check("US1: alvo não caído é recusado",
      any(r.get("regra") == "alvo_nao_caido" for r in out_nao_caido.get("rejected") or []),
      str(out_nao_caido.get("rejected")))
check("US1: recusa de alvo não caído NÃO cobra fadiga",
      fadiga_de(CURADOR)[0] == fadiga_antes_recusa)

_matar(CAIDO)
out_morto = motor.apply_resolution(CURADOR, {"cura_ops": [{"alvo": CAIDO, "vantagem": 5}]})
check("US1: alvo morto é recusado (nunca confundido com incapacitado)",
      any(r.get("regra") == "alvo_ja_morto" for r in out_morto.get("rejected") or []),
      str(out_morto.get("rejected")))
check("US1: recusa de alvo morto NÃO cobra fadiga",
      fadiga_de(CURADOR)[0] == fadiga_antes_recusa)

# T011 — A PROVA DE ATOMICIDADE: chamar o executor DIRETO, sem arbiter.py
# nem turno.apply_op — precisa recusar por conta própria nos três casos.
curador_folder = motor.find_character_folder(CURADOR)

_por_de_pe(CAIDO)
_, rejected_de_pe = motor.cura._apply_cura_ops(
    CURADOR, curador_folder, {"cura_ops": [{"alvo": CAIDO, "vantagem": 5}]})
check("US1 (atomicidade): executor DIRETO recusa alvo não caído por conta própria",
      any(r.get("regra") == "alvo_nao_caido" for r in rejected_de_pe), str(rejected_de_pe))

_matar(CAIDO)
_, rejected_morto = motor.cura._apply_cura_ops(
    CURADOR, curador_folder, {"cura_ops": [{"alvo": CAIDO, "vantagem": 5}]})
check("US1 (atomicidade): executor DIRETO recusa alvo morto por conta própria",
      any(r.get("regra") == "alvo_ja_morto" for r in rejected_morto), str(rejected_morto))

_derrubar(CAIDO)
motor.apply_resolution(CURADOR, {"rest_ops": [{"op": "sleep"}]})  # curador começa a descansar
_, rejected_descansando = motor.cura._apply_cura_ops(
    CURADOR, curador_folder, {"cura_ops": [{"alvo": CAIDO, "vantagem": 5}]})
check("US1 (atomicidade): executor DIRETO recusa ator descansando por conta própria",
      any(r.get("regra") == "descansando" for r in rejected_descansando), str(rejected_descansando))
# acorda o curador pra não vazar estado
fm_cur, body_cur = motor.read_doc(curador_folder / "character.md")
status_cur = dict(fm_cur.get("status") or {})
status_cur["descansando_desde"] = time.time() - (8 * 3600 + 60)
fm_cur["status"] = status_cur
motor.write_doc(curador_folder / "character.md", fm_cur, body_cur)
motor.apply_resolution(CURADOR, {"rest_ops": [{"op": "wake_up"}]})

# =========================================================================== #
# US2 — a proficiência no domínio 'cura' escala o HP recuperado
# =========================================================================== #

_mk_char("novato-p34", "Novato")
_mk_char("expert-p34", "Expert")
_mk_char("caido-novato-p34", "Caído do Novato")
_mk_char("caido-expert-p34", "Caído do Expert")
NOVATO, EXPERT = "novato-p34", "expert-p34"
CAIDO_NOVATO, CAIDO_EXPERT = "caido-novato-p34", "caido-expert-p34"

# EXPERT acumula várias memórias vívidas no domínio 'cura'
expert_folder = motor.find_character_folder(EXPERT)
for i in range(4):
    motor.memoria._write_memory(
        expert_folder, f"socorri alguém uma vez ({i})",
        intensity="giant", domain="cura", involved=[EXPERT])

nivel_novato = motor.proficiencies_for(NOVATO).get("cura", 0)
nivel_expert = motor.proficiencies_for(EXPERT).get("cura", 0)
check("US2: expert tem proficiência 'cura' MAIOR que o novato (precondição)",
      nivel_expert > nivel_novato, f"novato={nivel_novato} expert={nivel_expert}")

# nota 10: sempre banda alta, sem dado — isola o efeito da proficiência
_derrubar(CAIDO_NOVATO)
_derrubar(CAIDO_EXPERT)
motor.apply_resolution(NOVATO, {"cura_ops": [{"alvo": CAIDO_NOVATO, "vantagem": 10}]})
motor.apply_resolution(EXPERT, {"cura_ops": [{"alvo": CAIDO_EXPERT, "vantagem": 10}]})
hp_curado_novato, _ = hp_de(CAIDO_NOVATO)
hp_curado_expert, _ = hp_de(CAIDO_EXPERT)
check("US2: EXPERT recupera MAIS HP que NOVATO na mesma banda",
      hp_curado_expert > hp_curado_novato,
      f"novato={hp_curado_novato} expert={hp_curado_expert}")

# =========================================================================== #
# US3 — esquecida vs expired (os quatro pontos), custo de memória, memória
# nova nos dois lados, leque de testemunha, ausência de intenção
# =========================================================================== #

_mk_char("dupla-p34", "Dupla")
DUPLA = "dupla-p34"
dupla_folder = motor.find_character_folder(DUPLA)
mid_expirada = motor.memoria._write_memory(
    dupla_folder, "uma memória qualquer vencida", intensity="medium",
    involved=[DUPLA, "alguem-p34"])
mid_esquecida = motor.memoria._write_memory(
    dupla_folder, "uma memória qualquer esquecida", intensity="medium",
    involved=[DUPLA, "alguem-p34"])
# força as duas a "não vivas" por caminhos diferentes
exp_path = dupla_folder / "memories" / f"{mid_expirada}.md"
esq_path = dupla_folder / "memories" / f"{mid_esquecida}.md"
fm_exp, body_exp = motor.read_doc(exp_path)
fm_exp["state"] = "expired"
motor.write_doc(exp_path, fm_exp, body_exp)
fm_esq, body_esq = motor.read_doc(esq_path)
fm_esq["state"] = "esquecida"
motor.write_doc(esq_path, fm_esq, body_esq)

# T021 — _is_alive trata os dois como não-vivos
check("US3: _is_alive — 'expired' não é viva",
      not motor.memoria._is_alive(motor.read_doc(exp_path)[0]))
check("US3: _is_alive — 'esquecida' TAMBÉM não é viva",
      not motor.memoria._is_alive(motor.read_doc(esq_path)[0]))

# achado ao vivo contra o servidor real (não coberto originalmente): get_active_memories
# tinha um check de "expired" PRÓPRIO, duplicado de _is_alive, que nunca soube de
# "esquecida" — a memória continuava sendo entregue à Mente pra narração.
memorias_ativas_dupla = motor.memoria.get_active_memories(dupla_folder)
check("US3: get_active_memories NUNCA entrega uma memória 'esquecida' à Mente",
      not any(m.get("id") == mid_esquecida for m in memorias_ativas_dupla),
      str([m.get("id") for m in memorias_ativas_dupla]))

# T022 — _weigh_memories (via familiarity_with): expired pesa 1/4, esquecida pesa ZERO
peso_com_expirada_apenas = motor.familiarity_with(DUPLA, "alguem-p34")
# some a esquecida (torna ela 'active' temporariamente) pra medir a diferença isolada
fm_temp, body_temp = motor.read_doc(esq_path)
fm_temp["state"] = "expired"
motor.write_doc(esq_path, fm_temp, body_temp)
peso_com_ambas_expiradas = motor.familiarity_with(DUPLA, "alguem-p34")
fm_temp["state"] = "esquecida"
motor.write_doc(esq_path, fm_temp, body_temp)
check("US3: memória 'esquecida' pesa MENOS que a mesma memória só 'expired'",
      peso_com_expirada_apenas < peso_com_ambas_expiradas,
      f"c/ esquecida={peso_com_expirada_apenas} c/ as 2 expiradas={peso_com_ambas_expiradas}")

# T023 — proficiencies_for: mesma distinção, agora por domínio
_mk_char("prof-p34", "Prof Teste")
PROF34 = "prof-p34"
prof34_folder = motor.find_character_folder(PROF34)
mid_prof_a = motor.memoria._write_memory(
    prof34_folder, "vivência a", intensity="giant", domain="cura", involved=[PROF34])
mid_prof_b = motor.memoria._write_memory(
    prof34_folder, "vivência b", intensity="giant", domain="cura", involved=[PROF34])
nivel_antes_esquecer = motor.proficiencies_for(PROF34).get("cura", 0)
path_prof_b = prof34_folder / "memories" / f"{mid_prof_b}.md"
fm_pb, body_pb = motor.read_doc(path_prof_b)
fm_pb["state"] = "esquecida"
motor.write_doc(path_prof_b, fm_pb, body_pb)
nivel_apos_esquecer = motor.proficiencies_for(PROF34).get("cura", 0)
check("US3: proficiencies_for cai quando uma memória vira 'esquecida' (peso zero)",
      nivel_apos_esquecer < nivel_antes_esquecer,
      f"antes={nivel_antes_esquecer} depois={nivel_apos_esquecer}")

# T024 — _renew_memory revive 'expired' mas NUNCA toca 'esquecida'
motor.memoria._renew_memory(dupla_folder, entity_id="alguem-p34", modo="prazo")
check("US3: _renew_memory REVIVE a memória apenas 'expired' (comportamento de sempre)",
      motor.read_doc(exp_path)[0].get("state") == "active")
check("US3: _renew_memory NUNCA revive a memória 'esquecida'",
      motor.read_doc(esq_path)[0].get("state") == "esquecida")

# T025-T027 — cenário fim-a-fim: banda media/alta esquece memórias vívidas,
# percentual escala com banda e proficiência, sempre alguma perda (piso)
_mk_char("curador2-p34", "Curador2")
_mk_char("caido2-p34", "Caído2")
CURADOR2, CAIDO2 = "curador2-p34", "caido2-p34"
caido2_folder = motor.find_character_folder(CAIDO2)
ids_pre_existentes = set()
for i in range(6):
    mid = motor.memoria._write_memory(
        caido2_folder, f"memória vívida do caído ({i})", intensity="giant",
        involved=[CAIDO2, "alguem-p34"])
    ids_pre_existentes.add(mid)
ativas_antes = sum(1 for fm in motor.memoria._iter_memories(CAIDO2)
                  if fm.get("id") in ids_pre_existentes and motor.memoria._is_alive(fm))
qtd_arquivos_antes = len(list(caido2_folder.glob("memories/*.md")))

_derrubar(CAIDO2)
motor.apply_resolution(CURADOR2, {"cura_ops": [{"alvo": CAIDO2, "vantagem": 10}]})  # banda alta
# só entre as PRÉ-EXISTENTES — a memória nova "healed" (_record_cura) nasce
# ATIVA na mesma chamada e não deve ser confundida com o que sobreviveu
ativas_depois = sum(1 for fm in motor.memoria._iter_memories(CAIDO2)
                   if fm.get("id") in ids_pre_existentes and motor.memoria._is_alive(fm))
esquecidas_depois = sum(1 for fm in motor.memoria._iter_memories(CAIDO2)
                       if fm.get("id") in ids_pre_existentes and fm.get("state") == "esquecida")
check("US3: cura bem-sucedida esquece AO MENOS UMA memória vívida (nunca de graça)",
      esquecidas_depois >= 1, f"esquecidas={esquecidas_depois}")
check("US3: as memórias esquecidas SOMEM da contagem de ativas (entre as pré-existentes)",
      ativas_depois == ativas_antes - esquecidas_depois,
      f"antes={ativas_antes} depois={ativas_depois} esquecidas={esquecidas_depois}")
check("US3: NENHUM arquivo de memória foi removido do disco (só cresce, nunca encolhe)",
      len(list(caido2_folder.glob("memories/*.md"))) >= qtd_arquivos_antes)

# T028 — memória nova nasce nos dois lados
memorias_curador2_novas = [fm for fm in motor.memoria._iter_memories(CURADOR2)
                          if fm.get("evento") == "heal"]
memorias_caido2_novas = [fm for fm in motor.memoria._iter_memories(CAIDO2)
                        if fm.get("evento") == "healed"]
check("US3: nasce memória nova 'heal' no curador",
      len(memorias_curador2_novas) >= 1)
check("US3: nasce memória nova 'healed' no curado",
      len(memorias_caido2_novas) >= 1)

# T029 — leque de testemunha: terceiro presente ganha memória witness_heal
_mk_char("curador3-p34", "Curador3")
_mk_char("caido3-p34", "Caído3")
_mk_char("testemunha-cura-p34", "Testemunha")
CURADOR3, CAIDO3, TESTEMUNHA_CURA = "curador3-p34", "caido3-p34", "testemunha-cura-p34"
_derrubar(CAIDO3)
motor.apply_resolution(CURADOR3, {"cura_ops": [{"alvo": CAIDO3, "vantagem": 10}]})
check("US3: testemunha presente ganha memória witness_heal do resgate",
      any(fm.get("evento") == "witness_heal" for fm in motor.memoria._iter_memories(TESTEMUNHA_CURA)))

# banda baixa não gera testemunha nenhuma
_mk_char("curador4-p34", "Curador4")
_mk_char("caido4-p34", "Caído4")
_mk_char("testemunha-cura2-p34", "Testemunha2")
CURADOR4, CAIDO4, TESTEMUNHA2 = "curador4-p34", "caido4-p34", "testemunha-cura2-p34"
_derrubar(CAIDO4)
motor.apply_resolution(CURADOR4, {"cura_ops": [{"alvo": CAIDO4, "vantagem": 0}]})  # banda baixa
check("US3: banda BAIXA não gera memória de testemunha nenhuma",
      not any(fm.get("evento") == "witness_heal" for fm in motor.memoria._iter_memories(TESTEMUNHA2)))

# T030 — NENHUMA intenção nasce no curado (FR-010/SC-007)
intentions_dir = motor.find_character_folder(CAIDO3) / "intentions"
qtd_intentions = len(list(intentions_dir.glob("*.md"))) if intentions_dir.exists() else 0
check("US3: nenhuma intenção nasce no curado após o resgate (FR-010)",
      qtd_intentions == 0, f"intentions encontradas: {qtd_intentions}")

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 34 (Cura e socorro, spec 032) OK.")
