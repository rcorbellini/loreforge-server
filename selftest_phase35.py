"""Auto-teste da Fase 35 — Presença no mundo (spec 034).

Cobre as quatro User Stories da spec:
  - US1: deslocamento (partida/chegada) passa a ser testemunhável, pelo mesmo
    piso de saliência de golpe/furto/etc — código PRÓPRIO de
    `deslocamento.py`, nunca uma entrada em `_witness_facts`/`_finalize_turn`
  - US2: `ask_about` aceita um LUGAR além de pessoa, com enum real (cena atual
    + lugares conhecidos/reconhecidos)
  - US3: `ask_about`/`ask_directions` resolvem pergunta + registro numa
    chamada só; `hear_about` e o ramo `fonte` de `learn_routes` saem do
    manifest
  - US4: toda partida/chegada grava uma marca física (`rastro`) no lugar,
    independente de testemunha, com decaimento FÍSICO (≤48h)

Fixture: taverna(M) -20-> forja(P) -30-> pátio(G) -40-> mirante(P) — a MESMA
cadeia que a fase 16 (viagem longa) já usa, reaproveitada para o teste de
deslocamento testemunhado perna-a-perna.

Uso:  python3 server/selftest_phase35.py
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
import arbiter  # noqa: E402
import motor  # noqa: E402
import selftest_helpers  # noqa: E402
import validator  # noqa: E402

FAILS = []

TAVERNA, FORJA = "taverna-do-gancho", "forja-de-ferro"
PATIO, MIRANTE = "patio-das-brasas", "mirante-do-corvo"
ROTA_TF, ROTA_FP, ROTA_PM = "portao-lateral", "trilha-do-patio", "subida-do-corvo"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(loc: str, cid: str, name: str) -> None:
    d = motor.WORLD_DIR / loc / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n"
        f"  CHA: 10\nskills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")


def pasta(cid):
    return motor.find_character_folder(cid)


def onde(cid):
    return pasta(cid).parent.name


def planta_familiaridade(cid, sobre_id, texto):
    motor._write_memory(pasta(cid), texto, intensity="small", involved=[sobre_id])


def mems_de(cid):
    d = pasta(cid) / "memories"
    if not d.is_dir():
        return []
    return [motor.read_doc(p)[0] for p in d.glob("*.md")]


def rastros_em(loc):
    """Os rastros de um lugar — arquivos soltos em `<lugar>/rastros/`, o mesmo
    desenho de `memories/` (2026-08-30). Antes era uma PASTA por marca."""
    return list((motor.WORLD_DIR / loc / "rastros").glob("rastro-*.md"))


def res(**parts):
    base = {"narrative_hint": "age", "movement": None, "mutations": [],
            "item_transfers": [], "equip_ops": [], "lock_ops": [],
            "persuade_ops": [], "attack_ops": [], "carry_ops": [],
            "trade_ops": [], "persuade_give_ops": [], "steal_ops": [],
            "learn_ops": [], "hearsay_ops": [], "intentions": [],
            "promise_ops": [], "accuse_ops": [], "travel_ops": [],
            "rest_ops": [], "cura_ops": [], "memories": []}
    base.update(parts)
    return base


def andar(cid, rota):
    return motor.apply_resolution(cid, res(movement={"enter_route": rota}))


def adianta(cid):
    """Empurra o trânsito atual para o passado e deixa o mundo avançar
    (mesmo padrão da fase 16: `_resolve_arrivals` roda no world-touch)."""
    path = pasta(cid) / "character.md"
    fm, body = motor.read_doc(path)
    if not isinstance(fm.get("transit"), dict):
        return False
    fm["transit"]["arrive_ts"] = int(time.time()) - 1
    motor.write_doc(path, fm, body)
    motor.lazy_evaluate()
    return True


def chega(cid, limite=10):
    for _ in range(limite):
        if not adianta(cid):
            break


# =========================================================================== #
# US1 — deslocamento testemunhado (partida/chegada, piso de saliência)
# =========================================================================== #

print("\n--- US1: partida gera testemunha (só com familiaridade prévia) -------")

_mk_char(TAVERNA, "viajante-1", "Viajante")
_mk_char(TAVERNA, "vizinho-o1", "VizinhoO")
_mk_char(TAVERNA, "estranho-o1", "EstranhoO")
planta_familiaridade("vizinho-o1", "viajante-1", "Já cruzei com o Viajante antes.")

andar("viajante-1", ROTA_TF)

check("vizinho com familiaridade prévia ganha memória de partida",
      any(m.get("evento") == "witness_departure" for m in mems_de("vizinho-o1")),
      str(mems_de("vizinho-o1")))
check("estranho sem familiaridade NÃO ganha nada (piso de saliência)",
      not any(m.get("evento") == "witness_departure" for m in mems_de("estranho-o1")),
      str(mems_de("estranho-o1")))
check("domínio do evento é `deslocamento`",
      any(m.get("domain") == "deslocamento" for m in mems_de("vizinho-o1")
          if m.get("evento") == "witness_departure"))


print("\n--- US1: chegada gera testemunha (só com familiaridade prévia) -------")

_mk_char(FORJA, "vizinho-d1", "VizinhoD")
_mk_char(FORJA, "estranho-d1", "EstranhoD")
planta_familiaridade("vizinho-d1", "viajante-1", "Conheço o Viajante de vista.")

chega("viajante-1")

check("viajante realmente chegou à forja", onde("viajante-1") == FORJA, onde("viajante-1"))
check("vizinho no destino ganha memória de chegada",
      any(m.get("evento") == "witness_arrival" for m in mems_de("vizinho-d1")),
      str(mems_de("vizinho-d1")))
check("estranho no destino NÃO ganha nada",
      not any(m.get("evento") == "witness_arrival" for m in mems_de("estranho-d1")),
      str(mems_de("estranho-d1")))


print("\n--- US1: sem ninguém presente, nenhuma memória DE TERCEIRO nasce ------")

_mk_char(FORJA, "viajante-vazio", "ViajanteVazio")
antes = {p for p in motor.WORLD_DIR.rglob("mem-*.md")
         if "viajante-vazio" not in str(p)}
andar("viajante-vazio", ROTA_FP)
depois = {p for p in motor.WORLD_DIR.rglob("mem-*.md")
          if "viajante-vazio" not in str(p)}
novas = depois - antes
check("partida de lugar sem testemunha não cria NENHUMA memória de TERCEIRO"
      " (a própria memória do viajante não conta)",
      not novas, str(novas))


print("\n--- US1: viagem longa testemunha em CADA perna, não só no final ------")

_mk_char(TAVERNA, "longevo", "Longevo")
_mk_char(FORJA, "vizinho-i", "VizinhoI")  # verá a PASSAGEM pela forja
planta_familiaridade("vizinho-i", "longevo", "Já vi o Longevo por aqui.")
_mk_char(PATIO, "vizinho-p", "VizinhoP")  # verá a passagem pelo pátio
planta_familiaridade("vizinho-p", "longevo", "Conheço o Longevo.")
_mk_char(MIRANTE, "vizinho-m", "VizinhoM")  # verá a chegada final
planta_familiaridade("vizinho-m", "longevo", "O Longevo já esteve aqui.")

andar("longevo", ROTA_TF)         # taverna -> forja (perna 1)
chega("longevo")
andar("longevo", ROTA_FP)         # forja -> pátio (perna 2)
chega("longevo")
andar("longevo", ROTA_PM)         # pátio -> mirante (perna final)
chega("longevo")

check("chegou ao destino final (mirante)", onde("longevo") == MIRANTE, onde("longevo"))
check("testemunha na FORJA (perna intermediária) percebeu a passagem",
      any(m.get("evento") in ("witness_arrival", "witness_departure")
          for m in mems_de("vizinho-i")),
      str(mems_de("vizinho-i")))
check("testemunha no PÁTIO (perna intermediária) percebeu a passagem",
      any(m.get("evento") in ("witness_arrival", "witness_departure")
          for m in mems_de("vizinho-p")),
      str(mems_de("vizinho-p")))
check("testemunha no MIRANTE (destino final) percebeu a chegada",
      any(m.get("evento") == "witness_arrival" for m in mems_de("vizinho-m")),
      str(mems_de("vizinho-m")))


print("\n--- US1: a memória de testemunha diz O PARADEIRO, não só 'vi partir' --")

# Achado em teste exploratório (2026-07-30): a memória de testemunha dizia só
# "Vi Fulano partir" — sem direção, então perguntar o PARADEIRO de alguém não
# revelava nada de útil, mesmo com uma testemunha real. Corrigido: a prosa
# inclui "rumo a"/"vindo de", e o LUGAR (origem/destino) entra em `involved` —
# sem isso, perguntar sobre O LUGAR (US2) nunca achava estes episódios.

_mk_char(TAVERNA, "sumido-p", "SumidoP")
_mk_char(TAVERNA, "vizinho-par", "VizinhoPar")
planta_familiaridade("vizinho-par", "sumido-p", "Conheço o SumidoP de vista.")
_mk_char(TAVERNA, "curioso-par", "CuriosoPar")

andar("sumido-p", ROTA_TF)

_ev_partida = [m for m in mems_de("vizinho-par") if m.get("evento") == "witness_departure"]
check("a prosa da testemunha inclui o PARADEIRO (rumo a...)",
      _ev_partida and "rumo a" in _ev_partida[0].get("summary", ""),
      str(_ev_partida))

motor._roll_d20 = lambda: 20

# ITEM 52: o reconto pede ao mundo o Z (o que o informante DIZ) pelo MESMO `ctx.ask`
# que entrega a nota da régua. O dublê distingue pelo system: régua devolve NÚMERO,
# reconto devolve JSON. A suíte segue sem modelo — dublê, como antes.
def _ask_mundo(system, _user):
    if '{"conta"' in (system or ""):
        return '{"conta": "Contei o que sei, do jeito que me lembro."}'
    return "8"

_cap_par = []
selftest_helpers.resolve_scripted(
    {"action": "pergunta pelo paradeiro"}, motor.get_context("curioso-par"),
    [("ask_about", {"quem": "vizinho-par", "sobre": "sumido-p", "disposicao": 9})],
    ask=_ask_mundo, captured=_cap_par)
_visto_par = {"pessoa": _cap_par[0]}
check("perguntar SOBRE A PESSOA revela o paradeiro (rumo a...)",
      any("rumo a" in (e.get("content") or "")
          for e in _visto_par["pessoa"].get("episodios") or []),
      str(_visto_par["pessoa"]))

_mk_char(TAVERNA, "curioso-par2", "CuriosoPar2")
_cap_par2 = []
selftest_helpers.resolve_scripted(
    {"action": "pergunta sobre o lugar"}, motor.get_context("curioso-par2"),
    [("ask_about", {"quem": "vizinho-par", "sobre": TAVERNA, "disposicao": 9})],
    ask=_ask_mundo, captured=_cap_par2)
_visto_par2 = {"lugar": _cap_par2[0]}
check("perguntar SOBRE O LUGAR TAMBÉM acha o mesmo episódio de partida"
      " (o lugar entra em `involved`, não só quem se moveu)",
      any("SumidoP" in (e.get("content") or "")
          for e in _visto_par2["lugar"].get("episodios") or []),
      str(_visto_par2["lugar"]))


print("\n--- US1: prova de atomicidade — direto, sem arbiter.py/turno.py -------")

_mk_char(TAVERNA, "atomico-1", "Atomico1")
_mk_char(TAVERNA, "atomico-2", "Atomico2")
planta_familiaridade("atomico-2", "atomico-1", "Conheço o Atomico1.")
motor._witness_movement(pasta("atomico-1").parent, "atomico-1",
                                "witness_departure")
check("_witness_movement chamado DIRETO grava memória sem turno/arbiter",
      any(m.get("evento") == "witness_departure" for m in mems_de("atomico-2")),
      str(mems_de("atomico-2")))
_r0 = motor._enter_route_locked("atomico-1", ROTA_TF)
check("_enter_route_locked chamado DIRETO também testemunha (self-contained)",
      _r0.get("moved"), str(_r0))


# =========================================================================== #
# US2 — perguntar sobre um LUGAR, sem suspeito nomeado
# =========================================================================== #

print("\n--- US2: perguntar sobre um lugar devolve episódios reais -------------")

_mk_char(TAVERNA, "testemunha-l", "TestemunhaL")
_mk_char(TAVERNA, "perguntador-l", "PerguntadorL")
motor._write_memory(pasta("testemunha-l"), "Vi um furto acontecer bem aqui.",
                    intensity="medium", involved=[TAVERNA], evento="witness_theft")

motor._roll_d20 = lambda: 20
_cap_l = []
selftest_helpers.resolve_scripted(
    {"action": "pergunta sobre o lugar"}, motor.get_context("perguntador-l"),
    [("ask_about", {"quem": "testemunha-l", "sobre": TAVERNA, "disposicao": 9})],
    ask=_ask_mundo, captured=_cap_l)
_visto_l = {"r": _cap_l[0]}
check("episódio real do lugar é devolvido",
      bool(_visto_l["r"].get("episodios")), str(_visto_l["r"]))
check("reconto nasce no perguntador na mesma chamada",
      any(motor.memory_ouvido_de(m) == "testemunha-l"
          for m in mems_de("perguntador-l")),
      str(mems_de("perguntador-l")))


print("\n--- US2: sem episódio, resposta explícita de nada a contar ------------")

_mk_char(TAVERNA, "silencioso-l", "SilenciosoL")
_cap_l2 = []
selftest_helpers.resolve_scripted(
    {"action": "pergunta"}, motor.get_context("perguntador-l"),
    [("ask_about", {"quem": "silencioso-l", "sobre": TAVERNA, "disposicao": 9})],
    ask=_ask_mundo, captured=_cap_l2)
_visto_l2 = {"r": _cap_l2[0]}
check("sem episódio, `nada_a_contar` explícito, sem erro",
      _visto_l2["r"].get("ok") and _visto_l2["r"].get("nada_a_contar"),
      str(_visto_l2["r"]))


print("\n--- ITEM 52.2: pergunta SEM REFERENTE grava nos DOIS e é consultável ----")
# A distinção que a US2 acima protege: `sobre` que É entidade real e o informante não
# conhece segue SUCESSO honesto (o check anterior). O que muda aqui é a outra
# ausência — `sobre` que não é entidade NENHUMA. Medido na Nerissa: 148 de 152
# `ask_about` eram assim, todas voltavam em silêncio e sem memória, e ela repetiu a
# MESMA pergunta 23 vezes. Decisão do mantenedor (2026-08-13): memória nos DOIS,
# intensidade mínima, texto legível, consultável pelos dois.
_ASSUNTO52 = "nome do deus do santuario"


def _mems52(cid):
    d = motor.find_character_folder(cid) / "memories"
    return {p.name for p in d.glob("*.md")} if d.is_dir() else set()


_antes52 = {c: _mems52(c) for c in ("perguntador-l", "silencioso-l")}
_cap52 = []
selftest_helpers.resolve_scripted(
    {"action": "pergunta"}, motor.get_context("perguntador-l"),
    [("ask_about", {"quem": "silencioso-l", "sobre": _ASSUNTO52, "disposicao": 9})],
    ask=_ask_mundo, captured=_cap52)
_visto52 = {"r": _cap52[0]}

_novas52 = {c: _mems52(c) - _antes52[c] for c in _antes52}
check("grava memória nos DOIS lados (quem perguntou e quem foi perguntado)",
      len(_novas52["perguntador-l"]) == 1 and len(_novas52["silencioso-l"]) == 1,
      str({k: sorted(v) for k, v in _novas52.items()}))

_textos52 = {}
for _c, _ns in _novas52.items():
    for _n in _ns:
        _fm52, _corpo52 = motor.read_doc(
            motor.find_character_folder(_c) / "memories" / _n)
        _textos52[_c] = (_fm52, _corpo52.strip())

check("intensidade MÍNIMA nos dois (nada mudou no mundo — não pesa em régua)",
      all(fm.get("intensity") == "small" for fm, _ in _textos52.values()),
      str({c: fm.get("intensity") for c, (fm, _) in _textos52.items()}))
check("o ASSUNTO aparece no TEXTO — é onde ele pode morar, já que não é entidade",
      all(_ASSUNTO52 in corpo for _, corpo in _textos52.values()),
      str({c: corpo for c, (_, corpo) in _textos52.items()}))
check("o texto NOMEIA o outro (legível, não genérico)",
      "Silencioso" in _textos52["perguntador-l"][1]
      and "Perguntador" in _textos52["silencioso-l"][1],
      str({c: corpo for c, (_, corpo) in _textos52.items()}))
check("cada lado fala na PRÓPRIA voz (perguntei × me perguntou)",
      _textos52["perguntador-l"][1].startswith("Perguntei")
      and "me perguntou" in _textos52["silencioso-l"][1],
      str({c: corpo for c, (_, corpo) in _textos52.items()}))

# E O QUE FECHA O LAÇO: os DOIS têm de ACHAR isto no tick seguinte. Gravar sem poder
# consultar não resolveria nada — foi por isso que o `recall` passou a casar por TEXTO
# e não só por `involved` (o assunto não é entidade, não cabe em `involved`).
for _quem, _rot in (("perguntador-l", "quem perguntou"), ("silencioso-l", "quem foi perguntado")):
    _r52 = motor.recall(_quem, {"sobre": "o deus do santuario"})
    check(f"o recall de {_rot} ACHA a pergunta que não rendeu",
          "não guarda" not in _r52["lembra"], _r52["lembra"][:120])
# e não virou "acha tudo": pergunta sem relação nenhuma continua vazia
check("o recall NÃO passou a casar qualquer coisa (pergunta alheia segue vazia)",
      "não guarda" in motor.recall("perguntador-l", {"sobre": "dragões alados"})["lembra"])


print("\n--- US2: lugar fora do enum é recusado ---------------------------------")

_cap_l3 = []
selftest_helpers.resolve_scripted(
    {"action": "pergunta"}, motor.get_context("perguntador-l"),
    [("ask_about", {"quem": "testemunha-l", "sobre": MIRANTE, "disposicao": 9})],
    ask=_ask_mundo, captured=_cap_l3)
_visto_l3 = {"r": _cap_l3[0]}
check("lugar nunca conhecido/visitado é recusado, nunca aceito",
      not _visto_l3["r"].get("ok"), str(_visto_l3["r"]))


# =========================================================================== #
# US3 — perguntar numa chamada só (pessoa, lugar, caminho)
# =========================================================================== #

print("\n--- US3: ask_about extremos sem dado, faixa intermediária com dado ---")

_mk_char(TAVERNA, "fonte-3", "Fonte3")
_mk_char(TAVERNA, "pergunta-3", "Pergunta3")
motor._write_memory(pasta("fonte-3"), "Vi algo acontecer.",
                    intensity="medium", involved=[TAVERNA])


def _ask(disposicao):
    """spec 043: a nota NÃO vem mais em `args` — a capacidade a pede ao mundo por
    `ctx.ask`. O ponto de injeção do teste passa a ser esse, que é o caminho real."""
    _cap = []
    selftest_helpers.resolve_scripted(
        {"action": "pergunta"}, motor.get_context("pergunta-3"),
        [("ask_about", {"quem": "fonte-3", "sobre": TAVERNA})],
        # o dublê serve aos DOIS usos do `ask` (item 52): a NOTA da régua e o
        # Z do reconto.
        ask=lambda _sys, _usr: (
            '{"conta": "Contei o que sei dele."}'
            if '{"conta"' in (_sys or "") else str(disposicao)),
        captured=_cap)
    return _cap[0]


def _boom():
    raise AssertionError("rolagem não deveria acontecer no extremo")


motor._roll_d20 = _boom
r0 = _ask(0)
check("disposicao 0 recusa SEM dado", not r0.get("ok"), str(r0))
r10 = _ask(10)
check("disposicao 10 registra SEM dado", r10.get("registrado"), str(r10))

motor._roll_d20 = lambda: 15
_mk_char(TAVERNA, "pergunta-3b", "Pergunta3b")
_cap_mid = []
selftest_helpers.resolve_scripted(
    {"action": "pergunta"}, motor.get_context("pergunta-3b"),
    [("ask_about", {"quem": "fonte-3", "sobre": TAVERNA, "disposicao": 5})],
    ask=_ask_mundo, captured=_cap_mid)
rmid = _cap_mid[0]
check("faixa intermediária resolve com uma rolagem (não explode)",
      rmid is not None, str(rmid))


print("\n--- US3: veredito único — repetir não re-rola -------------------------")

motor._roll_d20 = lambda: 20
_mk_char(TAVERNA, "pergunta-3c", "Pergunta3c")

_cap_dup = []
selftest_helpers.resolve_scripted(
    {"action": "pergunta duas vezes"}, motor.get_context("pergunta-3c"),
    [("ask_about", {"quem": "fonte-3", "sobre": TAVERNA, "disposicao": 9}),
     ("ask_about", {"quem": "fonte-3", "sobre": TAVERNA, "disposicao": 9})],
    ask=_ask_mundo, captured=_cap_dup)
_res_dup = {"r1": _cap_dup[0], "r2": _cap_dup[1]}
check("repetir a mesma pergunta no mesmo turno não produz um segundo veredito"
      " (recusada OU reconhecida como repetição — nunca um novo registro)",
      _res_dup["r2"].get("erro")
      or "já registrada" in str(_res_dup["r2"].get("nota", "")),
      str(_res_dup["r2"]))


print("\n--- US3: ask_directions resolve numa chamada só (regressão + fold) ---")

_ctx35 = motor.get_context("pergunta-3c")
_tools35 = {t["name"] for t in arbiter.build_tools(_ctx35)}
check("hear_about não existe mais no manifest", "hear_about" not in _tools35,
      str(_tools35))
_lr35 = [t for t in arbiter.build_tools(_ctx35) if t["name"] == "learn_routes"]
if _lr35:
    check("learn_routes não tem mais fonte/disposicao/atitude",
          not ({"fonte", "disposicao", "atitude"} & set(_lr35[0]["parameters"]["properties"])),
          str(sorted(_lr35[0]["parameters"]["properties"])))


# =========================================================================== #
# US4 — rastro físico (independente de testemunha, decaimento por relógio)
# =========================================================================== #

print("\n--- US4: partida/chegada deixam rastro MESMO sem testemunha -----------")

_mk_char(TAVERNA, "sozinho-r", "SozinhoR")
antes_r = set(rastros_em(TAVERNA))
andar("sozinho-r", ROTA_TF)
depois_r = set(rastros_em(TAVERNA))
check("marca nasce na ORIGEM mesmo sem ninguém para testemunhar",
      len(depois_r) > len(antes_r), str(depois_r - antes_r))

antes_rd = set(rastros_em(FORJA))
chega("sozinho-r")
depois_rd = set(rastros_em(FORJA))
check("marca nasce no DESTINO mesmo sem ninguém para testemunhar",
      len(depois_rd) > len(antes_rd), str(depois_rd - antes_rd))

_novo_rastro = list(depois_rd - antes_rd)[0]
_fm_rastro, _ = motor.read_doc(_novo_rastro)
check("a marca identifica quem passou e a direção (ground-truth)",
      _fm_rastro.get("quem") == "sozinho-r" and _fm_rastro.get("direcao"),
      str(_fm_rastro))
check("intensidade nasce baixa (small)", _fm_rastro.get("intensity") == "small",
      str(_fm_rastro))
check("ttl nunca ultrapassa 48h", _fm_rastro.get("ttl_seconds") <= 172800,
      str(_fm_rastro))
check("World Validator aceita o rastro (schema válido)",
      validator.validate(_fm_rastro) == [], str(validator.validate(_fm_rastro)))


print("\n--- US4: decaimento físico, nunca por uso -----------------------------")

_fm_velho = dict(_fm_rastro)
_fm_velho["criado_em"] = int(time.time()) - _fm_velho["ttl_seconds"] - 10
check("marca com criado_em+ttl no passado deixa de contar como ativa",
      not motor._is_trace_active(_fm_velho))
check("marca recém-criada ainda conta como ativa",
      motor._is_trace_active(_fm_rastro))
check("o arquivo nunca é removido do disco (Princípio IV)",
      _novo_rastro.exists())


print("\n--- US4: a rolagem varia pouco, nunca sai da faixa baixa/curta --------")

_mk_char(TAVERNA, "rola-alta", "RolaAlta")
motor._roll_trace_d20 = lambda: 20
antes_alta = set(rastros_em(TAVERNA))
andar("rola-alta", ROTA_TF)
novo_alta = list(set(rastros_em(TAVERNA)) - antes_alta)[0]
fm_alta, _ = motor.read_doc(novo_alta)

_mk_char(TAVERNA, "rola-baixa", "RolaBaixa")
motor._roll_trace_d20 = lambda: 1
antes_baixa = set(rastros_em(TAVERNA))
andar("rola-baixa", ROTA_TF)
novo_baixa = list(set(rastros_em(TAVERNA)) - antes_baixa)[0]
fm_baixa, _ = motor.read_doc(novo_baixa)

check("rolagem alta desloca o ttl para CIMA (nunca explode a faixa)",
      fm_alta["ttl_seconds"] >= fm_baixa["ttl_seconds"],
      f"alta={fm_alta['ttl_seconds']} baixa={fm_baixa['ttl_seconds']}")
check("nenhum dos dois sai da faixa baixa/curta (intensity ainda small)",
      fm_alta["intensity"] == "small" and fm_baixa["intensity"] == "small",
      f"{fm_alta['intensity']} / {fm_baixa['intensity']}")
check("nenhum dos dois ultrapassa 48h",
      fm_alta["ttl_seconds"] <= 172800 and fm_baixa["ttl_seconds"] <= 172800)


print("\n--- US4: prova de atomicidade — direto, sem deslocamento.py -----------")

rid = motor._leave_trace(pasta("rola-alta").parent, "rola-alta", ROTA_TF, "partida")
check("_leave_trace chamado DIRETO cria o rastro, sem depender de mais nada",
      bool(rid))


print("\n--- ITEM 52.6: a pergunta de CAMINHO que não rendeu registra nos dois ---")
# Decisão do mantenedor: os DOIS casos registram, nos DOIS lados. A fadiga sozinha não
# quebrava o laço — a Nerissa perguntou o caminho à Odila 50 VEZES, porque nada
# guardava que ela já havia perguntado e sido rebatida.
#
# E as vozes são DIFERENTES de propósito, preparando a MENTIRA futura ("mentir seria
# dizer que não sabia quando na verdade não quis"): quem PERGUNTOU guarda o que OUVIU,
# quem RESPONDEU guarda o que FEZ. Hoje coincidem; quando a mentira existir, só o lado
# do informante muda, e a memória de quem ouviu segue fiel ao que lhe disseram.
from motor.conhecimento import executores as _ex52   # noqa: E402

_A52, _B52 = "perguntador-l", "testemunha-l"
_f52 = motor.find_character_folder(_A52)
for _motivo, _extra, _rot in (("nao_quis", {"rota": ROTA_TF}, "não quis dizer"),
                              ("nao_sabe", {"rota": ROTA_TF}, "não conhece o caminho")):
    _ap, _rj, _cr = _ex52._apply_unanswered_ops(
        _A52, _f52, {"unanswered_ops": [{"informante": _B52, "motivo": _motivo, **_extra}]})
    _lados = {}
    for _c in _cr:
        _fm, _corpo = motor.read_doc(
            motor.find_character_folder(_c["target"]) / "memories" / f"{_c['id']}.md")
        _lados[_c["target"]] = (_fm, _corpo.strip())
    check(f"`{_motivo}` grava nos DOIS lados", len(_lados) == 2, str(list(_lados)))
    check(f"`{_motivo}` é `small` nos dois",
          all(fm.get("intensity") == "small" for fm, _ in _lados.values()),
          str({k: v[0].get("intensity") for k, v in _lados.items()}))
    check(f"`{_motivo}`: quem PERGUNTOU registra o que OUVIU (\"disse que…\")",
          "disse que" in _lados[_A52][1], _lados[_A52][1])
    check(f"`{_motivo}`: quem RESPONDEU registra o que FEZ (sem \"disse que\")",
          "disse que" not in _lados[_B52][1], _lados[_B52][1])
    check(f"`{_motivo}` nomeia o CAMINHO no texto (achável depois)",
          "Portão Lateral" in _lados[_A52][1], _lados[_A52][1])

# ---- item 53.4: a pergunta repetida RENOVA, não duplica ---------------------
# O Irmão Tobias perguntou o caminho à Nerissa por três horas. Cada pergunta
# gravava um arquivo novo, e ele chegou a 35 das 40 memórias VIVAS sendo a MESMA
# recusa. A vida dele sumiu debaixo delas, o contexto dobrou (9.128 → 20.631
# tokens de entrada), o turno foi de 68s a 260s e batia em timeout em 34% das
# vezes — e, o pior, virou COMBUSTÍVEL: sem intenção e sem urgência biológica, a
# memória era a única bússola do tick autônomo, e ela apontava 35 vezes para o
# assunto malresolvido. Ele perguntava porque lembrava de ter perguntado.
_mems = _f52 / "memories"
_antes = {p.name for p in _mems.glob("*.md")}
for _ in range(6):
    _ex52._apply_unanswered_ops(
        _A52, _f52, {"unanswered_ops": [{"informante": _B52, "sobre": "o poço velho",
                                         "motivo": "nao_soube"}]})
_novos = [p for p in _mems.glob("*.md") if p.name not in _antes]
check("53.4: seis perguntas iguais deixam UMA memória, não seis",
      len(_novos) == 1, f"{len(_novos)} arquivos")
if _novos:
    _fm6, _corpo6 = motor.read_doc(_novos[0])
    check("53.4: e ela conta que se insistiu — é a informação que faltava",
          "insisti" in _corpo6.lower(), _corpo6)
    check("53.4: sem número de sistema no texto (Princípio V)",
          not any(d in _corpo6 for d in "0123456789"), _corpo6)
    check("53.4: a repetição RENOVA o prazo (não morre no relógio da 1ª vez)",
          _fm6.get("state") == "active" and _fm6.get("vezes") == 6,
          f"state={_fm6.get('state')} vezes={_fm6.get('vezes')}")
# assunto DIFERENTE continua sendo memória própria — a fusão é por assunto, não por evento
_antes2 = {p.name for p in _mems.glob("*.md")}
_ex52._apply_unanswered_ops(
    _A52, _f52, {"unanswered_ops": [{"informante": _B52, "sobre": "a ponte nova",
                                     "motivo": "nao_soube"}]})
check("53.4: outro assunto NÃO se funde com o primeiro",
      len([p for p in _mems.glob("*.md") if p.name not in _antes2]) == 1)


# ---- 2026-08-20: a MESMA renovação para a RECUSA re-tentada ------------------
# `_remember_recurring` teve UM consumidor só (`unanswered`) por semanas, e o
# resto das recusas seguiu duplicando: a Elga acumulou 9 cópias de "tentei
# cozinhar na Rua do Mercador, mas não tinha calor" e 7 de "tentei beber de Moeda
# de Prata" (2026-08-20). É o mesmo laço do Tobias, e pelo mesmo motivo — a
# memória da recusa é o que manda tentar de novo.
#
# O que destravou a generalização foi a PROSA: `_insistencia` fala de pergunta
# ("já insisti"), e o `sanea_mundo.py` já registrava que ela não serve a "Vi X
# acusar Y". Agora a escala mora num lugar (`_reincidencia`) e o VERBO vem de
# quem chama.
_antes_r = {p.name for p in _mems.glob("*.md")}
for _ in range(4):
    motor.memoria.remember_recurring(
        _A52, "Tentei cozinhar em Rua do Mercador, mas não tinha calor nenhum.",
        about="cozinhar\x00sem_calor\x00rua-do-mercador",
        evento="cook_refused_fonte", involved=["rua-do-mercador"], frag="tentei",
        valence={"rua-do-mercador": "negativa"})
_novos_r = [p for p in _mems.glob("*.md") if p.name not in _antes_r]
check("recusa repetida deixa UMA memória, não quatro", len(_novos_r) == 1,
      f"{len(_novos_r)} arquivos")
if _novos_r:
    _fmr, _corpor = motor.read_doc(_novos_r[0])
    check("a recusa repetida conta que se insistiu, com o VERBO certo",
          "tentei" in _corpor.lower() and "insisti" not in _corpor.lower(), _corpor)
    check("recusa repetida: sem número de sistema (Princípio V)",
          not any(d in _corpor for d in "0123456789"), _corpor)
    check("recusa repetida: a VALÊNCIA sobrevive à renovação (o afeto é o que "
          "faz o personagem desgostar do que já o frustrou)",
          (_fmr.get("valence") or {}).get("rua-do-mercador") == "negativa",
          str(_fmr.get("valence")))
    check("recusa repetida: renova o prazo e conta as vezes",
          _fmr.get("state") == "active" and _fmr.get("vezes") == 4,
          f"state={_fmr.get('state')} vezes={_fmr.get('vezes')}")

# CHAVES DIFERENTES NÃO FUNDEM: `nao_comestivel` e `nao_alimenta` compartilham o
# evento `eat_refused`, e com a mesma chave os dois textos virariam um só.
_antes_k = {p.name for p in _mems.glob("*.md")}
motor.memoria.remember_recurring(_A52, "Tentei comer X, mas não era comida.",
    about="comer\x00nao_comestivel\x00x", evento="eat_refused", frag="tentei")
motor.memoria.remember_recurring(_A52, "Pensei em comer X, mas não ia matar a fome.",
    about="comer\x00nao_alimenta\x00x", evento="eat_refused", frag="pensei nisso")
check("mesmo evento com `about` diferente NÃO funde (são coisas distintas)",
      len([p for p in _mems.glob("*.md") if p.name not in _antes_k]) == 2)


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 35 (spec 034) passaram.")
