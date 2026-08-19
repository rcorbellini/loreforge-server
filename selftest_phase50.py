"""Auto-teste da Fase 50 — Cozinhar (spec 048, US1+US2+US3+US4).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com
`ask` forçado) para o comportamento da GUARDA (curto-circuito, dedup, exclusividade
`is_cooking`). Cobre:

  - US1: combinação válida + fonte de calor válida -> ingredientes removidos no
    ato; `status.cozinhando` pendente; item novo materializa só depois de
    `pronto_ts`, via `get_context` (resolução preguiçosa, molde de `_resolve_arrivals`)
  - US2: fonte de calor / cozinhabilidade 0 -> recusa determinística, com memória;
    erro corrigível (id/alcance) -> sem memória; `ja_cozinhando` bloqueia 2ª tentativa
  - US3: banda RUIM nunca é falha total -> prato nasce comprometido; a description
    candidata certa (ruim/média/ótima) é escolhida SÓ depois da rolagem
  - US4: proficiência em "cozinha" soma DIRETO na rolagem de favorabilidade (decide
    a banda, não só a magnitude) — curva assintótica sem teto (research R12)

Uso:  python3 selftest_phase50.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test50-"))
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


def _mk_char(cid: str, name: str, intel: int = 10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: {intel}\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_item(parent_folder: Path, item_id: str, name: str, descricao: str,
            weight_kg: float = 0.3):
    d = parent_folder / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {item_id}\nname: {name}\nsize: P\nweight_kg: {weight_kg}\n"
        f"origin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def _mk_object(location_folder: Path, object_id: str, name: str, descricao: str):
    d = location_folder / object_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {object_id}\nname: {name}\n"
        f"origin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def cooking_de(cid: str):
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return (fm.get("status") or {}).get("cozinhando")


def conditions_de(cid: str) -> list:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return list((fm.get("status") or {}).get("conditions") or [])


def memorias_evento(cid: str, evento: str) -> list:
    return [fm for fm in motor.memoria._iter_memories(cid) if fm.get("evento") == evento]


def cook_op(ingredientes, fonte_calor, fonte_de_calor=7, cozinhabilidade=7,
           favorabilidade=5, duracao=0, nome="Prato de Teste",
           descricao_ruim="malfeito", descricao_media="comum", descricao_otima="ótimo"):
    return {"ingredientes": list(ingredientes), "fonte_calor": fonte_calor,
            "fonte_de_calor": fonte_de_calor, "cozinhabilidade": cozinhabilidade,
            "favorabilidade": favorabilidade, "duracao": duracao, "nome": nome,
            "descricao_ruim": descricao_ruim, "descricao_media": descricao_media,
            "descricao_otima": descricao_otima}


def _forcar_pronto(cid: str):
    """Backdate `pronto_ts` pro passado — mesmo truque que outros testes de
    resolução preguiçosa já usam (`_backdate_descansando_desde`), sem dormir
    de verdade."""
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    cozinhando = dict(status.get("cozinhando") or {})
    cozinhando["pronto_ts"] = time.time() - 1
    status["cozinhando"] = cozinhando
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def _planta_memoria_cozinha(cid: str, intensity: str = "giant"):
    folder = motor.find_character_folder(cid)
    motor.memoria._write_memory(folder, "uma sessão e tanto na cozinha",
                                intensity=intensity, domain="cozinha", involved=[cid])


force = motor._roll_d20

# =========================================================================== #
# US1 — cozinhar de verdade: ingredientes somem no ato, prato materializa só
# depois do tempo real, em qualquer lugar ao alcance
# =========================================================================== #

_mk_char("cozinheiro-p50", "Cozinheiro de Teste")
COZ = "cozinheiro-p50"
coz_folder = motor.find_character_folder(COZ)
taverna_folder = coz_folder.parent

_mk_object(taverna_folder, "fogao-p50", "Fogão", "Um fogão de ferro com brasas vivas.")
_mk_item(coz_folder, "peixe-p50", "Peixe", "Um peixe fresco.", weight_kg=0.4)
_mk_item(coz_folder, "batata-p50", "Batata", "Uma batata terrosa.", weight_kg=0.2)

check("US1 (baseline): status.cozinhando não existe antes de cozinhar",
      cooking_de(COZ) is None, str(cooking_de(COZ)))

motor._roll_d20 = lambda: 20  # banda ótima garantida (favorabilidade=5, dc=10)
motor.apply_resolution(COZ, {"cozinha_ops": [
    cook_op(["peixe-p50", "batata-p50"], "fogao-p50", favorabilidade=5, duracao=2,
           nome="Peixe com Batata", descricao_otima="peixe assado com batata, no ponto")]})
motor._roll_d20 = force

check("US1: ingredientes REMOVIDOS imediatamente (consumo no ATO, não na materialização)",
      not (coz_folder / "peixe-p50").exists() and not (coz_folder / "batata-p50").exists())
pendente = cooking_de(COZ)
check("US1: status.cozinhando gravado com pronto_ts FUTURO",
      isinstance(pendente, dict) and pendente.get("pronto_ts", 0) > time.time(),
      str(pendente))
check("US1: NENHUM item novo existe ainda (materialização é preguiçosa)",
      not any((taverna_folder / p.get("id", "")).exists()
             for p in [pendente.get("prato") or {}]))
mem_otima_ato = memorias_evento(COZ, "cook_otimo")
check("US1: memória 'medium' positiva já gravada NO ATO (domain='cozinha')",
      len(mem_otima_ato) == 1 and mem_otima_ato[0].get("intensity") == "medium"
      and mem_otima_ato[0].get("domain") == "cozinha", str(mem_otima_ato))

prato_id = (pendente.get("prato") or {}).get("id")
_forcar_pronto(COZ)
motor.get_context(COZ)  # dispara a resolução preguiçosa (lazy_evaluate)
check("US1: após o tempo se cumprir, o prato passa a EXISTIR no lugar onde o ato começou",
      (taverna_folder / prato_id / "item.md").exists())
prato_fm, prato_body = motor.read_doc(taverna_folder / prato_id / "item.md")
check("US1: peso do prato = soma determinística dos ingredientes consumidos (0.4+0.2=0.6)",
      abs(float(prato_fm.get("weight_kg") or 0) - 0.6) < 1e-6, str(prato_fm.get("weight_kg")))
check("US1: a description do prato é a candidata 'ótima' (banda que saiu)",
      prato_body.strip() == "peixe assado com batata, no ponto", prato_body)
check("US1: status.cozinhando foi removido após materializar", cooking_de(COZ) is None)

# ingredientes em TRÊS lugares diferentes (mão/chão implícitos + dentro de um
# contêiner aberto) — mesmo filtro de `eat`, sem física nova (FR-001)
_mk_item(taverna_folder, "sal-p50", "Sal", "Um punhado de sal grosso.", weight_kg=0.05)
_mk_item(coz_folder, "bolsa-p50", "Bolsa Aberta", "Uma bolsa de couro aberta.", weight_kg=0.1)
(coz_folder / "bolsa-p50" / "item.md").write_text(
    "---\ntype: item\nid: bolsa-p50\nname: Bolsa Aberta\nsize: P\nweight_kg: 0.1\n"
    "container:\n  max_size: PP\n  max_items: 4\nstate:\n  fechado: false\n"
    "origin: editorial\n---\nUma bolsa de couro aberta.\n", encoding="utf-8")
_mk_item(coz_folder / "bolsa-p50", "ervas-p50", "Ervas", "Um maço de ervas frescas.",
         weight_kg=0.05)
ctx_multi = arbiter.build_ctx(
    motor.get_context(COZ),
    ask=lambda _s, _u: ('{"fonte_de_calor": 7, "cozinhabilidade": 7, "favorabilidade": 5, '
                        '"duracao": 0, "nome": "Tempero", "descricao_ruim": "ruim", '
                        '"descricao_media": "comum", "descricao_otima": "ótimo"}'),
    prosa={"acao": "cozinhar com o que der"})
res_multi = ctx_multi.execute("cook", {"ingredientes": ["sal-p50", "ervas-p50"],
                                       "fonte_calor": "fogao-p50"})
check("US1: ingrediente no CHÃO da cena + ingrediente DENTRO de contêiner aberto "
     "entram no enum e são aceitos, sem física nova",
      res_multi[0].get("ok") is True, str(res_multi[0]))

# dedup semântico (ctx.cooked_asked): testado no molde EXATO de eat/drink — a
# 1ª tentativa precisa ser uma RECUSA (senão o anti-loop genérico de `execute`
# já barra a 2ª chamada idêntica antes de chegar na guarda, mascarando o teste).
_mk_object(taverna_folder, "lareira-fria2-p50", "Lareira Fria", "Cinzas frias, apagada.")
_mk_item(coz_folder, "peixe-dedup-p50", "Peixe", "Peixe fresco.")
ctx_dedup = arbiter.build_ctx(
    motor.get_context(COZ),
    ask=lambda _s, _u: ('{"fonte_de_calor": 0, "cozinhabilidade": 5, "favorabilidade": 5, '
                        '"duracao": 0, "nome": "", "descricao_ruim": "", '
                        '"descricao_media": "", "descricao_otima": ""}'),
    prosa={"acao": "cozinhar na lareira apagada"})
res_dedup_1 = ctx_dedup.execute("cook", {"ingredientes": ["peixe-dedup-p50"],
                                         "fonte_calor": "lareira-fria2-p50"})
res_dedup_2 = ctx_dedup.execute("cook", {"ingredientes": ["peixe-dedup-p50"],
                                         "fonte_calor": "lareira-fria2-p50"})
check("US1 (dedup, 1ª tentativa): recusa determinística por fonte de calor",
      not res_dedup_1[0].get("ok"), str(res_dedup_1[0]))
check("US1 (dedup, 2ª tentativa): o MESMO conjunto+fonte é barrado pela guarda "
     "(`ctx.cooked_asked`), sem reconsultar as réguas",
      not res_dedup_2[0].get("ok")
      and "já foi tentado" in (res_dedup_2[0].get("erro") or ""), str(res_dedup_2[0]))

# segredo: nenhuma nota/proficiência aparece no manifest da tool
import types as _types_mod
import arbiter_tools.base as _face_mod
face_cook = _face_mod.build_face(motor.registro.get_spec("cook"), "cook",
                                 _types_mod.SimpleNamespace(
                                     cand={"cook_ingredientes": [], "cook_fonte": []},
                                     actor_id=COZ))
props_cook = (face_cook or {}).get("parameters", {}).get("properties", {})
check("US1: nenhuma das quatro notas (nem nome/descriptions candidatas) aparece na FACE",
      not ({"fonte_de_calor", "cozinhabilidade", "favorabilidade", "duracao", "nome",
           "descricao_ruim", "descricao_media", "descricao_otima"} & set(props_cook)),
      str(sorted(props_cook)))

# =========================================================================== #
# US2 — os dois gates de admissão recusam com memória; erro corrigível sem
# memória; `ja_cozinhando` bloqueia nova tentativa enquanto um prato pende
# =========================================================================== #

_mk_char("recusado-p50", "Recusado de Teste")
REC = "recusado-p50"
rec_folder = motor.find_character_folder(REC)
_mk_object(rec_folder.parent, "lareira-fria-p50", "Lareira Fria", "Cinzas frias, apagada.")
_mk_object(rec_folder.parent, "fogao2-p50", "Fogão", "Fogo aceso, brasas vivas.")
_mk_item(rec_folder, "peixe2-p50", "Peixe", "Peixe fresco.")
_mk_item(rec_folder, "aticador-p50", "Atiçador", "Uma haste de ferro fria, não é comida.")

out_sem_calor = motor.apply_resolution(REC, {"cozinha_ops": [
    cook_op(["peixe2-p50"], "lareira-fria-p50", fonte_de_calor=0)]})
check("US2: fonte de calor 0 -> recusa 'sem_calor'",
      any(r.get("regra") == "sem_calor" for r in out_sem_calor.get("rejected") or []),
      str(out_sem_calor.get("rejected")))
check("US2: fonte de calor 0 -> ingrediente NÃO consumido",
      (rec_folder / "peixe2-p50").exists())
check("US2: fonte de calor 0 -> status.cozinhando NUNCA criado", cooking_de(REC) is None)
mem_sem_calor = memorias_evento(REC, "cook_refused_fonte")
check("US2: recusa por fonte de calor GERA memória small/negativa",
      len(mem_sem_calor) == 1 and mem_sem_calor[0].get("intensity") == "small",
      str(mem_sem_calor))

out_sem_combo = motor.apply_resolution(REC, {"cozinha_ops": [
    cook_op(["aticador-p50"], "fogao2-p50", fonte_de_calor=7, cozinhabilidade=0)]})
check("US2: cozinhabilidade 0 -> recusa 'nao_cozinhavel'",
      any(r.get("regra") == "nao_cozinhavel" for r in out_sem_combo.get("rejected") or []),
      str(out_sem_combo.get("rejected")))
check("US2: cozinhabilidade 0 -> ingrediente NÃO consumido", (rec_folder / "aticador-p50").exists())
mem_sem_combo = memorias_evento(REC, "cook_refused_combo")
check("US2: recusa por cozinhabilidade GERA memória small/negativa",
      len(mem_sem_combo) == 1 and mem_sem_combo[0].get("intensity") == "small",
      str(mem_sem_combo))

out_corrigivel = motor.apply_resolution(REC, {"cozinha_ops": [
    cook_op(["item-inexistente-p50"], "fogao2-p50")]})
check("US2: ingrediente inexistente -> recusa 'ingrediente_inacessivel', SEM memória "
     "(erro corrigível, não recusa de mérito)",
      any(r.get("regra") == "ingrediente_inacessivel"
         for r in out_corrigivel.get("rejected") or [])
      and len(memorias_evento(REC, "cook_refused_fonte")) == 1  # não cresceu
      and len(memorias_evento(REC, "cook_refused_combo")) == 1,
      str(out_corrigivel.get("rejected")))

motor._roll_d20 = lambda: 20
motor.apply_resolution(REC, {"cozinha_ops": [
    cook_op(["peixe2-p50"], "fogao2-p50", favorabilidade=5)]})
motor._roll_d20 = force
check("US2: prato pendente criado — status.cozinhando agora existe",
      cooking_de(REC) is not None)
_mk_item(rec_folder, "batata2-p50", "Batata", "Outra batata.")
out_ja_cozinhando = motor.apply_resolution(REC, {"cozinha_ops": [
    cook_op(["batata2-p50"], "fogao2-p50")]})
check("US2: tentar cozinhar de novo com um prato JÁ pendente -> recusa 'ja_cozinhando'",
      any(r.get("regra") == "ja_cozinhando" for r in out_ja_cozinhando.get("rejected") or []),
      str(out_ja_cozinhando.get("rejected")))
check("US2: 'ja_cozinhando' não consome o segundo ingrediente", (rec_folder / "batata2-p50").exists())

# =========================================================================== #
# US3 — banda RUIM nunca é falha total; a description candidata certa (ruim/
# média/ótima) é escolhida SÓ depois da rolagem; encadeamento real com `eat`
# =========================================================================== #

_mk_char("azarado-p50", "Cozinheiro Azarado")
AZAR50 = "azarado-p50"
azar_folder = motor.find_character_folder(AZAR50)
_mk_object(azar_folder.parent, "fogao3-p50", "Fogão", "Fogo aceso.")
_mk_item(azar_folder, "peixe3-p50", "Peixe", "Peixe fresco.")

motor._roll_d20 = lambda: 1  # banda ruim garantida (favorabilidade=5, dc=10, mod=0)
motor.apply_resolution(AZAR50, {"cozinha_ops": [
    cook_op(["peixe3-p50"], "fogao3-p50", favorabilidade=5,
           descricao_ruim="peixe queimado por fora, cru por dentro",
           descricao_media="peixe comum", descricao_otima="peixe perfeito")]})
motor._roll_d20 = force
pendente_ruim = cooking_de(AZAR50)
check("US3: banda RUIM ainda cria status.cozinhando — NUNCA falha total",
      pendente_ruim is not None, str(pendente_ruim))
check("US3: a description candidata escolhida é a de banda RUIM, não uma genérica",
      (pendente_ruim.get("prato") or {}).get("description")
      == "peixe queimado por fora, cru por dentro",
      str(pendente_ruim))
mem_ruim = memorias_evento(AZAR50, "cook_ruim")
check("US3: banda RUIM grava memória small/negativa (domain='cozinha')",
      len(mem_ruim) == 1 and mem_ruim[0].get("intensity") == "small"
      and mem_ruim[0].get("domain") == "cozinha", str(mem_ruim))
check("US3: NENHUMA condição aplicada ao personagem por `cook` (a punição é de `eat`, depois)",
      conditions_de(AZAR50) == [])

prato_ruim_id = (pendente_ruim.get("prato") or {}).get("id")
_forcar_pronto(AZAR50)
motor.get_context(AZAR50)
prato_ruim_fm, prato_ruim_body = motor.read_doc(azar_folder.parent / prato_ruim_id / "item.md")
check("US3: prato malfeito materializou de verdade, com a description comprometida",
      prato_ruim_body.strip() == "peixe queimado por fora, cru por dentro", prato_ruim_body)

# encadeamento com `eat`: o prato malfeito é julgado por `eat`, sem atalho —
# valores medidos por sondagem real (sondagem_eat_sobre_cook_ruim.py, spec 048)
out_eat_ruim = motor.apply_resolution(AZAR50, {"eat_ops": [{
    "item": prato_ruim_id, "comestibilidade": 3, "saciedade": 2, "toxicidade": 8,
    "consumo": 0}]})
check("SC-010: `eat` julga o prato malfeito de `cook` normalmente — sem bypass "
     "(comestibilidade>0 aceita a tentativa, toxicidade alta reflete o risco medido)",
      bool(out_eat_ruim.get("eat_ops_applied")), str(out_eat_ruim))

# média e ótima: a candidata certa muda com a banda, sem reconsultar o Árbitro
_mk_char("medio-p50", "Cozinheiro Mediano")
MED50 = "medio-p50"
med_folder = motor.find_character_folder(MED50)
_mk_object(med_folder.parent, "fogao4-p50", "Fogão", "Fogo aceso.")
_mk_item(med_folder, "peixe4-p50", "Peixe", "Peixe fresco.")
motor._roll_d20 = lambda: 12  # total=12, dc=10, margem=2<=5 -> media
motor.apply_resolution(MED50, {"cozinha_ops": [
    cook_op(["peixe4-p50"], "fogao4-p50", favorabilidade=5,
           descricao_ruim="ruim", descricao_media="peixe comum, bem cozido",
           descricao_otima="ótimo")]})
motor._roll_d20 = force
pendente_media = cooking_de(MED50)
check("US3: banda MÉDIA escolhe a candidata 'média'",
      (pendente_media.get("prato") or {}).get("description") == "peixe comum, bem cozido",
      str(pendente_media))
mem_media = memorias_evento(MED50, "cook")
check("US3: banda MÉDIA grava memória small neutra/positiva (event='cook')",
      len(mem_media) == 1 and mem_media[0].get("intensity") == "small", str(mem_media))

# =========================================================================== #
# US4 — proficiência soma DIRETO na rolagem (decide a banda, não só a
# magnitude); `skills.cozinha` continua morto; curva assintótica sem teto
# =========================================================================== #

_mk_char("novato-p50", "Novato")
_mk_char("experiente-p50", "Experiente")
NOV50 = "novato-p50"
EXP50 = "experiente-p50"
nov_folder = motor.find_character_folder(NOV50)
exp_folder = motor.find_character_folder(EXP50)
_planta_memoria_cozinha(EXP50, "giant")  # peso 8.0 -> fator ~3.33 (R12)

nivel_nov = motor.memoria.proficiencies_for(NOV50).get("cozinha", 0)
nivel_exp = motor.memoria.proficiencies_for(EXP50).get("cozinha", 0)
check("US4: experiente tem proficiência 'cozinha' MAIOR que o novato (precondição)",
      nivel_exp > nivel_nov, f"novato={nivel_nov} experiente={nivel_exp}")

_mk_object(nov_folder.parent, "fogao5-p50", "Fogão", "Fogo aceso.")
_mk_object(exp_folder.parent, "fogao6-p50", "Fogão", "Fogo aceso.")
_mk_item(nov_folder, "peixe5-p50", "Peixe", "Peixe fresco.")
_mk_item(exp_folder, "peixe6-p50", "Peixe", "Peixe fresco.")

# MESMO d20 (9) para os dois: novato (nivel=0) -> total=9 < dc(10) -> ruim.
# experiente (nivel~3.33) -> total=12.33 -> margem 2.33<=5 -> media. A MESMA
# tirada produzindo bandas diferentes, só pela perícia (FR-007).
motor._roll_d20 = lambda: 9
motor.apply_resolution(NOV50, {"cozinha_ops": [
    cook_op(["peixe5-p50"], "fogao5-p50", favorabilidade=5)]})
motor.apply_resolution(EXP50, {"cozinha_ops": [
    cook_op(["peixe6-p50"], "fogao6-p50", favorabilidade=5)]})
motor._roll_d20 = force
banda_nov = memorias_evento(NOV50, "cook_ruim")
banda_exp = memorias_evento(EXP50, "cook")
check("US4: MESMO d20 (9) -> novato cai em banda RUIM, experiente cruza pra MÉDIA "
     "(a proficiência soma direto na tirada, FR-007)",
      len(banda_nov) == 1 and len(banda_exp) == 1,
      f"novato(ruim)={len(banda_nov)} experiente(media)={len(banda_exp)}")

_mk_char("elga-skill-p50", "Elga com skill morto", intel=10)
ELGA50 = "elga-skill-p50"
elga50_folder = motor.find_character_folder(ELGA50)
elga50_fm, elga50_body = motor.read_doc(elga50_folder / "character.md")
elga50_fm["skills"] = {"cozinha": 4}  # skills.cozinha alto, mas SEM memória de domínio
motor.write_doc(elga50_folder / "character.md", elga50_fm, elga50_body)
nivel_elga50 = motor.memoria.proficiencies_for(ELGA50).get("cozinha", -1)
check("US4: `skills.cozinha` alto (4) NÃO alimenta a proficiência dinâmica — "
     "fator continua 0.0 sem memória de domínio (FR-008)",
      nivel_elga50 == 0.0, str(nivel_elga50))

_mk_char("curva-p50", "Testador de Curva")
CURVA50 = "curva-p50"
_planta_memoria_cozinha(CURVA50, "giant")  # peso 8 (parcial de 16)
peso3_fator = motor.memoria._proficiency_factor(3.0)
peso16_fator = motor.memoria._proficiency_factor(16.0)
peso64_fator = motor.memoria._proficiency_factor(64.0)
check("US4: curva assintótica bate com a fórmula em peso=3/16/64, sem teto de nível",
      abs(peso3_fator - 10.0 * 3 / 19) < 1e-9
      and abs(peso16_fator - 5.0) < 1e-9
      and abs(peso64_fator - 8.0) < 1e-9,
      f"{peso3_fator} {peso16_fator} {peso64_fator}")

# recusas NÃO alimentam a proficiência — só prato criado de verdade conta
mem_dominio_recusa = [fm for fm in motor.memoria._iter_memories(REC)
                      if fm.get("evento") in ("cook_refused_fonte", "cook_refused_combo")
                      and fm.get("domain") == "cozinha"]
check("US4: recusas (sem_calor/nao_cozinhavel) NÃO carregam domain='cozinha' — "
     "só prato criado alimenta a proficiência (FR-009)",
      len(mem_dominio_recusa) == 0, str(mem_dominio_recusa))
mem_dominio_sucesso = [fm for fm in motor.memoria._iter_memories(AZAR50)
                       if fm.get("domain") == "cozinha"]
check("US4: prato criado (mesmo banda RUIM) carrega domain='cozinha'",
      len(mem_dominio_sucesso) == 1, str(mem_dominio_sucesso))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 50 (Cozinhar, spec 048) OK.")
