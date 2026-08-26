"""Auto-teste da Fase 56 — Preparar (spec 055, US1+US2+US3).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com `ask`
forçado) para o comportamento da GUARDA (curto-circuito, dedup, exclusividade
`is_busy`). Cobre:

  - US1: combinação válida + recipiente válido -> ingredientes removidos no ato; a
    peça em processo existe na cena (molde EXATO da panela no fogo); o remédio só
    materializa depois de `pronto_ts`, via `get_context`; o RECIPIENTE nunca é tocado
  - US2: recipiente/preparabilidade 0 -> recusa determinística, com memória
    RENOVADA por `about`; erro corrigível (id/alcance) -> sem memória; `ja_preparando`
    bloqueia 2ª tentativa enquanto uma peça pende
  - US3: proficiência em "botica" soma DIRETO na rolagem de favorabilidade (decide a
    banda, não só a magnitude depois) — curva assintótica sem teto, mesmo mecanismo
    de "cozinha"/"herbalismo"; `character.skills.alquimia`/`herbalismo` NUNCA lidos

Uso:  python3 selftest_phase56.py
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
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test56-"))
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
        f"skills:\n  herbalismo: 5\n  alquimia: 4\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_item(parent_folder: Path, item_id: str, name: str, descricao: str,
            weight_kg: float = 0.2):
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


def _hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def peca_de(cid: str):
    """A PEÇA EM PROCESSO do personagem (spec 055): a peça pendente com relógio de
    PRAZO ligada a ele — mesmo papel que `panela_de` cumpre em `cook`."""
    achado = motor.trabalho.peca_pendente_de(motor.find_character_folder(cid),
                                             apenas_prazo=True)
    return achado[0] if achado else None


def preparando_de(cid: str):
    pasta = peca_de(cid)
    return motor.trabalho.ler(pasta) if pasta else None


def memorias_evento(cid: str, evento: str) -> list:
    return [fm for fm in motor.memoria._iter_memories(cid) if fm.get("evento") == evento]


def brew_op(ingredientes, recipiente, recipiente_adequado=7, preparabilidade=7,
           favorabilidade=5, duracao=0, nome="Preparo de Teste",
           descricao_ruim="malfeito", descricao_media="comum", descricao_otima="ótimo"):
    return {"ingredientes": list(ingredientes), "recipiente": recipiente,
            "recipiente_adequado": recipiente_adequado, "preparabilidade": preparabilidade,
            "favorabilidade": favorabilidade, "duracao": duracao, "nome": nome,
            "descricao_ruim": descricao_ruim, "descricao_media": descricao_media,
            "descricao_otima": descricao_otima}


def _forcar_pronto(cid: str):
    pasta = peca_de(cid)
    motor.trabalho.atualizar(pasta, pronto_ts=time.time() - 1)


def _planta_memoria_botica(cid: str, intensity: str = "giant"):
    folder = motor.find_character_folder(cid)
    motor.memoria._write_memory(folder, "uma sessão e tanto na botica",
                                intensity=intensity, domain="botica", involved=[cid])


force = motor._roll_d20

# =========================================================================== #
# US1 — preparar de verdade: ingredientes somem no ato, remédio materializa só
# depois do tempo real; o recipiente NUNCA é tocado
# =========================================================================== #

_mk_char("boticario-p56", "Boticário de Teste")
BOT = "boticario-p56"
bot_folder = motor.find_character_folder(BOT)
taverna_folder = bot_folder.parent

_mk_object(taverna_folder, "almofariz-p56", "Almofariz",
          "Um almofariz de pedra, gasto de uso, com um pilão ao lado.")
recipiente_arquivo = taverna_folder / "almofariz-p56" / "object.md"
hash_antes = _hash(recipiente_arquivo)

_mk_item(bot_folder, "raiz-torta-p56", "Raiz-torta", "Uma raiz nodosa e escura.")
_mk_item(bot_folder, "erva-sao-joao-p56", "Erva-de-São-João", "Folhas miúdas, flor amarela.")

check("US1 (baseline): peça em processo não existe antes de preparar",
      peca_de(BOT) is None, str(preparando_de(BOT)))

motor._roll_d20 = lambda: 20  # banda ótima garantida (favorabilidade=5, dc=10)
motor.apply_resolution(BOT, {"botica_ops": [
    brew_op(["raiz-torta-p56", "erva-sao-joao-p56"], "almofariz-p56",
           favorabilidade=5, duracao=2, nome="Tônico de Raiz-torta",
           descricao_otima="um líquido escuro, de cheiro amargo, no ponto")]})
motor._roll_d20 = force

check("US1: ingredientes REMOVIDOS imediatamente (consumo no ATO)",
      not (bot_folder / "raiz-torta-p56").exists()
      and not (bot_folder / "erva-sao-joao-p56").exists())
check("US1: o RECIPIENTE não foi tocado — hash idêntico",
      _hash(recipiente_arquivo) == hash_antes)

pendente = preparando_de(BOT)
check("US1: peça em processo gravada com pronto_ts FUTURO e `ator`",
      isinstance(pendente, dict) and pendente.get("pronto_ts", 0) > time.time()
      and pendente.get("ator") == BOT, str(pendente))
peca_folder = peca_de(BOT)
check("US1: a peça em processo EXISTE na cena e ainda não é o remédio",
      peca_folder is not None and (peca_folder / "item.md").exists()
      and motor.trabalho.ler(peca_folder) is not None)

mem_otima_ato = memorias_evento(BOT, "brew_otimo")
check("US1: memória 'medium' positiva já gravada NO ATO (domain='botica')",
      len(mem_otima_ato) == 1 and mem_otima_ato[0].get("intensity") == "medium"
      and mem_otima_ato[0].get("domain") == "botica", str(mem_otima_ato))

remedio_id = peca_folder.name
_forcar_pronto(BOT)
motor.get_context(BOT)  # dispara trabalho.resolver_vencidas()
check("US1: após o tempo se cumprir, a PEÇA vira o remédio, onde ela estiver",
      (taverna_folder / remedio_id / "item.md").exists()
      and motor.trabalho.ler(taverna_folder / remedio_id) is None)
remedio_fm, remedio_body = motor.read_doc(taverna_folder / remedio_id / "item.md")
check("US1: o nome do remédio não carrega mais '(preparando)'",
      remedio_fm.get("name") == "Tônico de Raiz-torta", str(remedio_fm.get("name")))
check("US1: a description do remédio é a candidata 'ótima' (banda que saiu)",
      remedio_body.strip() == "um líquido escuro, de cheiro amargo, no ponto", remedio_body)
check("US1: peso do remédio = soma determinística dos ingredientes (0.2+0.2=0.4)",
      abs(float(remedio_fm.get("weight_kg") or 0) - 0.4) < 1e-6, str(remedio_fm.get("weight_kg")))
check("US1: o RECIPIENTE segue intocado mesmo depois da materialização",
      _hash(recipiente_arquivo) == hash_antes)

# segredo: nenhuma nota/proficiência aparece no manifest da tool
import types as _types_mod
import arbiter_tools.base as _face_mod
face_brew = _face_mod.build_face(motor.registro.get_spec("brew"), "brew",
                                 _types_mod.SimpleNamespace(
                                     cand={"brew_ingredientes": [], "brew_recipiente": []},
                                     actor_id=BOT))
props_brew = (face_brew or {}).get("parameters", {}).get("properties", {})
check("US1: nenhuma das quatro notas (nem nome/descriptions candidatas) aparece na FACE",
      not ({"recipiente_adequado", "preparabilidade", "favorabilidade", "duracao", "nome",
           "descricao_ruim", "descricao_media", "descricao_otima"} & set(props_brew)),
      str(sorted(props_brew)))

# =========================================================================== #
# US2 — os dois gates de admissão recusam com memória RENOVADA; erro corrigível
# sem memória; `ja_preparando` bloqueia nova tentativa enquanto uma peça pende
# =========================================================================== #

_mk_char("recusado-p56", "Recusado de Teste")
REC = "recusado-p56"
rec_folder = motor.find_character_folder(REC)
rec_taverna = rec_folder.parent
_mk_object(rec_taverna, "bota-p56", "Bota Velha", "Uma bota de couro gasto, sem serventia.")
_mk_object(rec_taverna, "almofariz-rec-p56", "Almofariz", "Um almofariz de pedra comum.")
_mk_item(rec_folder, "moeda-p56", "Moeda", "Uma moeda de cobre qualquer.")
_mk_item(rec_folder, "prego-p56", "Prego", "Um prego enferrujado.")

motor.apply_resolution(REC, {"botica_ops": [
    brew_op(["moeda-p56"], "bota-p56", recipiente_adequado=0)]})
mem_sem_rec = memorias_evento(REC, "brew_refused_recipiente")
check("US2: RECIPIENTE_ADEQUADO 0 -> recusa de mérito, memória small negativa, "
     "renovada por `about`",
      len(mem_sem_rec) == 1 and mem_sem_rec[0].get("intensity") == "small"
      and mem_sem_rec[0].get("about", "").startswith("preparar\x00sem_recipiente"),
      str(mem_sem_rec))
check("US2: recusa por RECIPIENTE_ADEQUADO 0 NÃO consome o ingrediente",
      (rec_folder / "moeda-p56").exists())

motor.apply_resolution(REC, {"botica_ops": [
    brew_op(["moeda-p56", "prego-p56"], "almofariz-rec-p56", preparabilidade=0)]})
mem_combo = memorias_evento(REC, "brew_refused_combo")
check("US2: PREPARABILIDADE 0 -> recusa de mérito, sem consumir ingrediente",
      len(mem_combo) == 1 and (rec_folder / "moeda-p56").exists()
      and (rec_folder / "prego-p56").exists())

# ja_preparando: uma peça pendente bloqueia nova tentativa
_mk_item(rec_folder, "erva-ocupado-p56", "Erva", "Uma erva qualquer.")
_mk_item(rec_folder, "erva-ocupado2-p56", "Erva", "Outra erva qualquer.")
motor.apply_resolution(REC, {"botica_ops": [
    brew_op(["erva-ocupado-p56"], "almofariz-rec-p56", favorabilidade=5, duracao=5)]})
check("US2: uma peça em processo agora está pendente para REC",
      preparando_de(REC) is not None)
res_ocupado = motor.apply_resolution(REC, {"botica_ops": [
    brew_op(["erva-ocupado2-p56"], "almofariz-rec-p56")]})
check("US2 (ja_preparando): 2ª tentativa é recusada — ator já ocupado com um preparo",
      any(r.get("regra") == "ja_preparando" for r in res_ocupado.get("rejected", []))
      and (rec_folder / "erva-ocupado2-p56").exists(),
      str(res_ocupado.get("rejected")))

# dedup semântico (ctx.brewed_asked): 1ª tentativa precisa ser recusa (senão o
# anti-loop genérico de `execute` já barra a repetição idêntica antes da guarda).
_mk_char("dedup-p56", "Dedup de Teste")
DED = "dedup-p56"
ded_folder = motor.find_character_folder(DED)
_mk_object(ded_folder.parent, "bota-dedup-p56", "Bota Velha", "Uma bota sem serventia.")
_mk_item(ded_folder, "erva-dedup-p56", "Erva", "Uma erva qualquer.")
ctx_dedup = arbiter.build_ctx(
    motor.get_context(DED),
    ask=lambda _s, _u: ('{"recipiente_adequado": 0, "preparabilidade": 5, '
                        '"favorabilidade": 5, "duracao": 0, "nome": "", '
                        '"descricao_ruim": "", "descricao_media": "", "descricao_otima": ""}'),
    prosa={"acao": "preparar na bota"})
res_dedup_1 = ctx_dedup.execute("brew", {"ingredientes": ["erva-dedup-p56"],
                                         "recipiente": "bota-dedup-p56"})
res_dedup_2 = ctx_dedup.execute("brew", {"ingredientes": ["erva-dedup-p56"],
                                         "recipiente": "bota-dedup-p56"})
check("US2 (dedup, 1ª tentativa): recusa determinística por recipiente",
      not res_dedup_1[0].get("ok"), str(res_dedup_1[0]))
check("US2 (dedup, 2ª tentativa): o MESMO conjunto+recipiente é barrado pela guarda "
     "(`ctx.brewed_asked`), sem reconsultar as réguas",
      not res_dedup_2[0].get("ok")
      and "já foi tentado" in (res_dedup_2[0].get("erro") or ""), str(res_dedup_2[0]))

# =========================================================================== #
# US3 — proficiência em "botica" soma DIRETO na rolagem de favorabilidade,
# decidindo a PRÓPRIA banda com o MESMO d20; skills.herbalismo/alquimia NUNCA lidos
# =========================================================================== #

_mk_char("novato-p56", "Novato de Teste")
_mk_char("mestre-p56", "Mestre de Teste")
NOV, MES = "novato-p56", "mestre-p56"
nov_folder = motor.find_character_folder(NOV)
mes_folder = motor.find_character_folder(MES)
_mk_object(nov_folder.parent, "almofariz-nov-p56", "Almofariz", "Um almofariz de pedra.")
_mk_object(mes_folder.parent, "almofariz-mes-p56", "Almofariz", "Um almofariz de pedra.")
_mk_item(nov_folder, "erva-nov-p56", "Erva", "Uma erva qualquer.")
_mk_item(mes_folder, "erva-mes-p56", "Erva", "Uma erva qualquer.")
_planta_memoria_botica(MES, intensity="giant")

motor._roll_d20 = lambda: 10  # d20 FIXO idêntico para os dois; dc(favorabilidade=6) = 8
motor.apply_resolution(NOV, {"botica_ops": [
    brew_op(["erva-nov-p56"], "almofariz-nov-p56", favorabilidade=6)]})
motor.apply_resolution(MES, {"botica_ops": [
    brew_op(["erva-mes-p56"], "almofariz-mes-p56", favorabilidade=6)]})
motor._roll_d20 = force

check("US3: o NOVATO (proficiência 0) rendeu banda 'media' com o MESMO d20 fixo",
      len(memorias_evento(NOV, "brew")) == 1, str(memorias_evento(NOV, "brew")))
check("US3: o MESTRE (proficiência alta em 'botica') cruza para 'otima' com o "
     "MESMO d20 — a proficiência decide a PRÓPRIA banda",
      len(memorias_evento(MES, "brew_otimo")) == 1, str(memorias_evento(MES, "brew_otimo")))

_mk_char("nunca-preparou-p56", "Nunca Preparou")  # skills.herbalismo/alquimia na ficha, ZERO ato
check("US3: character.skills.herbalismo/alquimia NUNCA são lidos — quem nunca "
     "preparou tem proficiência 0, só memoria.proficiencies_for decide",
      motor.proficiencies_for("nunca-preparou-p56").get("botica", -1) == 0.0,
      str(motor.proficiencies_for("nunca-preparou-p56")))

print()
if FAILS:
    print(f"Fase 56 (Preparar, spec 055): {len(FAILS)} FALHA(S): " + "; ".join(FAILS))
    sys.exit(1)
print("Fase 56 (Preparar, spec 055) OK.")
