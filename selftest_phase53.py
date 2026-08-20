"""Auto-teste da Fase 53 — Forjar equipamento (spec 052, US1..US6).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com
`ask` forçado) para a GUARDA. Cobre:

  - US1: os quatro gates admitem/recusam SEPARADAMENTE; materiais somem só depois
    de todos passarem; a peça em processo nasce na cena; `character.md` sem campo
  - US2: retomada credita o tempo trabalhado COM CLAMP e NÃO chama o Árbitro
  - US3: conclusão escolhe a description da banda, grava `rarity` e o bloco
    mecânico; banda `falha` nasce SEM bloco (vale como improvisado)
  - US4: a maestria é TETO (não bônus); a catraca só desce; o EXTREMO do dado
    sobrevive à interrupção porque mora ao lado da banda, não dentro dela
  - US5: a peça guarda procedência — e ela NÃO aparece no contexto de cena
  - US6: `cook` migrado (a panela existe, é levável, o prato nasce onde ela está)
  - RETROFIT: `fate_twists` narra as rolagens de banda que morriam em silêncio

Uso:  python3 selftest_phase53.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test53-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import app  # noqa: E402
import motor  # noqa: E402
import arbiter  # noqa: E402
from motor.forja import primitivas as fp  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid, name, dex=10, stre=10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: {stre}\n  DEX: {dex}\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm ferreiro qualquer.\n", encoding="utf-8")
    return d


def _mk_item(parent, iid, name, desc, weight_kg=1.0):
    d = parent / iid
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {iid}\nname: {name}\nsize: P\nweight_kg: {weight_kg}\n"
        f"origin: editorial\n---\n{desc}\n", encoding="utf-8")
    return d


def _mk_object(loc, oid, name, desc):
    d = loc / oid
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {oid}\nname: {name}\norigin: editorial\n---\n{desc}\n",
        encoding="utf-8")
    return d


def _planta_memoria(cid, dominio, intensity="giant", quantas=1):
    folder = motor.find_character_folder(cid)
    for _ in range(quantas):
        motor.memoria._write_memory(folder, f"pratiquei {dominio}",
                                    intensity=intensity, domain=dominio,
                                    evento="pratica")


def forge_op(materiais, fonte, tipo="arma", forjabilidade=7, qualidade_material=7,
             fogo_de_forja=7, ferramental=7, duracao=0, nome="Lâmina de Teste",
             alta="uma lâmina de fio limpo", baixa="uma lâmina torta e sem fio",
             **extra):
    return {"tipo": tipo, "materiais": list(materiais), "fonte_calor": fonte,
            "forjabilidade": forjabilidade, "qualidade_material": qualidade_material,
            "fogo_de_forja": fogo_de_forja, "ferramental": ferramental,
            "duracao": duracao, "nome": nome,
            "descricao_alta": alta, "descricao_baixa": baixa, **extra}


def peca_de(cid):
    achado = motor.trabalho.peca_pendente_de(motor.find_character_folder(cid))
    return achado[0] if achado else None


def _forcar_d20(valor):
    motor.rolagem._roll_d20 = lambda: valor


_D20_REAL = motor.rolagem._roll_d20
taverna = motor.WORLD_DIR / TAVERNA


# --------------------------------------------------------------------------- #
# US1 — abertura: os quatro gates, o consumo e a peça que nasce
# --------------------------------------------------------------------------- #
FERR = "ferreiro-p53"
f_folder = _mk_char(FERR, "Ferreiro de Teste")
_mk_object(taverna, "forja-p53", "Forja", "Uma forja de pedra, o fole trabalhando, "
           "brasas vivas no fundo.")
_mk_item(taverna, "barra-p53", "Barra de Ferro", "Uma barra de ferro limpa.", 1.5)
_mk_item(taverna, "sucata-p53", "Sucata", "Ferro podre, farelento de ferrugem.", 0.5)

_forcar_d20(10)
out = motor.apply_resolution(FERR, {"forja_ops": [
    forge_op(["barra-p53"], "forja-p53", duracao=0)]})
check("US1: material consumido no ATO", not (taverna / "barra-p53").exists())
peca = peca_de(FERR)
check("US1: a peça em processo NASCE na cena, visível como entidade",
      peca is not None and (peca / "item.md").exists())
bloco = motor.trabalho.ler(peca)
check("US1: a peça carrega o relógio de ESFORÇO, nunca o de PRAZO",
      "tempo_necessario_s" in bloco and "pronto_ts" not in bloco, str(bloco))
check("US1: a peça grava QUAL capacidade a criou (recusa estrutural da outra)",
      bloco.get("tool") == "forge_weapon")
_fm_ator, _ = motor.read_doc(f_folder / "character.md")
check("SC-007: `character.md` NÃO ganhou nenhum campo de trabalho",
      "cozinhando" not in (_fm_ator.get("status") or {})
      and "forjando" not in (_fm_ator.get("status") or {}), str(_fm_ator.get("status")))
check("US1: peça em processo NÃO tem bloco mecânico nem raridade (FR-012)",
      motor.read_doc(peca / "item.md")[0].get("weapon") is None
      and motor.read_doc(peca / "item.md")[0].get("rarity") is None)

# cada gate recusa SOZINHO, com motivo próprio, e nada é consumido (FR-005c/FR-007)
for campo, regra in (("forjabilidade", "nao_forjavel"),
                     ("qualidade_material", "material_imprestavel"),
                     ("fogo_de_forja", "sem_calor_de_forja"),
                     ("ferramental", "sem_ferramental")):
    OUTRO = f"gate-{campo}-p53"
    _mk_char(OUTRO, "Gate")
    _mk_item(taverna, f"m-{campo}-p53", "Material", "Um material.", 1.0)
    r = motor.apply_resolution(OUTRO, {"forja_ops": [
        forge_op([f"m-{campo}-p53"], "forja-p53", **{campo: 0})]})
    regras = [x.get("regra") for x in (r.get("rejected") or [])]
    check(f"US1: gate '{campo}' em 0 recusa com '{regra}', e o material SOBREVIVE",
          regra in regras and (taverna / f"m-{campo}-p53").exists(), str(regras))

# ACHADO NO EXPLORATÓRIO: a lista vazia criava uma peça DO NADA pela bancada HTTP
VAZIO = "vazio-p53"; _mk_char(VAZIO, "Mãos Vazias")
r = motor.apply_resolution(VAZIO, {"forja_ops": [forge_op([], "forja-p53")]})
check("US1: `materiais` vazio -> recusa estrutural, e NENHUMA peça nasce do nada",
      any(x.get("regra") == "sem_material" for x in (r.get("rejected") or []))
      and peca_de(VAZIO) is None, str(r.get("rejected")))

# --------------------------------------------------------------------------- #
# US2 — retomada: credita com clamp, e ZERO consulta ao Árbitro
# --------------------------------------------------------------------------- #
motor.trabalho.atualizar(peca, trabalhando_desde=time.time() - 30,
                         tempo_necessario_s=300)
_asks = []
ctx = arbiter.build_ctx(motor.get_context(FERR),
                        ask=lambda s, u: _asks.append(1) or "{}")
res, _ = motor.registro.specs()["forge_weapon"].apply(
    "forge_weapon", {"peca": peca.name}, ctx)
motor.apply_resolution(FERR, {"forja_ops": ctx.queue["forja_ops"]})
bloco = motor.trabalho.ler(peca)
check("US2: retomar creditou o tempo efetivamente trabalhado (~30s)",
      29 <= (bloco.get("tempo_trabalhado_s") or 0) <= 32,
      str(bloco.get("tempo_trabalhado_s")))
check("SC-002: RETOMAR não consulta o Árbitro nenhuma vez",
      _asks == [], f"{len(_asks)} chamadas")

# O CLAMP: uma peça largada por dias credita só o que faltava, nunca os dias.
# Medido na primitiva, que é onde a linha mora — o crédito tem de bater EXATO no
# que restava, não só "não passar muito".
motor.trabalho.atualizar(peca, trabalhando_desde=time.time() - 86400 * 3,
                         tempo_trabalhado_s=100, tempo_necessario_s=300)
bloco = motor.trabalho.creditar_e_fechar(peca)
check("SC-003: peça largada por 3 dias credita EXATAMENTE o que faltava (clamp)",
      abs((bloco.get("tempo_trabalhado_s") or 0) - 300) < 0.01,
      str(bloco.get("tempo_trabalhado_s")))
check("SC-003: a sessão é fechada ao creditar — uma peça, uma sessão",
      "trabalhando_desde" not in bloco, str(bloco))
# e, aplicada pelo executor, a peça largada simplesmente CONCLUI
motor.trabalho.atualizar(peca, trabalhando_desde=time.time() - 86400 * 3,
                         tempo_trabalhado_s=0)
motor.apply_resolution(FERR, {"forja_ops": [{"tipo": "arma", "retomada": True,
                                             "peca": peca.name}]})
check("SC-003: a peça esquecida conclui — nunca ganha qualidade por ter esperado",
      motor.trabalho.ler(peca) is None)

# tool errada sobre a peça errada: estrutural, zero LLM. Peça NOVA, porque a
# anterior já concluiu no teste do clamp acima.
OFICINA = "oficina-p53"; _mk_char(OFICINA, "Dono da Oficina")
_mk_item(taverna, "mat-oficina-p53", "Material", "Metal.", 1.0)
_forcar_d20(10)
motor.apply_resolution(OFICINA, {"forja_ops": [
    forge_op(["mat-oficina-p53"], "forja-p53", duracao=10)]})
p_of = peca_de(OFICINA)
r = motor.apply_resolution(OFICINA, {"forja_ops": [
    {"tipo": "armadura", "retomada": True, "peca": p_of.name}]})
check("US2: `forge_armor` sobre peça de arma -> 'peca_de_outra_oficina' (zero LLM)",
      any(x.get("regra") == "peca_de_outra_oficina" for x in (r.get("rejected") or [])),
      str(r.get("rejected")))

# --------------------------------------------------------------------------- #
# US3 — conclusão
# --------------------------------------------------------------------------- #
item_fm, item_body = motor.read_doc(peca / "item.md")
check("US3: peça CONCLUÍDA deixa de carregar o bloco de trabalho",
      motor.trabalho.ler(peca) is None and item_fm.get("rarity") is not None,
      str(item_fm))
check("US3: a description escolhida corresponde à banda que saiu",
      item_body.strip() in ("uma lâmina de fio limpo", "uma lâmina torta e sem fio"),
      item_body)


def _forja_completa(cid, d20, **notas):
    """Abre, conclui e devolve o frontmatter final da peça."""
    _mk_item(taverna, f"mat-{cid}", "Material", "Metal de trabalho.", 1.0)
    _forcar_d20(d20)
    motor.apply_resolution(cid, {"forja_ops": [
        forge_op([f"mat-{cid}"], "forja-p53", duracao=0, **notas)]})
    p = peca_de(cid)
    motor.trabalho.atualizar(p, tempo_trabalhado_s=99999)
    motor.apply_resolution(cid, {"forja_ops": [
        {"tipo": notas.get("tipo", "arma"), "retomada": True, "peca": p.name}]})
    return p, motor.read_doc(p / "item.md")[0]

FALHO = "ferreiro-falho-p53"; _mk_char(FALHO, "Falho")
_p, fm_falha = _forja_completa(FALHO, 1, qualidade_material=1, fogo_de_forja=1,
                               ferramental=1)
check("US3/FR-025: banda `falha` nasce SEM bloco mecânico (vale como improvisado)",
      fm_falha.get("rarity") == "falha" and fm_falha.get("weapon") is None, str(fm_falha))
check("US3: `fisica.weapon_of` trata a peça falha como improvisada, sem regra nova",
      motor.fisica.weapon_of(fm_falha) == motor.fisica.weapon_of({}))

# --------------------------------------------------------------------------- #
# US4 — a maestria é TETO; a catraca só desce; o extremo sobrevive
# --------------------------------------------------------------------------- #
NOVATO = "novato-p53"; _mk_char(NOVATO, "Novato", dex=20)
_p, fm_novato = _forja_completa(NOVATO, 19, qualidade_material=10, fogo_de_forja=10,
                                ferramental=10)
check("SC-004: maestria 0 + material 10 + dado alto -> banda NUNCA passa do teto de "
      "maestria (`comum`)", fm_novato.get("rarity") == "comum", str(fm_novato.get("rarity")))

SORTUDO = "sortudo-p53"; _mk_char(SORTUDO, "Sortudo", dex=20)
_p, fm_sortudo = _forja_completa(SORTUDO, 20, qualidade_material=10, fogo_de_forja=10,
                                 ferramental=10)
check("FR-029: crítico natural leva o novato UMA banda acima do próprio teto",
      fm_sortudo.get("rarity") == "incomum", str(fm_sortudo.get("rarity")))

MESTRE = "mestre-p53"; _mk_char(MESTRE, "Mestre", dex=20)
_planta_memoria(MESTRE, "ferraria", "giant", quantas=4)   # peso 32 -> fator ~6.7
_p, fm_mestre = _forja_completa(MESTRE, 20, qualidade_material=10, fogo_de_forja=10,
                                ferramental=10)
check("FR-028: material 10 + maestria que sustenta + crítico -> `lendario`",
      fm_mestre.get("rarity") == "lendario", str(fm_mestre.get("rarity")))
check("US3: `lendario` traz o bloco mecânico acima do melhor equipamento editorial",
      (fm_mestre.get("weapon") or {}).get("damage") == 10, str(fm_mestre.get("weapon")))

SEM_CRIT = "semcrit-p53"; _mk_char(SEM_CRIT, "Sem Crítico", dex=20)
_planta_memoria(SEM_CRIT, "ferraria", "giant", quantas=4)
_p, fm_semcrit = _forja_completa(SEM_CRIT, 19, qualidade_material=10, fogo_de_forja=10,
                                 ferramental=10)
check("FR-031c: sem o crítico, `lendario` NÃO sai — a banda máxima não é alcançável "
      "por margem", fm_semcrit.get("rarity") != "lendario", str(fm_semcrit.get("rarity")))

# a CATRACA: um ferreiro pior rebaixa a peça, e ela nunca sobe
CAT = "catraca-p53"; _mk_char(CAT, "Dono da Peça", dex=20)
_planta_memoria(CAT, "ferraria", "giant", quantas=4)
_mk_item(taverna, "mat-catraca-p53", "Material", "Metal bom.", 1.0)
_forcar_d20(19)
motor.apply_resolution(CAT, {"forja_ops": [
    forge_op(["mat-catraca-p53"], "forja-p53", qualidade_material=10,
             fogo_de_forja=10, ferramental=10)]})
p_cat = peca_de(CAT)
banda_inicial = motor.trabalho.ler(p_cat).get("banda")
RUIM = "ferreiro-ruim-p53"; _mk_char(RUIM, "Ferreiro Ruim")
motor.apply_resolution(RUIM, {"forja_ops": [
    {"tipo": "arma", "retomada": True, "peca": p_cat.name}]})
banda_apos = motor.trabalho.ler(p_cat).get("banda")
check("US4: ferreiro sem maestria REBAIXA a peça que não sustenta",
      fp.indice(banda_apos) < fp.indice(banda_inicial), f"{banda_inicial} -> {banda_apos}")
motor.apply_resolution(CAT, {"forja_ops": [
    {"tipo": "arma", "retomada": True, "peca": p_cat.name}]})
check("FR-031: a catraca é de MÃO ÚNICA — o dono de volta não faz a banda subir",
      motor.trabalho.ler(p_cat).get("banda") == banda_apos)
mem_reb = [m for m in motor.memoria._iter_memories(RUIM)
           if m.get("evento") == "forge_downgrade"]
check("FR-039: o rebaixamento vira RÓTULO narrativo, nunca número",
      len(mem_reb) == 1 and "senti que a peça pedia mais" in (mem_reb[0].get("summary") or "")
      and mem_reb[0].get("domain") == "nenhuma", str(mem_reb))

# O EXTREMO SOBREVIVE À INTERRUPÇÃO (FR-031b / SC-001) — a asserção central da spec
SOBREV = "sobrevive-p53"; _mk_char(SOBREV, "Sortudo Interrompido", dex=20)
_mk_item(taverna, "mat-sobrev-p53", "Material", "Metal bom.", 1.0)
_forcar_d20(20)
motor.apply_resolution(SOBREV, {"forja_ops": [
    forge_op(["mat-sobrev-p53"], "forja-p53", qualidade_material=10,
             fogo_de_forja=10, ferramental=10, duracao=10)]})
p_sob = peca_de(SOBREV)
check("FR-031a: o EXTREMO fica congelado AO LADO da banda, não dentro dela",
      motor.trabalho.ler(p_sob).get("extremo") == "sucesso"
      and motor.trabalho.ler(p_sob).get("banda") == "comum",
      str(motor.trabalho.ler(p_sob)))
for _ in range(3):  # três interrupções e retomadas, pelo MESMO ferreiro
    motor.apply_resolution(SOBREV, {"forja_ops": [
        {"tipo": "arma", "retomada": True, "peca": p_sob.name}]})
motor.trabalho.atualizar(p_sob, tempo_trabalhado_s=99999)
motor.apply_resolution(SOBREV, {"forja_ops": [
    {"tipo": "arma", "retomada": True, "peca": p_sob.name}]})
check("SC-001/FR-031b: a obra acima da própria maestria SOBREVIVE a três "
      "interrupções — a sorte não mora na banda, mora ao lado dela",
      motor.read_doc(p_sob / "item.md")[0].get("rarity") == "incomum",
      str(motor.read_doc(p_sob / "item.md")[0].get("rarity")))

# --------------------------------------------------------------------------- #
# US5 — procedência: a peça guarda, a cena NÃO distribui
# --------------------------------------------------------------------------- #
mems_peca = motor.memoria._iter_memories_in(p_cat)
check("US5: a peça acumula a passagem de CADA ferreiro que trabalhou nela",
      len(mems_peca) >= 3, f"{len(mems_peca)} memórias")
ctx_cena = motor.get_context(CAT)
_texto_cena = str(ctx_cena)
check("FR-037: a procedência NÃO aparece no contexto de cena de quem está ali",
      "forge_session" not in _texto_cena and "forge_start" not in _texto_cena)

# --------------------------------------------------------------------------- #
# US6 — `cook` migrado, e o retrofit de `fate_twists`
# --------------------------------------------------------------------------- #
COZ = "cozinheiro-p53"; _mk_char(COZ, "Cozinheiro")
_mk_item(taverna, "peixe-p53", "Peixe", "Um peixe fresco.", 0.4)
motor.apply_resolution(COZ, {"cozinha_ops": [{
    "ingredientes": ["peixe-p53"], "fonte_calor": "forja-p53",
    "fonte_de_calor": 7, "cozinhabilidade": 7, "favorabilidade": 10, "duracao": 0,
    "nome": "Peixe Assado", "descricao_ruim": "queimado",
    "descricao_media": "comum", "descricao_otima": "no ponto"}]})
achado = motor.trabalho.peca_pendente_de(motor.find_character_folder(COZ),
                                         apenas_prazo=True)
check("US6/SC-013: cozinhar cria uma PANELA visível na cena (antes nada existia)",
      achado is not None and (achado[0] / "item.md").exists())
panela = achado[0]
check("US6: a panela usa o relógio de PRAZO, não o de ESFORÇO",
      motor.trabalho.por_prazo(motor.trabalho.ler(panela)))
# a panela é levada para outro lugar, e o prato nasce ONDE ELA ESTIVER (FR-046)
outro_lugar = motor.WORLD_DIR / TAVERNA / "quarto-dos-fundos-p53"
outro_lugar.mkdir(parents=True, exist_ok=True)
(outro_lugar / "location.md").write_text(
    "---\ntype: location\nid: quarto-p53\nname: Quarto\nsize: P\nentry_point: null\n"
    "origin: editorial\n---\nUm quarto pequeno.\n", encoding="utf-8")
motor.io.move_entity(panela, outro_lugar / panela.name)
panela = outro_lugar / panela.name
motor.trabalho.atualizar(panela, pronto_ts=time.time() - 1)
motor.get_context(COZ)
check("US6/FR-046: o prato nasce ONDE A PANELA ESTIVER, não onde o ato começou",
      motor.trabalho.ler(panela) is None
      and motor.read_doc(panela / "item.md")[1].strip() == "no ponto",
      motor.read_doc(panela / "item.md")[1])
check("SC-012: existe UMA via para trabalho pendente — `status.cozinhando` morreu",
      "cozinhando" not in str(motor.read_doc(
          motor.find_character_folder(COZ) / "character.md")[0]))

# --------------------------------------------------------------------------- #
# FR-005d/FR-005e — A OFICINA ESCRITA SÓ EM PROSA (o caso mais importante da spec)
# A única forja do mundo real (`porto-negro/forja-de-ferro`) descreve bigorna,
# tenazes, martelos e brasas do fole NA PROSA DA LOCATION, e não tem nenhum
# `object.md`. Um desenho que só olhasse objetos recusaria forjar exatamente onde
# se forja. Aqui o mesmo caso, reproduzido no mundo de teste.
# --------------------------------------------------------------------------- #
ferraria = motor.WORLD_DIR / TAVERNA / "ferraria-so-prosa-p53"
ferraria.mkdir(parents=True, exist_ok=True)
(ferraria / "location.md").write_text(
    "---\ntype: location\nid: ferraria-prosa-p53\nname: Ferraria\nsize: P\n"
    "entry_point: null\norigin: editorial\n---\n"
    "O ar é seco e quente; a bigorna ocupa o centro, cercada de tenazes, martelos e "
    "barris de água turva. Brasas respiram em vermelho no fundo do fole.\n",
    encoding="utf-8")
PROSA = "ferreiro-prosa-p53"
d_prosa = ferraria / PROSA
d_prosa.mkdir(parents=True, exist_ok=True)
shutil.copy(motor.find_character_folder(FERR) / "character.md", d_prosa / "character.md")
(d_prosa / "character.md").write_text(
    (d_prosa / "character.md").read_text(encoding="utf-8")
    .replace(f"id: {FERR}", f"id: {PROSA}"), encoding="utf-8")
_mk_item(ferraria, "barra-prosa-p53", "Barra de Ferro", "Ferro limpo.", 1.5)

_ctx_prosa = motor.get_context(PROSA)
_cand = arbiter.scene_candidates(arbiter._scene_index(_ctx_prosa))
check("FR-005e: o LUGAR entra no universo de fontes de calor, ao lado dos objects",
      "ferraria-prosa-p53" in _cand["forge_fonte"], str(_cand["forge_fonte"]))
check("FR-043a: e o mesmo vale para `cook` — a mesma prosa serve às duas",
      "ferraria-prosa-p53" in _cand["cook_fonte"], str(_cand["cook_fonte"]))

_forcar_d20(10)
motor.apply_resolution(PROSA, {"forja_ops": [
    forge_op(["barra-prosa-p53"], "ferraria-prosa-p53", duracao=0)]})
check("FR-005d/T030: forjar numa oficina escrita SÓ EM PROSA funciona — sem criar "
      "nenhuma entidade de cenário e sem declarar nenhum campo",
      peca_de(PROSA) is not None)

_mk_item(ferraria, "peixe-prosa-p53", "Peixe", "Um peixe.", 0.4)
COZP = "cozinheiro-prosa-p53"
d_cozp = ferraria / COZP
d_cozp.mkdir(parents=True, exist_ok=True)
(d_cozp / "character.md").write_text(
    (d_prosa / "character.md").read_text(encoding="utf-8")
    .replace(f"id: {PROSA}", f"id: {COZP}"), encoding="utf-8")
motor.apply_resolution(COZP, {"cozinha_ops": [{
    "ingredientes": ["peixe-prosa-p53"], "fonte_calor": "ferraria-prosa-p53",
    "fonte_de_calor": 7, "cozinhabilidade": 7, "favorabilidade": 5, "duracao": 0,
    "nome": "Peixe", "descricao_ruim": "r", "descricao_media": "m",
    "descricao_otima": "o"}]})
check("T014/FR-043a: cozinhar usando o LUGAR como fonte de calor funciona, e a "
      "régua de `cook` não mudou",
      motor.trabalho.peca_pendente_de(motor.find_character_folder(COZP),
                                      apenas_prazo=True) is not None)

# RETROFIT — as três rolagens que calculavam virada/crítico e não narravam nada
_antes = app.fate_twists([
    {"tipo": "cozinha", "resultado": "ruim", "virada": True, "critico": None,
     "rolagem": {"d20": 7}},
    {"tipo": "cura", "resultado": "alta", "virada": False, "critico": True,
     "rolagem": {"d20": 20}},
    {"tipo": "acougue", "resultado": "fraco", "virada": False, "critico": True,
     "rolagem": {"d20": 1}},
    {"tipo": "forja", "resultado": "raro", "virada": False, "critico": "sucesso",
     "rolagem": {"d20": 20}},
])
check("SC-011: as quatro rolagens de banda produzem frase in-world PRÓPRIA",
      len(_antes) == 4, str(_antes))
check("SC-011: o crítico natural SEM virada deixou de ser descartado em silêncio",
      any("as mãos souberam" in t["o_que"] for t in _antes), str(_antes))
check("SC-011: nenhuma delas cai mais no ramo genérico de FORÇA",
      not any("braços" in t["o_que"] for t in _antes), str(_antes))
check("FR-042: a frase in-world não carrega NENHUM número",
      not any(ch.isdigit() for t in _antes for ch in t["o_que"]), str(_antes))
# não-regressão dos seis ramos que já existiam
_combate = app.fate_twists([{"tipo": "combate", "resultado": "sucesso", "virada": False,
                             "critico": "sucesso", "rolagem": {"d20": 20}}])
check("T017: os ramos antigos de `fate_twists` saem idênticos",
      _combate and _combate[0]["o_que"] == "a lâmina achou exatamente o lugar",
      str(_combate))

motor.rolagem._roll_d20 = _D20_REAL
shutil.rmtree(_tmp, ignore_errors=True)
print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("Fase 53 (Forjar equipamento, spec 052) OK.")
