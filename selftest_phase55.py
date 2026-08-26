"""Auto-teste da Fase 55 — Colher (spec 054, US1+US2+US3).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com `ask`
forçado, ou contado) para o comportamento da GUARDA (enum de alvos, dedup, zero-LLM
estrutural). Cobre:

  - US1: alvo válido (LUGAR ou `object`) -> uma ou mais porções de matéria vegetal
    nascem NO ATO (síncrono, sem materialização preguiçosa)
  - US1/eixo central da spec: colher de uma `location` NUNCA a toca (hash idêntico);
    colher de um `object` reescreve o corpo dele para o estado colhido, instala um
    bloco `trabalho` de PRAZO cujo `resultado` guarda o NOME/CORPO ANTIGOS, e a
    rebrota (`trabalho.resolver_vencidas()`) restaura o arquivo byte a byte
  - US2: herbabilidade/riqueza 0 -> recusa de mérito, com memória; erro corrigível
    (id/alcance) -> sem memória; um `object` ainda não rebrotado sai do enum ->
    recusa estrutural, ZERO chamada ao Árbitro
  - US3: proficiência em "herbalismo" soma DIRETO na rolagem de riqueza (decide a
    banda, não só a quantidade depois) — mesmo mecanismo assintótico de "cozinha"/
    "acougue"; `character.skills.herbalismo` nunca é lido

Uso:  python3 selftest_phase55.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test55-"))
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


def _mk_char(cid: str, name: str, wis: int = 10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: {wis}\n  CHA: 10\n"
        f"skills:\n  herbalismo: 5\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_object(location_folder: Path, object_id: str, name: str, descricao: str):
    d = location_folder / object_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {object_id}\nname: {name}\n"
        f"origin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def forage_op(onde, herbabilidade=7, riqueza=7,
             nome_mato="Mato", descricao_mato="um punhado de mato murcho",
             nome_util="Ervas", descricao_util="um molho de ervas comuns",
             nome_seleta="Raiz-torta", descricao_seleta="raízes separadas com cuidado",
             descricao_colhida="revirado e sem nada mais à vista"):
    return {"onde": onde, "herbabilidade": herbabilidade, "riqueza": riqueza,
            "nome_mato": nome_mato, "descricao_mato": descricao_mato,
            "nome_util": nome_util, "descricao_util": descricao_util,
            "nome_seleta": nome_seleta, "descricao_seleta": descricao_seleta,
            "descricao_colhida": descricao_colhida}


def memorias_evento(cid: str, evento: str) -> list:
    return [fm for fm in motor.memoria._iter_memories(cid) if fm.get("evento") == evento]


def _hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _planta_memoria_herbalismo(cid: str, intensity: str = "giant"):
    folder = motor.find_character_folder(cid)
    motor.memoria._write_memory(folder, "uma colheita e tanto", intensity=intensity,
                                domain="herbalismo", involved=[cid])


force = motor._roll_d20

# =========================================================================== #
# US1 — a assimetria: colher de uma LOCATION não a toca; colher de um OBJECT
# reescreve o corpo e instala prazo; rebrota restaura byte a byte
# =========================================================================== #

_mk_char("herbalista-p55", "Herbalista de Teste")
HERB = "herbalista-p55"
herb_folder = motor.find_character_folder(HERB)
taverna_folder = herb_folder.parent
loc_file = taverna_folder / "location.md"
loc_hash_antes = _hash(loc_file)

motor._roll_d20 = lambda: 20  # banda seleta garantida (riqueza=7, dc baixa)
motor.apply_resolution(HERB, {"forage_ops": [forage_op(TAVERNA)]})
motor._roll_d20 = force

check("US1 (location): colher do LUGAR não toca location.md — hash idêntico",
      _hash(loc_file) == loc_hash_antes)
criados = [c for c in taverna_folder.iterdir()
          if c.is_dir() and c.name.startswith("erva-")]
check("US1 (location): pelo menos uma porção nasceu na pasta do lugar",
      len(criados) >= 1, str([c.name for c in criados]))
if criados:
    fm_porcao, corpo_porcao = motor.read_doc(criados[0] / "item.md")
    check("US1 (location): a porção carrega a description da banda SELETA",
          corpo_porcao.strip() == "raízes separadas com cuidado", corpo_porcao)
mem_seleta = memorias_evento(HERB, "forage_seleta")
check("US1 (location): memória 'medium' positiva gravada NO ATO (domain='herbalismo')",
      len(mem_seleta) == 1 and mem_seleta[0].get("intensity") == "medium"
      and mem_seleta[0].get("domain") == "herbalismo", str(mem_seleta))

# banda SELETA -> 3 porções (porcoes_de_erva)
check("US1: banda seleta rende 3 porções independentes",
      len(criados) == 3, str(len(criados)))

_mk_object(taverna_folder, "canteiro-p55", "Canteiro de Ervas",
          "Um canteiro fundo, de terra escura e revolvida, cheio de brotos.")
canteiro_folder = taverna_folder / "canteiro-p55"
canteiro_arquivo = canteiro_folder / "object.md"
fm_antes, corpo_antes = motor.read_doc(canteiro_arquivo)

motor._roll_d20 = lambda: 20
motor.apply_resolution(HERB, {"forage_ops": [forage_op("canteiro-p55", riqueza=5)]})
motor._roll_d20 = force

fm_depois, corpo_depois = motor.read_doc(canteiro_arquivo)
check("US1 (object): o CORPO foi reescrito para o texto de estado colhido",
      corpo_depois.strip() == "revirado e sem nada mais à vista", corpo_depois)
check("US1 (object): o FRONTMATTER 'name' NÃO mudou",
      fm_depois.get("name") == fm_antes.get("name"), str(fm_depois.get("name")))
bloco = motor.trabalho.ler(canteiro_folder)
check("US1 (object): ganhou bloco `trabalho` de PRAZO",
      isinstance(bloco, dict) and motor.trabalho.por_prazo(bloco)
      and bloco.get("tool") == "forage", str(bloco))
check("US1 (object): o `resultado` guarda o NOME/CORPO ANTIGOS (sentido invertido "
     "de cook/kindle_fire)",
      isinstance(bloco, dict)
      and bloco["resultado"].get("nome") == fm_antes.get("name")
      and bloco["resultado"].get("description") == corpo_antes,
      str(bloco.get("resultado")))
check("US1 (object): bloco SEM `ator` — não trava o colhedor em is_busy",
      "ator" not in (bloco or {}))
check("US1 (object): bloco SEM `extinto` — o canteiro FICA na cena, não sai de cena",
      not (bloco or {}).get("resultado", {}).get("extinto"))

motor.trabalho.atualizar(canteiro_folder, pronto_ts=time.time() - 1)
motor.get_context(HERB)  # dispara resolver_vencidas()
fm_rebrotado, corpo_rebrotado = motor.read_doc(canteiro_arquivo)
check("US1 (object): a REBROTA restaura o corpo byte a byte ao original",
      corpo_rebrotado == corpo_antes, corpo_rebrotado)
check("US1 (object): a rebrota restaura o `name` original",
      fm_rebrotado.get("name") == fm_antes.get("name"))
check("US1 (object): a rebrota REMOVE o bloco `trabalho`",
      motor.trabalho.ler(canteiro_folder) is None)

# =========================================================================== #
# US2 — os dois gates de admissão recusam com memória; erro corrigível sem
# memória; alvo ainda não rebrotado sai do enum -> ZERO chamada ao Árbitro
# =========================================================================== #

_mk_char("recusado-p55", "Recusado de Teste")
REC = "recusado-p55"
rec_folder = motor.find_character_folder(REC)
rec_taverna = rec_folder.parent

motor.apply_resolution(REC, {"forage_ops": [forage_op(TAVERNA, herbabilidade=0)]})
mem_sem_veg = memorias_evento(REC, "forage_refused_herbabilidade")
check("US2: HERBABILIDADE 0 -> recusa de mérito, memória small negativa",
      len(mem_sem_veg) == 1 and mem_sem_veg[0].get("intensity") == "small",
      str(mem_sem_veg))
check("US2: recusa de mérito NÃO carimba domain (fica 'nenhuma')",
      mem_sem_veg[0].get("domain") in (None, "nenhuma"), str(mem_sem_veg[0].get("domain")))

motor.apply_resolution(REC, {"forage_ops": [forage_op(TAVERNA, riqueza=0)]})
mem_nada = memorias_evento(REC, "forage_refused_riqueza")
check("US2: RIQUEZA 0 -> recusa de mérito, memória small negativa", len(mem_nada) == 1)

motor.apply_resolution(REC, {"forage_ops": [forage_op("id-que-nao-existe-p55")]})
check("US2: id inexistente -> recusa corrigível, ZERO memória nova",
      len(memorias_evento(REC, "forage_refused_herbabilidade")) == 1
      and len(memorias_evento(REC, "forage_refused_riqueza")) == 1)

_mk_object(rec_taverna, "canteiro-colhido-p55", "Canteiro Colhido",
          "Um canteiro colhido, revirado.")
canteiro_colhido = rec_taverna / "canteiro-colhido-p55"
motor.trabalho._grava_bloco(canteiro_colhido, {
    "tool": "forage", "pronto_ts": time.time() + 3600,
    "resultado": {"nome": "Canteiro de Ervas", "description": "Original."}})

chamadas = {"n": 0}


def _ask_conta(_s, _u):
    chamadas["n"] += 1
    return ('{"herbabilidade": 7, "riqueza": 7, "nome_mato": "m", "descricao_mato": "m", '
           '"nome_util": "u", "descricao_util": "u", "nome_seleta": "s", '
           '"descricao_seleta": "s", "descricao_colhida": "c"}')


ctx_cooldown = arbiter.build_ctx(motor.get_context(REC), ask=_ask_conta,
                                 prosa={"acao": "colher do canteiro já colhido"})
res_cooldown = ctx_cooldown.execute("forage", {"onde": "canteiro-colhido-p55"})
check("US2 (cooldown): object ainda não rebrotado sai do enum -> recusa determinística",
      not res_cooldown[0].get("ok"), str(res_cooldown[0]))
check("US2 (cooldown): ZERO chamadas ao Árbitro (o objeto nem chega a ser perguntado)",
      chamadas["n"] == 0, str(chamadas["n"]))

# dedup semântico (ctx.forage_asked): 1ª tentativa precisa ser recusa (senão o
# anti-loop genérico de `execute` já barra a repetição idêntica antes da guarda).
_mk_char("dedup-p55", "Dedup de Teste")
DED = "dedup-p55"
ctx_dedup = arbiter.build_ctx(
    motor.get_context(DED),
    ask=lambda _s, _u: ('{"herbabilidade": 0, "riqueza": 5, "nome_mato": "", '
                        '"descricao_mato": "", "nome_util": "", "descricao_util": "", '
                        '"nome_seleta": "", "descricao_seleta": "", '
                        '"descricao_colhida": ""}'),
    prosa={"acao": "colher na cena"})
res_dedup_1 = ctx_dedup.execute("forage", {"onde": TAVERNA})
res_dedup_2 = ctx_dedup.execute("forage", {"onde": TAVERNA})
check("US2 (dedup, 1ª tentativa): recusa determinística por herbabilidade",
      not res_dedup_1[0].get("ok"), str(res_dedup_1[0]))
check("US2 (dedup, 2ª tentativa): o MESMO `onde` é barrado pela guarda "
     "(`ctx.forage_asked`), sem reconsultar as réguas",
      not res_dedup_2[0].get("ok")
      and "já foi tentado" in (res_dedup_2[0].get("erro") or ""), str(res_dedup_2[0]))

# segredo: nenhuma nota/proficiência aparece no manifest da tool
import types as _types_mod
import arbiter_tools.base as _face_mod
face_forage = _face_mod.build_face(motor.registro.get_spec("forage"), "forage",
                                   _types_mod.SimpleNamespace(
                                       cand={"forage_onde": []}, actor_id=DED))
props_forage = (face_forage or {}).get("parameters", {}).get("properties", {})
check("US2: nenhuma das duas notas (nem os pares nome/description) aparece na FACE",
      not ({"herbabilidade", "riqueza", "nome_mato", "descricao_mato", "nome_util",
           "descricao_util", "nome_seleta", "descricao_seleta", "descricao_colhida"}
          & set(props_forage)),
      str(sorted(props_forage)))

# =========================================================================== #
# US3 — proficiência em "herbalismo" soma DIRETO na rolagem de riqueza,
# decidindo a PRÓPRIA banda com o MESMO d20; skills.herbalismo NUNCA é lido
# =========================================================================== #

_mk_char("novato-p55", "Novato de Teste", wis=10)
_mk_char("mestre-p55", "Mestre de Teste", wis=10)
NOV, MES = "novato-p55", "mestre-p55"
_planta_memoria_herbalismo(MES, intensity="giant")

motor._roll_d20 = lambda: 10  # d20 FIXO idêntico para os dois; dc(riqueza=6) = 8
motor.apply_resolution(NOV, {"forage_ops": [forage_op(TAVERNA, riqueza=6)]})
motor.apply_resolution(MES, {"forage_ops": [forage_op(TAVERNA, riqueza=6)]})
motor._roll_d20 = force

banda_nov = (memorias_evento(NOV, "forage_mato") or memorias_evento(NOV, "forage_util")
            or memorias_evento(NOV, "forage_seleta"))
banda_mes = (memorias_evento(MES, "forage_mato") or memorias_evento(MES, "forage_util")
            or memorias_evento(MES, "forage_seleta"))
check("US3: o NOVATO (proficiência 0) rendeu 'util' — nem farto nem mato, "
     "com o MESMO d20 fixo",
      len(memorias_evento(NOV, "forage_util")) == 1, str(banda_nov))
check("US3: o MESTRE (proficiência alta em 'herbalismo') cruza para 'seleta' com "
     "o MESMO d20 — a proficiência decide a PRÓPRIA banda, não só a magnitude",
      len(memorias_evento(MES, "forage_seleta")) == 1, str(banda_mes))

_mk_char("nunca-colheu-p55", "Nunca Colheu")  # skills.herbalismo: 5 na ficha, ZERO ato
check("US3: character.skills.herbalismo (5, na ficha) NUNCA é lido — "
     "quem nunca colheu tem proficiência 0, só memoria.proficiencies_for decide",
      motor.proficiencies_for("nunca-colheu-p55").get("herbalismo", -1) == 0.0,
      str(motor.proficiencies_for("nunca-colheu-p55")))

print()
if FAILS:
    print(f"Fase 55 (Colher, spec 054): {len(FAILS)} FALHA(S): " + "; ".join(FAILS))
    sys.exit(1)
print("Fase 55 (Colher, spec 054) OK.")
