"""Auto-teste da Fase 54 — Acender fogo (spec 053, US1..US3 + fundação).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx` para os enums.

  - FUNDAÇÃO: `trabalho` cego ao arquivo de entidade; `resultado` com e sem
    `extinto`; `resolver_vencidas` genérica; DOMAINS com `fogo`; `vezes` pesando
    na proficiência
  - US1: gate de combustibilidade recusa sem dado/consumo; o êxito cria o object;
    a falha preserva os materiais; a recusa RENOVA e o êxito NÃO
  - US2: a fonte entra em cook_fonte/forge_fonte e a prosa desce à Mente
  - US3: o prazo apaga, marca `state.extinto_em`, some dos TRÊS pontos de
    enumeração e avisa os presentes — sem chamar o Árbitro

Uso:  python3 selftest_phase54.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test54-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
import validator  # noqa: E402
from motor import trabalho  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid, name, dex=10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: {dex}\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nAlguém que acende fogo.\n", encoding="utf-8")
    return d


def _mk_item(parent, iid, name, desc, weight_kg=1.0):
    d = parent / iid
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {iid}\nname: {name}\nsize: P\nweight_kg: {weight_kg}\n"
        f"origin: editorial\n---\n{desc}\n", encoding="utf-8")
    return d


def _mk_object(parent, oid, name, desc):
    d = parent / oid
    d.mkdir(parents=True, exist_ok=True)
    (d / "object.md").write_text(
        f"---\ntype: object\nid: {oid}\nname: {name}\norigin: editorial\n---\n{desc}\n",
        encoding="utf-8")
    return d


# ============================================================================ #
# FUNDAÇÃO (T014) — `trabalho` cego ao tipo, `resultado`, resolução genérica
# ============================================================================ #

_LOC = motor.WORLD_DIR / TAVERNA
_obj = _mk_object(_LOC, "fogo-de-teste", "Fogueira de teste", "Chama viva sobre gravetos.")
_fm, _body = motor.io.read_doc(_obj / "object.md")
_fm["trabalho"] = {"tool": "kindle_fire", "pronto_ts": time.time() - 1,
                   "resultado": {"nome": "Cinzas de teste", "extinto": True,
                                 "description": "Cinzas frias."}}
motor.io.write_doc(_obj / "object.md", _fm, _body)

check("FR-010: `trabalho.ler` enxerga o bloco num object.md",
      (trabalho.ler(_obj) or {}).get("tool") == "kindle_fire")
check("FR-010: `vencidas_por_prazo` varre object.md, não só item.md",
      any(pasta == _obj for pasta, _ in trabalho.vencidas_por_prazo()))
check("FR-009: object com bloco `trabalho` válido passa no World Validator",
      validator.validate(motor.io.read_doc(_obj / "object.md")[0]) == [])
check("FR-010: object com DOIS relógios é recusado pelo validador (buraco fechado)",
      validator.validate({"type": "object", "id": "x", "name": "X",
                          "trabalho": {"tool": "t", "pronto_ts": 1,
                                       "tempo_necessario_s": 2}}) != [])

_char_pres = _mk_char("testemunha-do-fogo", "Testemunha")
trabalho.resolver_vencidas()
_fm2, _body2 = motor.io.read_doc(_obj / "object.md")
check("FR-011: o prazo transformou a entidade (nome e corpo das cinzas)",
      _fm2.get("name") == "Cinzas de teste" and "Cinzas frias" in _body2)
check("FR-011: o bloco `trabalho` saiu inteiro",
      "trabalho" not in _fm2)
check("FR-011: o arquivo CONTINUA no disco com a data da extinção (Princípio IV)",
      (_obj / "object.md").exists()
      and isinstance((_fm2.get("state") or {}).get("extinto_em"), int))
check("FR-012: quem estava no lugar recebeu o fato do apagamento",
      "apagou" in (motor.io.read_doc(_char_pres / "character.md")[0]
                   .get("status") or {}).get("action", ""))

check("FR-026: `fogo` entrou em DOMAINS", "fogo" in validator.DOMAINS)
_pr = motor.memoria.primitivas._peso_das_repeticoes
check("FR-028: memória sem `vezes` pesa 1,0 (não-regressão)", _pr({}) == 1.0)
check("FR-028: memória com `vezes: 13` pesa 4,0", _pr({"vezes": 13}) == 4.0)
# FR-029 de verdade: renovar NÃO pode escalar `intensity` — escalar reconstruiria o
# dano que criou a recorrência (o não-evento insistido virando o fato mais importante
# da vida do personagem). O que cresce é a prática contabilizada, nunca a saliência.
_mp = motor.memoria.primitivas
_alvo = _mk_char("praticante-do-fogo", "Praticante")
for _ in range(3):
    _mp._remember_recurring(_alvo, "Tentei acender e não pegou.", evento="kindle_falha",
                            about="acender\x00nao_pegou", involved=[], intensity="small",
                            frag="tentei")
_recs = [m for m in _mp._iter_memories_in(_alvo) if m.get("evento") == "kindle_falha"]
check("FR-029: três repetições viram UM arquivo, não três", len(_recs) == 1, str(len(_recs)))
check("FR-029: `vezes` cresceu para 3", (_recs[0].get("vezes") if _recs else 0) == 3)
check("FR-029: `intensity` NÃO escalou — continua 'small'",
      (_recs[0].get("intensity") if _recs else None) == "small")
check("FR-028: e a prática das 3 vezes agora PESA (1,5x contra 1,0x)",
      abs(_pr(_recs[0]) - 1.5) < 1e-9 if _recs else False)


# ============================================================================ #
# US1 (T025) — a fogueira nasce, a recusa ensina, a falha preserva
# ============================================================================ #

_ator = _mk_char("acendedor", "Acendedor", dex=14)
_mk_item(_LOC, "gravetos-secos", "Gravetos secos",
         "Feixe de gravetos secos, casca solta e resina perfumada.")
_mk_item(_LOC, "pedra-do-rio", "Pedra do rio",
         "Uma pedra lisa e fria, arredondada pela água.")


def _acender(materiais, comb, fav, dur=5):
    return motor.apply_resolution("acendedor", {"fogo_ops": [{
        "materiais": materiais, "combustibilidade": comb, "favorabilidade": fav,
        "duracao": dur, "nome": "Fogueira de gravetos",
        "descricao": "Uma fogueira baixa de gravetos secos, com brasas firmes sob a chama.",
        "nome_final": "Cinzas de gravetos",
        "descricao_final": "Cinzas frias e gravetos enegrecidos."}]})


def _objects_na_cena():
    _, objs, _ = motor.io._scene_entities(_LOC)
    return objs


# --- gate de mérito: pedra não queima ---
_n_antes = len(_objects_na_cena())
_r = _acender(["pedra-do-rio"], comb=0, fav=8)
check("FR-005: combustibilidade 0 é RECUSADA",
      any(x.get("regra") == "nao_queima" for x in _r.get("rejected") or []), str(_r))
check("FR-005: a recusa não criou fogo nenhum", len(_objects_na_cena()) == _n_antes)
check("FR-005: a recusa NÃO consumiu a pedra", (_LOC / "pedra-do-rio").exists())
check("FR-006: a recusa de mérito não gastou dado",
      not (_r.get("rolls") or []), str(_r.get("rolls")))

# --- a recusa repetida RENOVA (não vira N memórias) ---
_acender(["pedra-do-rio"], comb=0, fav=8)
_mems = [m for m in motor.memoria.primitivas._iter_memories("acendedor")
         if m.get("evento") == "kindle_refused"]
check("FR-021: duas recusas viram UM arquivo de memória", len(_mems) == 1, str(len(_mems)))
check("FR-021: e `vezes` cresceu para 2", (_mems[0].get("vezes") if _mems else 0) == 2)
# `nenhuma` é o default para evento fora do mapa de domínios, e `proficiencies_for`
# nunca o soma — é a forma correta de "não ensina", não a ausência da chave.
check("FR-023: recusa de mérito NÃO alimenta proficiência (domain nenhuma/ausente)",
      all(m.get("domain") in (None, "nenhuma") for m in _mems),
      str([m.get("domain") for m in _mems]))

# --- falha de rolagem: material preservado ---
_D20_REAL = motor.rolagem._roll_d20
motor.rolagem._roll_d20 = lambda: 1
_r = _acender(["gravetos-secos"], comb=8, fav=3)
check("FR-006: rolagem ruim NÃO acende",
      any(x.get("regra") == "nao_pegou" for x in _r.get("rejected") or []), str(_r))
check("FR-008: a falha PRESERVA os materiais (diverge de cook de propósito)",
      (_LOC / "gravetos-secos").exists())
check("FR-008: e não nasceu object nenhum", len(_objects_na_cena()) == _n_antes)

# --- êxito ---
motor.rolagem._roll_d20 = lambda: 20
_r = _acender(["gravetos-secos"], comb=8, fav=6)
check("FR-009: a ignição bem-sucedida foi aplicada", bool(_r.get("applied")), str(_r))
check("FR-008: o material foi consumido só AGORA", not (_LOC / "gravetos-secos").exists())
_objs = _objects_na_cena()
_fogo_id = next((o for o in _objs if o.startswith("fogo-")), None)
check("FR-009: nasceu exatamente UM object de fogo na cena", _fogo_id is not None, str(_objs))
_ffm, _fbody = motor.io.read_doc(_LOC / _fogo_id / "object.md")
check("FR-009: é um `object`, não um item", _ffm.get("type") == "object")
check("FR-014: a prosa dele afirma a chama", "brasas" in _fbody)
check("FR-009: tem bloco `trabalho` de PRAZO", "pronto_ts" in (_ffm.get("trabalho") or {}))
check("FR-009: e NÃO guarda `ator` (o fogo não prende quem o acendeu)",
      "ator" not in (_ffm.get("trabalho") or {}))
check("FR-009: quem acendeu NÃO ficou ocupado", not trabalho.is_busy(_ator))
check("FR-009: o object passa no World Validator", validator.validate(_ffm) == [])

# --- proficiência: cada êxito é fato PRÓPRIO ---
motor.rolagem._roll_d20 = lambda: 20
_mk_item(_LOC, "mais-gravetos", "Mais gravetos", "Outro feixe de gravetos bem secos.")
_acender(["mais-gravetos"], comb=8, fav=6)
_exitos = [m for m in motor.memoria.primitivas._iter_memories("acendedor")
           if m.get("evento") == "kindle_fire"]
check("FR-022: dois êxitos viram DUAS memórias (sem `about`) — é o que faz a prática somar",
      len(_exitos) == 2, str(len(_exitos)))
check("FR-023: o êxito carimba `domain: fogo`",
      all(m.get("domain") == "fogo" for m in _exitos))
check("FR-027: a proficiência em `fogo` subiu do zero",
      motor.memoria.proficiencies_for("acendedor").get("fogo", 0) > 0,
      str(motor.memoria.proficiencies_for("acendedor")))
motor.rolagem._roll_d20 = _D20_REAL

# ============================================================================ #
# US2 (T026–T029) — o mesmo fogo serve a dois domínios, e A Mente o enxerga
# ============================================================================ #

_ctx = motor.get_context("acendedor")
_cand = arbiter.scene_candidates(arbiter._scene_index(_ctx))

check("FR-015: a fonte criada entra em `cook_fonte` SEM tocar em arbiter.py",
      _fogo_id in (_cand or {}).get("cook_fonte", []), str((_cand or {}).get("cook_fonte")))
check("FR-015: e em `forge_fonte` pelo mesmo caminho",
      _fogo_id in (_cand or {}).get("forge_fonte", []), str((_cand or {}).get("forge_fonte")))
check("FR-016: a fonte NÃO entra em `kindle_materiais` (fogo não é combustível)",
      _fogo_id not in (_cand or {}).get("kindle_materiais", []))

# FR-013 — a PROSA desce à Mente, não só o nome. Sem isto, uma entidade cujo
# significado inteiro vive na descrição seria muda para quem interpreta.
_obj_ctx = next((o for o in _ctx.get("objects_present", []) if o.get("id") == _fogo_id), None)
check("FR-013: o fogo aparece em `objects_present`", _obj_ctx is not None)
check("FR-013: e carrega a `description` — A Mente lê a prosa, não só o nome",
      bool((_obj_ctx or {}).get("description"))
      and "brasas" in ((_obj_ctx or {}).get("description") or ""),
      str(_obj_ctx))

# A régua de cook lê a MESMA prosa, pela primitiva do Motor (não pelo bundle)
_desc = motor.descricao_de(_fogo_id) or {}
check("FR-016: `io.descricao_de` entrega a prosa do fogo às réguas",
      "brasas" in (_desc.get("descricao") or ""), str(_desc))
check("FR-016: acender NÃO declarou uso — nenhum campo diz cozinha/forja",
      not any(k in _ffm for k in ("fogo", "calor", "uso", "temperatura")), str(list(_ffm)))

# ============================================================================ #
# US3 (T038) — o prazo apaga, deixa vestígio DATADO e some dos TRÊS pontos
# ============================================================================ #

# Vence o prazo do fogo criado na US1, sem esperar 60 minutos de verdade.
_ffm2, _fbody2 = motor.io.read_doc(_LOC / _fogo_id / "object.md")
_ffm2["trabalho"]["pronto_ts"] = time.time() - 1
motor.io.write_doc(_LOC / _fogo_id / "object.md", _ffm2, _fbody2)

_ASK_CHAMADO = []
_ctx_apagou = None
try:
    _ctx_apagou = motor.get_context("acendedor")   # é aqui que a resolução preguiçosa roda
except Exception as e:                              # pragma: no cover
    check("US3: get_context rodou a resolução sem erro", False, str(e))

_ffm3, _fbody3 = motor.io.read_doc(_LOC / _fogo_id / "object.md")
check("FR-011: o arquivo do fogo CONTINUA no disco (nada é deletado)",
      (_LOC / _fogo_id / "object.md").exists())
check("FR-011: virou cinzas — nome e prosa trocados",
      _ffm3.get("name") == "Cinzas de gravetos" and "enegrecidos" in _fbody3)
check("FR-011: o bloco `trabalho` saiu inteiro", "trabalho" not in _ffm3)
check("FR-011: e ganhou a DATA da extinção — o vestígio que a investigação vai ler",
      isinstance((_ffm3.get("state") or {}).get("extinto_em"), int),
      str(_ffm3.get("state")))
check("FR-011: `state.extinto_em` passa no World Validator",
      validator.validate(_ffm3) == [])

# --- os TRÊS pontos de filtro, afirmados SEPARADAMENTE ---
# Esquecer um é o modo de falha que a spec 046 registra ter acontecido de verdade.
_, _objs_cena, _ = motor.io._scene_entities(_LOC)
check("FR-011a ponto 1/3: sumiu de `io._scene_entities` (choke-point dos enums)",
      _fogo_id not in _objs_cena, str(list(_objs_cena)))
_alcance = motor.percepcao.consultas._walk_scene(_LOC, lambda *a: False)
check("FR-011a ponto 2/3: sumiu de `_walk_scene` (alcance/visão/oferta)",
      _fogo_id not in _alcance, str(list(_alcance)))
check("FR-011a ponto 3/3: sumiu de `objects_present` (o bundle da Mente)",
      not any(o.get("id") == _fogo_id
              for o in (_ctx_apagou or {}).get("objects_present", [])))

_cand2 = arbiter.scene_candidates(arbiter._scene_index(_ctx_apagou))
check("SC-006: e sumiu dos enums de fonte de calor, sem regra nova",
      _fogo_id not in _cand2.get("cook_fonte", [])
      and _fogo_id not in _cand2.get("forge_fonte", []))

check("FR-012: quem estava no lugar soube que o fogo se apagou",
      "apagou" in (motor.io.read_doc(_ator / "character.md")[0]
                   .get("status") or {}).get("action", ""),
      str((motor.io.read_doc(_ator / "character.md")[0].get("status") or {}).get("action")))

# --- SC-006a: o acúmulo não existe ---
# Apaga tudo o que ainda arde (a US1 deixou uma segunda fogueira viva) para que a
# base seja estável, e SÓ ENTÃO mede.
def _vencer_todos_os_fogos():
    for _o, _pasta in list(motor.io._scene_entities(_LOC)[1].items()):
        _f, _b = motor.io.read_doc(_pasta / "object.md")
        if "trabalho" in _f:
            _f["trabalho"]["pronto_ts"] = time.time() - 1
            motor.io.write_doc(_pasta / "object.md", _f, _b)
    trabalho.resolver_vencidas()


_vencer_todos_os_fogos()
_n_objs_base = len(motor.io._scene_entities(_LOC)[1])
_n_vestigios_base = sum(1 for d in _LOC.iterdir() if d.is_dir()
                        and (d / "object.md").exists()
                        and motor.io.esta_extinto(motor.io.read_doc(d / "object.md")[0]))
_D20_REAL2 = motor.rolagem._roll_d20
motor.rolagem._roll_d20 = lambda: 20
for _i in range(10):
    _mk_item(_LOC, f"lenha-{_i}", f"Lenha {_i}", "Um feixe de lenha bem seca.")
    _acender([f"lenha-{_i}"], comb=8, fav=6)
    _vencer_todos_os_fogos()
motor.rolagem._roll_d20 = _D20_REAL2

_n_objs_fim = len(motor.io._scene_entities(_LOC)[1])
check("SC-006a: dez fogueiras acesas e apagadas NÃO aumentam os objects da cena",
      _n_objs_fim == _n_objs_base, f"{_n_objs_base} -> {_n_objs_fim}")
_cinzas = [d for d in _LOC.iterdir() if d.is_dir() and (d / "object.md").exists()
           and motor.io.esta_extinto(motor.io.read_doc(d / "object.md")[0])]
check("FR-011: mas os dez vestígios NOVOS existem no disco, cada um com sua data",
      len(_cinzas) == _n_vestigios_base + 10,
      f"{_n_vestigios_base} + 10 esperado, achou {len(_cinzas)}")
check("SC-006a: e o enum de fonte de calor também não cresceu",
      len(arbiter.scene_candidates(arbiter._scene_index(
          motor.get_context("acendedor"))).get("cook_fonte", [])) <= _n_objs_base + 1)

shutil.rmtree(_tmp, ignore_errors=True)
print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("Fase 54 (Acender fogo, spec 053) OK.")
