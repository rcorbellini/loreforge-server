"""Auto-teste da Fase 49 — Beber (spec 047, US1+US2+US3+US4+US5).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com
`ask` forçado) para o comportamento da GUARDA (curto-circuito, dedup, os dois
tipos de alvo). Cobre:

  - US1: hidratação -> rótulo de status.thirst; consumo -> io.rewrite_description
    SEMPRE (NUNCA io.remove_entity — divergência deliberada de `eat`, R3); memória
    de rotina (small) e de hidratação extrema (medium/positiva)
  - US2: embriaguez -> extremos deterministas, faixa 1-9 com UMA rolagem
    (d20+mod(CON) vs alcohol_dc); falha -> condição 'bêbado' + memória negativa;
    INDEPENDENTE da toxicidade (as duas podem falhar juntas, UMA memória só)
  - US3: toxicidade (reusada de `eat`, sem mudança) -> mesmo contrato, aplicada a
    `drink`; independência confirmada (toxicidade falha sozinha -> só 'doente')
  - US4: alvo `object` (fonte ambiental) -> réguas comuns aplicam, ZERO escrita no
    arquivo do object, repetível em turnos diferentes, bebibilidade 0 recusa igual
    a um item
  - US5: bebibilidade 0 -> recusa determinística SEM as outras réguas, MAS com
    memória small/negativa (react_actor_memory, contrato JÁ aberto por `eat` —
    zero extensão nova); veredito único — repetir o MESMO alvo no turno é barrado,
    inclusive um alvo `object`

Uso:  python3 selftest_phase49.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test49-"))
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
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
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


def _mk_object(location_folder: Path, object_id: str, name: str, descricao: str):
    d = location_folder / object_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {object_id}\nname: {name}\n"
        f"origin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def thirst_de(cid: str) -> str:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return (fm.get("status") or {}).get("thirst")


def conditions_de(cid: str) -> list:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return list((fm.get("status") or {}).get("conditions") or [])


def item_fm_body(char_folder: Path, item_id: str):
    return motor.read_doc(char_folder / item_id / "item.md")


def object_raw(location_folder: Path, object_id: str) -> str:
    return (location_folder / object_id / "object.md").read_text(encoding="utf-8")


def memorias_evento(cid: str, evento: str) -> list:
    return [fm for fm in motor.memoria._iter_memories(cid) if fm.get("evento") == evento]


def memoria_texto(cid: str, mem_id: str) -> str:
    folder = motor.find_character_folder(cid)
    _, body = motor.read_doc(folder / "memories" / f"{mem_id}.md")
    return body.strip()


def drink_op(alvo, bebibilidade=5, hidratacao=5, embriaguez=0, toxicidade=0,
            consumo=5, nova_descricao="resto"):
    return {"alvo": alvo, "bebibilidade": bebibilidade, "hidratacao": hidratacao,
            "embriaguez": embriaguez, "toxicidade": toxicidade, "consumo": consumo,
            "nova_descricao": nova_descricao}


def drink_op_fonte(alvo, bebibilidade=5, hidratacao=5, embriaguez=0, toxicidade=0):
    return {"alvo": alvo, "bebibilidade": bebibilidade, "hidratacao": hidratacao,
            "embriaguez": embriaguez, "toxicidade": toxicidade}


# =========================================================================== #
# US1 — hidratação -> rótulo de sede; consumo NUNCA remove; memória
# =========================================================================== #

_mk_char("sedento-p49", "Sedento")
SED = "sedento-p49"
sed_folder = motor.find_character_folder(SED)

check("US1 (baseline): status.thirst não existe antes de beber",
      thirst_de(SED) is None, str(thirst_de(SED)))

# T014 — hidratação em três faixas -> três rótulos distintos
_mk_item(sed_folder, "gole-p49", "Gole", "Um gole ínfimo de água num copo rachado.")
motor.apply_resolution(SED, {"drink_ops": [drink_op("gole-p49", hidratacao=1)]})
check("US1: hidratação baixa (1) -> rótulo 'com sede'", thirst_de(SED) == "com sede",
      thirst_de(SED))

_mk_item(sed_folder, "copo-p49", "Copo", "Um copo comum de água.")
motor.apply_resolution(SED, {"drink_ops": [drink_op("copo-p49", hidratacao=5)]})
check("US1: hidratação média (5) -> rótulo 'sem sede'", thirst_de(SED) == "sem sede",
      thirst_de(SED))

_mk_item(sed_folder, "barril-p49", "Barril", "Um barril farto de água fresca.")
motor.apply_resolution(SED, {"drink_ops": [drink_op("barril-p49", hidratacao=9, consumo=0)]})
check("US1: hidratação extrema (9) -> rótulo 'hidratado'", thirst_de(SED) == "hidratado",
      thirst_de(SED))
check("US1: nenhum número de hidratação vaza para o status",
      thirst_de(SED) in ("com sede", "sem sede", "hidratado"))

# T015 — régua de consumo: NUNCA remove, mesmo em nota 0 (R3, divergência de eat)
_mk_item(sed_folder, "cantil-p49", "Cantil", "Um cantil de couro, cheio de água.")
motor.apply_resolution(SED, {"drink_ops": [drink_op("cantil-p49", consumo=0,
                                                     nova_descricao="Cantil de couro, vazio.")]})
check("US1: consumo 0 -> o ARQUIVO CONTINUA EXISTINDO (io.remove_entity NUNCA chamado)",
      (sed_folder / "cantil-p49" / "item.md").exists())
fm_cantil, body_cantil = item_fm_body(sed_folder, "cantil-p49")
check("US1: consumo 0 -> description reescrita para o estado vazio, MESMO id",
      fm_cantil.get("id") == "cantil-p49" and "vazio" in body_cantil, body_cantil)
_, _, presentes_cantil = motor.io._scene_entities(sed_folder.parent)
check("US1: item com consumo 0 CONTINUA presente na cena (não some, diferente de eat)",
      "cantil-p49" in presentes_cantil, str(list(presentes_cantil)))

_mk_item(sed_folder, "sobra-p49", "Copo Cheio", "Descrição original B.")
motor.apply_resolution(SED, {"drink_ops": [drink_op("sobra-p49", consumo=5,
                                                     nova_descricao="Copo pela metade.")]})
fm_sobra, body_sobra = item_fm_body(sed_folder, "sobra-p49")
check("US1: consumo 1-9 -> description reescrita em lugar, MESMO id",
      fm_sobra.get("id") == "sobra-p49" and body_sobra.strip() == "Copo pela metade.",
      body_sobra)

# REGRESSÃO (mesmo achado de eat): resposta com consumo=0 mas descrição não-vazia
# não pode virar "vazio" calado — o texto vence a nota.
_mk_item(sed_folder, "sem-texto-p49", "Sem Texto", "Descrição original C.")
motor.apply_resolution(SED, {"drink_ops": [drink_op("sem-texto-p49", consumo=5,
                                                     nova_descricao="")]})
check("US1 (regressão): consumo>0 com nova_descricao VAZIA usa fallback, nunca fica calado",
      (sed_folder / "sem-texto-p49" / "item.md").exists())
_, body_sem_texto = item_fm_body(sed_folder, "sem-texto-p49")
check("US1 (regressão): a description mudou mesmo sem o texto do modelo",
      body_sem_texto.strip() != "Descrição original C.", body_sem_texto)

# T016 — memória: rotina (small) vs hidratação extrema (medium/positiva)
_mk_item(sed_folder, "rotina-p49", "Água Comum", "Um copo de água comum.")
motor.apply_resolution(SED, {"drink_ops": [drink_op("rotina-p49", hidratacao=4, consumo=5)]})
mem_rotina = [m for m in memorias_evento(SED, "drink")
             if "rotina-p49" in (m.get("involved") or [])]
check("US1: consumo rotineiro grava memória 'drink' intensidade small",
      len(mem_rotina) == 1 and mem_rotina[0].get("intensity") == "small",
      str(mem_rotina))

_mk_item(sed_folder, "extremo-p49", "Água Fartíssima", "Um barril farto e gelado.")
motor.apply_resolution(SED, {"drink_ops": [drink_op("extremo-p49", hidratacao=8, consumo=0)]})
mem_extremo = [m for m in memorias_evento(SED, "drink_sated")
              if "extremo-p49" in (m.get("involved") or [])]
check("US1: hidratação extrema grava memória 'drink_sated' intensidade medium",
      len(mem_extremo) == 1 and mem_extremo[0].get("intensity") == "medium",
      str(mem_extremo))
check("US1: hidratação extrema grava valência POSITIVA dirigida ao ALVO",
      mem_extremo and mem_extremo[0].get("valence", {}).get("extremo-p49") == "positiva",
      str(mem_extremo))

# =========================================================================== #
# US2 — embriaguez: extremos deterministas, faixa com UMA rolagem, condição,
# INDEPENDENTE de toxicidade (podem falhar juntas)
# =========================================================================== #

_mk_char("bebum-p49", "Bebum", con=10)
BEB = "bebum-p49"
beb_folder = motor.find_character_folder(BEB)
beb_fm, _ = motor.read_doc(beb_folder / "character.md")
force = motor._roll_d20

# T017 — extremos deterministas
embebedou0, info0 = motor.itens.roll_embriaguez_check(beb_fm, BEB, "x", 0)
check("US2: embriaguez 0 -> nunca embebeda, sem dado",
      embebedou0 is False and info0.get("rolagem") is None, str(info0))
embebedou10, info10 = motor.itens.roll_embriaguez_check(beb_fm, BEB, "x", 10)
check("US2: embriaguez 10 -> sempre embebeda, sem dado",
      embebedou10 is True and info10.get("rolagem") is None, str(info10))

# T018 — faixa 1-9, rolagem forçada
_mk_item(beb_folder, "cerveja-p49", "Cerveja Forte", "Uma cerveja escura e pesada.")
motor._roll_d20 = lambda: 1  # falha garantida na faixa intermediária
motor.apply_resolution(BEB, {"drink_ops": [drink_op("cerveja-p49", embriaguez=6, toxicidade=0)]})
motor._roll_d20 = force
check("US2: faixa intermediária com rolagem ruim -> ficou bêbado",
      "bêbado" in conditions_de(BEB), str(conditions_de(BEB)))
mem_bebado = [m for m in memorias_evento(BEB, "drink_drunk")
             if "cerveja-p49" in (m.get("involved") or [])]
check("US2: ficar bêbado grava memória 'drink_drunk' medium/negativa",
      len(mem_bebado) == 1 and mem_bebado[0].get("intensity") == "medium"
      and mem_bebado[0].get("valence", {}).get("cerveja-p49") == "negativa",
      str(mem_bebado))

_mk_char("resistente-p49", "Resistente", con=18)
RES = "resistente-p49"
res_folder = motor.find_character_folder(RES)
_mk_item(res_folder, "cerveja2-p49", "Cerveja2", "Cerveja forte mas ele resiste.")
motor._roll_d20 = lambda: 20  # sucesso garantido
motor.apply_resolution(RES, {"drink_ops": [drink_op("cerveja2-p49", embriaguez=6, toxicidade=0)]})
motor._roll_d20 = force
check("US2: faixa intermediária com rolagem boa -> resistiu, sem condição",
      "bêbado" not in conditions_de(RES), str(conditions_de(RES)))

# T019 — item AO MESMO TEMPO forte E contaminado: os dois testes independentes;
# se os DOIS falharem, as DUAS condições aplicam, mas UMA ÚNICA memória combinada
_mk_char("azarado-p49", "Azarado", con=8)
AZAR = "azarado-p49"
azar_folder = motor.find_character_folder(AZAR)
_mk_item(azar_folder, "porre-p49", "Porre Contaminado",
        "Uma bebida forte e visivelmente contaminada.")
motor._roll_d20 = lambda: 1  # falha garantida nos dois testes
motor.apply_resolution(
    AZAR, {"drink_ops": [drink_op("porre-p49", embriaguez=6, toxicidade=6)]})
motor._roll_d20 = force
conds_azar = conditions_de(AZAR)
check("US2/US3: os DOIS testes falhando aplicam as DUAS condições",
      "bêbado" in conds_azar and "doente" in conds_azar, str(conds_azar))
mem_combo = [m for m in memorias_evento(AZAR, "drink_sick_drunk")
            if "porre-p49" in (m.get("involved") or [])]
check("FR-014: os dois desfechos falhando geram UMA ÚNICA memória combinada",
      len(mem_combo) == 1, str(mem_combo))
mem_drunk_solo = [m for m in memorias_evento(AZAR, "drink_drunk")
                 if "porre-p49" in (m.get("involved") or [])]
mem_sick_solo = [m for m in memorias_evento(AZAR, "drink_sick")
                if "porre-p49" in (m.get("involved") or [])]
check("FR-014: NÃO nascem duas memórias separadas do mesmo ato",
      len(mem_drunk_solo) == 0 and len(mem_sick_solo) == 0,
      f"drunk={mem_drunk_solo} sick={mem_sick_solo}")

# T020 — virada + segredo
embebedou_v, info_v = motor.itens.roll_embriaguez_check(beb_fm, BEB, "y", 9, rolls=[])
check("US2: nota alta (9) que por acaso resiste é VIRADA",
      True if not embebedou_v else info_v.get("virada") is not None)

# =========================================================================== #
# US3 — toxicidade (reusada de eat, sem mudança): extremos, faixa, INDEPENDÊNCIA
# =========================================================================== #

# T021 — extremos deterministas (mesma curva/função de eat, aplicada por drink)
adoeceu0, tinfo0 = motor.itens.roll_toxicidade_check(beb_fm, BEB, "x", 0)
check("US3: toxicidade 0 -> nunca adoece, sem dado",
      adoeceu0 is False and tinfo0.get("rolagem") is None, str(tinfo0))
adoeceu10, tinfo10 = motor.itens.roll_toxicidade_check(beb_fm, BEB, "x", 10)
check("US3: toxicidade 10 -> sempre adoece, sem dado",
      adoeceu10 is True and tinfo10.get("rolagem") is None, str(tinfo10))

# T022 — faixa 1-9, rolagem forçada, via drink de verdade
_mk_char("provador-p49", "Provador de Água")
PROV = "provador-p49"
prov_folder = motor.find_character_folder(PROV)
_mk_item(prov_folder, "agua-ruim-p49", "Água Ruim", "Água turva, com sinais de contaminação.")
motor._roll_d20 = lambda: 1
motor.apply_resolution(PROV, {"drink_ops": [drink_op("agua-ruim-p49", embriaguez=0, toxicidade=6)]})
motor._roll_d20 = force
check("US3: faixa intermediária com rolagem ruim -> adoeceu",
      "doente" in conditions_de(PROV), str(conditions_de(PROV)))

# T023 — toxicidade falha SOZINHA (embriaguez 0, sem teste) -> só 'doente'
check("US3: toxicidade falhou sozinha -> 'bêbado' AUSENTE (independência)",
      "bêbado" not in conditions_de(PROV), str(conditions_de(PROV)))
mem_sick_solo2 = [m for m in memorias_evento(PROV, "drink_sick")
                 if "agua-ruim-p49" in (m.get("involved") or [])]
check("US3: memória 'drink_sick' isolada (sem embriaguez) grava medium/negativa",
      len(mem_sick_solo2) == 1 and mem_sick_solo2[0].get("intensity") == "medium",
      str(mem_sick_solo2))

# =========================================================================== #
# US4 — alvo OBJECT (fonte ambiental): zero escrita, repetível, bebibilidade 0
# =========================================================================== #

_mk_char("viajante-p49", "Viajante")
VIAJ = "viajante-p49"
viaj_folder = motor.find_character_folder(VIAJ)
_mk_object(viaj_folder.parent, "riacho-p49", "Riacho da Trilha",
          "Um riacho de água corrente, fria e límpida, descendo da rocha.")
raw_antes = object_raw(viaj_folder.parent, "riacho-p49")

# T024 — object-fonte funciona igual a item para as réguas comuns, ZERO escrita
motor.apply_resolution(VIAJ, {"drink_ops": [drink_op_fonte("riacho-p49", hidratacao=6)]})
check("US4: beber de object muda status.thirst igual a um item",
      thirst_de(VIAJ) == "sem sede", thirst_de(VIAJ))
raw_depois = object_raw(viaj_folder.parent, "riacho-p49")
check("US4: o arquivo do object permanece BYTE-A-BYTE idêntico antes/depois",
      raw_antes == raw_depois)

# T025 — repetir a MESMA fonte em "turnos diferentes" (chamadas de executor
# distintas, sem dedup de turno) funciona de novo, sem "esgotada"
out2 = motor.apply_resolution(VIAJ, {"drink_ops": [drink_op_fonte("riacho-p49", hidratacao=6)]})
check("US4: beber da MESMA fonte de novo (turno diferente) não é recusado",
      bool(out2.get("drink_ops_applied") or out2.get("applied")) or not out2.get("rejected"),
      str(out2.get("rejected")))
raw_depois2 = object_raw(viaj_folder.parent, "riacho-p49")
check("US4: mesmo após repetir, o arquivo do object segue intocado",
      raw_antes == raw_depois2)

# T026 — object cuja descrição NÃO estabelece líquido -> bebibilidade 0, recusa
_mk_object(viaj_folder.parent, "bau-p49", "Baú de Pedra", "Um baú de pedra maciça, seco por dentro.")
out_bau = motor.apply_resolution(VIAJ, {"drink_ops": [drink_op_fonte("bau-p49", bebibilidade=0)]})
check("US4: object não-bebível -> recusa estruturada 'nao_bebivel'",
      any(r.get("regra") == "nao_bebivel" for r in out_bau.get("rejected") or []),
      str(out_bau.get("rejected")))
mem_bau = [m for m in memorias_evento(VIAJ, "drink_refused")
          if "bau-p49" in (m.get("involved") or [])]
check("US4: recusa de object não-bebível TAMBÉM gera memória small/negativa",
      len(mem_bau) == 1 and mem_bau[0].get("intensity") == "small", str(mem_bau))

# T027 — fonte ambiental contaminada -> mesma régua de toxicidade de um item
_mk_object(viaj_folder.parent, "pantano-p49", "Poça do Pântano", "Água parada, turva e fétida.")
motor._roll_d20 = lambda: 1
motor.apply_resolution(VIAJ, {"drink_ops": [drink_op_fonte("pantano-p49", toxicidade=6)]})
motor._roll_d20 = force
check("US4: fonte ambiental contaminada pode adoecer, mesmo teste que item usaria",
      "doente" in conditions_de(VIAJ), str(conditions_de(VIAJ)))

# =========================================================================== #
# US5 — bebibilidade 0: recusa determinística COM memória; veredito único
# (item E object) via a GUARDA de verdade
# =========================================================================== #

_mk_char("teimoso-p49", "Teimoso")
TEI = "teimoso-p49"
tei_folder = motor.find_character_folder(TEI)

# T028 — recusa determinística, sem efeito colateral, MAS com memória
_mk_item(tei_folder, "pedra-p49", "Pedra", "Uma pedra lisa, claramente não é bebida.")
thirst_antes = thirst_de(TEI)
out_nb = motor.apply_resolution(TEI, {"drink_ops": [drink_op("pedra-p49", bebibilidade=0)]})
check("US5: bebibilidade 0 -> recusa estruturada 'nao_bebivel'",
      any(r.get("regra") == "nao_bebivel" for r in out_nb.get("rejected") or []),
      str(out_nb.get("rejected")))
check("US5: bebibilidade 0 -> status.thirst INTOCADO", thirst_de(TEI) == thirst_antes)
check("US5: bebibilidade 0 -> nenhuma condição aplicada", conditions_de(TEI) == [])
_, _, presentes_pedra = motor.io._scene_entities(tei_folder.parent)
check("US5: bebibilidade 0 -> item NÃO é tocado (segue presente, sem marca)",
      "pedra-p49" in presentes_pedra)
mem_recusa = [m for m in memorias_evento(TEI, "drink_refused")
             if "pedra-p49" in (m.get("involved") or [])]
check("US5: recusa de mérito GERA memória 'drink_refused' small/negativa "
     "(reusa react_actor_memory já aberto por eat — zero extensão nova)",
      len(mem_recusa) == 1 and mem_recusa[0].get("intensity") == "small"
      and mem_recusa[0].get("valence", {}).get("pedra-p49") == "negativa",
      str(mem_recusa))

# T029 — veredito único via a guarda de verdade (arbiter.build_ctx/execute),
# no molde EXATO do régua-escape de eat (selftest_phase48)
_mk_char("repetidor-p49", "Repetidor")
REP = "repetidor-p49"
rep_folder = motor.find_character_folder(REP)
_mk_item(rep_folder, "seixo-p49", "Seixo", "Um seixo pequeno, claramente não é bebida.")
_mk_item(rep_folder, "cascalho-p49", "Cascalho", "Outro pedaço de pedra, também não é bebida.")
_mk_object(rep_folder.parent, "cratera-seca-p49", "Cratera Seca",
          "Uma cratera de pedra, seca, claramente não tem água.")
ctx49 = motor.get_context(REP)
_cap49: list = []
_json_bebibilidade_0 = ('{"bebibilidade": 0, "hidratacao": 0, "embriaguez": 0, '
                        '"toxicidade": 0, "consumo": 0, "descricao": ""}')
_ctx_escape49 = arbiter.build_ctx(ctx49, ask=lambda _s, _u: _json_bebibilidade_0,
                                  prosa={"acao": "insiste em beber o seixo"})
_cap49.append(_ctx_escape49.execute("drink", {"alvo": "seixo-p49"}))
_cap49.append(_ctx_escape49.execute("drink", {"alvo": "seixo-p49"}))
check("US5 (veredito único): 1ª tentativa recusa (bebibilidade 0, forçada)",
      not _cap49[0][0].get("ok"), str(_cap49[0][0]))
check("US5 (veredito único): 2ª tentativa no MESMO alvo é BARRADA sem reconsultar réguas",
      not _cap49[1][0].get("ok")
      and "já foi tentado" in (_cap49[1][0].get("erro") or ""),
      str(_cap49[1][0]))
mem_seixo = [m for m in memorias_evento(REP, "drink_refused")
            if "seixo-p49" in (m.get("involved") or [])]
check("US5 (veredito único): só UMA memória de recusa nasce",
      len(mem_seixo) == 1, str(mem_seixo))

# alvo DIFERENTE no mesmo contexto: permitido (FR-018) — item já criado ANTES
# do ctx (o candidato "drink" é um snapshot; criar depois não entraria no enum)
_cap49.append(_ctx_escape49.execute("drink", {"alvo": "cascalho-p49"}))
check("US5: alvo DIFERENTE no mesmo contexto NÃO é barrado pelo dedup",
      "já foi tentado" not in (_cap49[2][0].get("erro") or ""), str(_cap49[2][0]))

# dedup também vale para um alvo OBJECT (fonte ambiental) — mesma trava
_cap49.append(_ctx_escape49.execute("drink", {"alvo": "cratera-seca-p49"}))
_cap49.append(_ctx_escape49.execute("drink", {"alvo": "cratera-seca-p49"}))
check("US5 (exploratório): dedup vale IGUALMENTE para um alvo object",
      not _cap49[4][0].get("ok")
      and "já foi tentado" in (_cap49[4][0].get("erro") or ""), str(_cap49[4][0]))

# =========================================================================== #
# REGRESSÃO PONTA-A-PONTA — chamada ÚNICA (mesmo molde de eat), pela GUARDA DE
# VERDADE (`_drink`, via `execute()`), para os DOIS tipos de alvo.
# =========================================================================== #
_mk_char("elga-p49", "Elga de Teste")
ELGA49 = "elga-p49"
elga49_folder = motor.find_character_folder(ELGA49)
_mk_item(elga49_folder, "cantil-real-p49", "Cantil",
        "Um cantil de couro, cheio de água fresca e limpa, sem sinal de vinho ou álcool.")
_resposta_item = (
    '{"bebibilidade": 8, "hidratacao": 5, "embriaguez": 0, "toxicidade": 0, '
    '"consumo": 4, "descricao": "cantil de couro, ainda com bastante água"}')
ctx_elga49 = motor.get_context(ELGA49)
ctx_real49 = arbiter.build_ctx(ctx_elga49, ask=lambda _s, _u: _resposta_item,
                               prosa={"acao": "beber do cantil"})
resultado_real49 = ctx_real49.execute("drink", {"alvo": "cantil-real-p49"})
check("REGRESSÃO PONTA-A-PONTA (item): a chamada foi aceita (não recusada)",
      resultado_real49[0].get("ok") is True, str(resultado_real49[0]))
check("REGRESSÃO PONTA-A-PONTA (item): NUNCA removido — arquivo continua existindo",
      (elga49_folder / "cantil-real-p49" / "item.md").exists())
_, body_real49 = item_fm_body(elga49_folder, "cantil-real-p49")
check("REGRESSÃO PONTA-A-PONTA (item): a description FOI reescrita com o texto do modelo",
      "água" in body_real49 and body_real49.strip() != (
          "Um cantil de couro, cheio de água fresca e limpa, sem sinal de vinho ou álcool."),
      body_real49)

_mk_object(elga49_folder.parent, "fonte-real-p49", "Fonte da Praça",
          "Uma fonte de pedra no centro da praça, água límpida jorrando sem parar.")
_resposta_fonte = ('{"bebibilidade": 9, "hidratacao": 6, "embriaguez": 0, "toxicidade": 0}')
ctx_fonte49 = arbiter.build_ctx(motor.get_context(ELGA49), ask=lambda _s, _u: _resposta_fonte,
                                prosa={"acao": "beber da fonte"})
raw_fonte_antes = object_raw(elga49_folder.parent, "fonte-real-p49")
resultado_fonte49 = ctx_fonte49.execute("drink", {"alvo": "fonte-real-p49"})
check("REGRESSÃO PONTA-A-PONTA (fonte): a chamada foi aceita (não recusada)",
      resultado_fonte49[0].get("ok") is True, str(resultado_fonte49[0]))
raw_fonte_depois = object_raw(elga49_folder.parent, "fonte-real-p49")
check("REGRESSÃO PONTA-A-PONTA (fonte): o arquivo do object NUNCA foi tocado",
      raw_fonte_antes == raw_fonte_depois)

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 49 (Beber, spec 047) OK.")
