"""Auto-teste da Fase 18 — Perguntar o Caminho a Alguém (spec 015).

Cobre:
  - o ENCANAMENTO: o que um personagem lembra de OUTRO alcança quem arbitra,
    recortado pela relação e só o que está vivo
  - `directions_from`: ensina-se o que se SABE percorrer, não o que se reconhece
  - o PORTÃO: nota 0 recusa sem dado, 10 informa sem dado, 1-9 rolam uma vez
  - o caso que motivou a spec: quem levou uma pancada não indica caminho nenhum,
    e o motivo chega ao jogador (SC-003a, SC-003c)
  - a SEGUNDA CAMADA: rota real que o informante não conhece é recusada pelo
    arquivo, não pelo prompt
  - a DC deslocada pelo INT de quem explica (SC-005), sem que material lido mude
  - memória nos DOIS lados, e o que se aprendeu sobrevive ao informante (SC-012)
  - a guarda que exige `ask_directions` antes de `learn_routes` com fonte

As memórias do fixture são criadas AQUI, no tmpdir, e não no fixture partilhado:
a fase 15 checa `known_routes(ELGA)["ramos"] == []` e um `memories/` versionado
quebraria outras fases.

Uso:  python3 server/selftest_phase18.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import motor  # noqa: E402

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
ROTA = "portao-lateral"          # Elga vai saber; Torvin não
OUTRA = "subida-do-corvo"        # Elga só vai reconhecer (vencida)
TERCEIRA = "trilha-do-patio"     # ninguém sabe: a segunda camada


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def dado(v):
    motor._roll_d20 = lambda: v


def dados(seq):
    """Sequência de rolagens — expõe quem consome dado a mais ou a menos."""
    it = iter(list(seq))
    motor._roll_d20 = lambda: next(it)


def pasta(cid):
    return motor.find_character_folder(cid)


def limpar_memorias(cid):
    d = pasta(cid) / "memories"
    if d.is_dir():
        for p in d.glob("*.md"):
            p.unlink()


def rotas_de(cid):
    return {motor.memory_about(m) for m in motor._iter_memories(cid)
            if motor.memory_kind(m) == motor.ROTA}


def res(**parts):
    base = {"narrative_hint": "pergunta", "movement": None, "mutations": [],
            "lido": [], "informes": [],
            "item_transfers": [], "equip_ops": [], "lock_ops": [],
            "persuade_ops": [], "attack_ops": [], "carry_ops": [],
            "trade_ops": [], "learn_ops": [], "travel_ops": [], "memories": []}
    base.update(parts)
    return base


def prosa_de(rota):
    return motor.find_route(rota)[2].strip()


def ensinar(rota, *, fonte=ELGA, disposicao=8, atitude="fala sem cerimônia",
            trecho=None):
    """Uma op de aprendizado por CONVERSA, com a citação tirada da prosa real."""
    texto = prosa_de(rota) if trecho is None else trecho
    return [{"rotas": [rota], "citacoes": [{"rota": rota, "trecho": texto}],
             "fonte": fonte, "disposicao": disposicao, "atitude": atitude}]


def montar_mundo():
    """Elga SABE o portão lateral, RECONHECE a subida do corvo (vencida)."""
    limpar_memorias(ELGA)
    limpar_memorias(TORVIN)
    motor._remember_route(pasta(ELGA), ROTA, "Portão Lateral")
    motor._remember_route(pasta(ELGA), OUTRA, "Subida do Corvo")
    # vence a segunda à mão: reconhecer não é saber
    for p in (pasta(ELGA) / "memories").glob("*.md"):
        fm, body = motor.read_doc(p)
        if motor.memory_about(fm) == OUTRA:
            fm["state"] = "expired"
            motor.write_doc(p, fm, body)


montar_mundo()


print("\n--- O encanamento: a relação alcança quem arbitra --------------------")

check("sem história, não há nada a lembrar de alguém",
      motor.remembered_about(ELGA, TORVIN) == [])

motor._write_memory(pasta(ELGA),
                    "O punho do ferreiro pegou-me de lado, e o chão da taverna "
                    "veio ao encontro do meu rosto.",
                    intensity="large", involved=[TORVIN],
                    summary="Levei uma pancada de Torvin.")
motor._write_memory(pasta(ELGA), "Servi ensopado a um viajante calado.",
                    intensity="small", involved=["ninguem-em-especial"])

lembra = motor.remembered_about(ELGA, TORVIN)
check("o que ela guarda DELE chega a quem arbitra", len(lembra) == 1, str(lembra))
check("e chega com o texto, não só com um número",
      lembra and "punho do ferreiro" in (lembra[0].get("content") or ""),
      str(lembra))
check("o recorte é pela RELAÇÃO: o que não o envolve fica fora",
      all("ensopado" not in (m.get("content") or "") for m in lembra))
check("memória de rota nunca entra na relação",
      all(m.get("id") not in rotas_de(ELGA) for m in lembra))
check("quem não existe não tem relação com ninguém",
      motor.remembered_about("nao-existe", TORVIN) == [])

# o rancor esfria pelo relógio da spec 013 — sem mecanismo de perdão nenhum
for p in (pasta(ELGA) / "memories").glob("*.md"):
    fm, body = motor.read_doc(p)
    if TORVIN in motor.memory_involved(fm):
        fm["state"] = "expired"
        motor.write_doc(p, fm, body)
check("memória VENCIDA já não pesa na relação",
      motor.remembered_about(ELGA, TORVIN) == [],
      str(motor.remembered_about(ELGA, TORVIN)))
for p in (pasta(ELGA) / "memories").glob("*.md"):   # revive para os testes adiante
    fm, body = motor.read_doc(p)
    if TORVIN in motor.memory_involved(fm):
        fm["state"] = "active"
        motor.write_doc(p, fm, body)


print("\n--- Ensina-se o que se SABE, não o que se reconhece ------------------")

d = motor.directions_from(ELGA)
ids = {c["rota"] for c in d["caminhos"]}
check("FR-004: o caminho que ela SABE entra", ROTA in ids, str(ids))
check("e o que ela apenas reconhece (vencido) fica FORA", OUTRA not in ids, str(ids))
check("o que ninguém sabe não entra", TERCEIRA not in ids, str(ids))
check("a prosa vai junto, e é a do mundo",
      any(c["prosa"] == prosa_de(ROTA) for c in d["caminhos"]), str(d))
check("quem não conhece caminho nenhum não inventa cidade",
      motor.directions_from(TORVIN)["caminhos"] == [])


print("\n--- O portão: os extremos não consomem dado --------------------------")

limpar_memorias(TORVIN)
dados([])   # qualquer consumo de dado aqui estoura StopIteration
out = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)], learn_ops=ensinar(ROTA, disposicao=0,
                                             atitude="cospe no chão")))
regras = {r.get("regra") for r in out.get("rejected") or []}
check("nota 0 recusa SEM dado", "recusou_informar" in regras, str(regras))
check("e nada foi aprendido", rotas_de(TORVIN) == set(), str(rotas_de(TORVIN)))
check("SC-003c: o MOTIVO viaja com a recusa",
      any((r.get("valores") or {}).get("atitude") for r in out.get("rejected") or []),
      str(out.get("rejected")))

limpar_memorias(TORVIN)
dados([20])   # UM dado só. Se o portão consumisse, a leitura estouraria a fila.
out = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)], learn_ops=ensinar(ROTA, disposicao=10)))
check("nota 10 informa SEM dado: o único gasto é o da leitura",
      ROTA in rotas_de(TORVIN), str(rotas_de(TORVIN)))

limpar_memorias(TORVIN)
dados([1, 20])   # portão falha (1+mod(CHA -1) < DC), leitura nem chega a rolar
out = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)], learn_ops=ensinar(ROTA, disposicao=5)))
check("nota intermediária ROLA, e o portão pode fechar",
      rotas_de(TORVIN) == set(), str(rotas_de(TORVIN)))
check("e a recusa é `recusou_informar`",
      any(r.get("regra") == "recusou_informar" for r in out.get("rejected") or []),
      str([r.get("regra") for r in out.get("rejected") or []]))


print("\n--- O caso da pancada (SC-003a) --------------------------------------")

# É o caso que motivou a spec. O Árbitro é quem lê a memória e dá a nota 0; o
# que se verifica AQUI é que, dada a nota, o mundo não deixa escapar nada — e
# que a memória está lá para ser lida.
check("a memória da agressão está viva e alcança quem arbitra",
      any("punho" in (m.get("content") or "")
          for m in motor.remembered_about(ELGA, TORVIN)))
limpar_memorias(TORVIN)
dados([20, 20, 20])   # dados generosos: nada disso deve salvar o pedido
out = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)],
    learn_ops=ensinar(ROTA, disposicao=0,
                      atitude="vira as costas, a marca do soco ainda no rosto")))
check("SC-003a: quem apanhou não ensina, e dado nenhum salva",
      rotas_de(TORVIN) == set(), str(rotas_de(TORVIN)))
_motivos = [(r.get("valores") or {}).get("atitude")
            for r in out.get("rejected") or []]
check("e o jogador recebe o motivo em linguagem de mundo",
      any(m and "soco" in m for m in _motivos), str(_motivos))
_falhas = server_app.inworld_failures(out.get("rejected") or [])
check("a recusa chega a A Mente como falha de CONVERSA, não de item",
      any("não foi ensinado" in f.get("o_que_falhou", "") for f in _falhas),
      str(_falhas))
check("e o motivo vai DENTRO da frase que A Mente lê — ela não vê as memórias "
      "do informante e não teria como inventá-lo",
      any("soco" in f.get("o_que_falhou", "") for f in _falhas), str(_falhas))


print("\n--- A segunda camada: o arquivo recusa o que o prompt permitiria ------")

limpar_memorias(TORVIN)
dado(20)
out = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(TERCEIRA)],
    learn_ops=ensinar(TERCEIRA, disposicao=10)))
regras = {r.get("regra") for r in out.get("rejected") or []}
check("rota REAL que o informante não conhece é recusada",
      "informante_nao_sabe" in regras, str(regras))
check("e nada foi aprendido", rotas_de(TORVIN) == set())

# informante caído não conversa
_f = pasta(ELGA) / "character.md"
_fm, _body = motor.read_doc(_f)
_fm.setdefault("status", {})["conditions"] = [motor.INCAPACITATED]
motor.write_doc(_f, _fm, _body)
dado(20)
out = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)], learn_ops=ensinar(ROTA, disposicao=10)))
check("informante caído não responde",
      any(r.get("regra") == "informante_indisponivel"
          for r in out.get("rejected") or []),
      str([r.get("regra") for r in out.get("rejected") or []]))
_fm["status"]["conditions"] = []
motor.write_doc(_f, _fm, _body)


print("\n--- A citação continua sendo conferida -------------------------------")

limpar_memorias(TORVIN)
dado(20)
out = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)],
    learn_ops=ensinar(ROTA, disposicao=10,
                      trecho="ele disse que o caminho passa pela ponte")))
check("SC-008: citação que a fala não sustenta não ensina",
      rotas_de(TORVIN) == set(), str(rotas_de(TORVIN)))
check("e a recusa diz que aquilo não foi dito",
      any(r.get("regra") == "citacao_nao_confere"
          for r in out.get("rejected") or []))


print("\n--- Quem explica bem ensina bem (SC-005) -----------------------------")

check("DC de um informante mediano é a mesma do material",
      motor.learn_dc_from({"attributes": {"INT": 10}}) == motor.LEARN_ROUTE_DC)
check("erudito abaixa a DC",
      motor.learn_dc_from({"attributes": {"INT": 18}}) < motor.LEARN_ROUTE_DC)
check("embotado levanta a DC",
      motor.learn_dc_from({"attributes": {"INT": 6}}) > motor.LEARN_ROUTE_DC)
check("o clamp segura os dois extremos",
      motor.learn_dc_from({"attributes": {"INT": 30}}) == 8
      and motor.learn_dc_from({"attributes": {"INT": 1}}) == 16,
      f"{motor.learn_dc_from({'attributes': {'INT': 30}})} / "
      f"{motor.learn_dc_from({'attributes': {'INT': 1}})}")

# mesmo dado, mesmo ouvinte: o INT de quem explica decide
_elga_fm, _elga_body = motor.read_doc(pasta(ELGA) / "character.md")
_dc_alvo = None
for _int, _esperado in ((18, True), (6, False)):
    _elga_fm["attributes"]["INT"] = _int
    motor.write_doc(pasta(ELGA) / "character.md", _elga_fm, _elga_body)
    limpar_memorias(TORVIN)
    dados([11])   # 11 + mod(INT 10 do Torvin)=0 -> passa em DC<=11, falha acima
    motor.apply_resolution(TORVIN, res(
        lido=[prosa_de(ROTA)], learn_ops=ensinar(ROTA, disposicao=10)))
    check(f"informante de INT {_int} {'ensina' if _esperado else 'não ensina'} "
          "com a mesma rolagem",
          (ROTA in rotas_de(TORVIN)) == _esperado, str(rotas_de(TORVIN)))
_elga_fm["attributes"]["INT"] = 11
motor.write_doc(pasta(ELGA) / "character.md", _elga_fm, _elga_body)


print("\n--- Memória dos dois lados, e o que fica -----------------------------")

limpar_memorias(TORVIN)
limpar_memorias(ELGA)
motor._remember_route(pasta(ELGA), ROTA, "Portão Lateral")
dado(20)
out = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)], learn_ops=ensinar(ROTA, disposicao=10)))
check("o caminho passou de quem sabia para quem não sabia (SC-001)",
      motor.knows_route(TORVIN, ROTA))
_ev = {m.get("event") for m in out.get("memories_created") or []}
check("o canal `inform` gravou", "inform" in _ev, str(out.get("memories_created")))
_mem_torvin = [m for m in motor._iter_memories(TORVIN)
               if motor.memory_kind(m) != motor.ROTA]
_mem_elga = [m for m in motor._iter_memories(ELGA)
             if motor.memory_kind(m) != motor.ROTA]
check("quem aprendeu lembra de QUEM ensinou",
      any(ELGA in motor.memory_involved(m) for m in _mem_torvin),
      str([motor.memory_involved(m) for m in _mem_torvin]))
check("quem ensinou lembra de ter sido procurado",
      any(TORVIN in motor.memory_involved(m) for m in _mem_elga),
      str([motor.memory_involved(m) for m in _mem_elga]))
check("o relato ao jogador diz de QUEM ele aprendeu",
      any("aprendeu com" in d for d in server_app.inworld_effects(out)),
      str(server_app.inworld_effects(out)))


print("\n--- Spec 034: ask_directions resolve numa chamada só -----------------")

_ctx = motor.get_context(TORVIN)
_tools = {t["name"] for t in arbiter.build_tools(_ctx)}
check("`ask_directions` entrou no manifest", "ask_directions" in _tools, str(_tools))
_ad = [t for t in arbiter.build_tools(_ctx) if t["name"] == "ask_directions"][0]
# spec 043: `disposicao` SAIU da face — é JUÍZO, e ninguém de fora a preenche. O que
# resta é ESCOLHA. A ausência dela aqui é o Princípio IX virado estrutura.
check("`ask_directions` expõe só a ESCOLHA; `disposicao` (juízo) não desce",
      _ad["parameters"]["required"] == ["quem"]
      and "disposicao" not in _ad["parameters"]["properties"],
      str(_ad["parameters"]))
_lr = [t for t in arbiter.build_tools(_ctx) if t["name"] == "learn_routes"][0]
_props = _lr["parameters"]["properties"]
check("`learn_routes` NÃO tem mais fonte/disposicao/atitude — só material",
      not ({"fonte", "disposicao", "atitude"} & set(_props)), str(sorted(_props)))
check("e continua exigindo só `rotas`",
      _lr["parameters"]["required"] == ["rotas"], str(_lr["parameters"]["required"]))

# O ELO, pelo Árbitro (spec 034, US3): uma chamada só resolve pergunta E
# registro — não há mais `learn_routes` a chamar depois. A fase 17 registra
# que este tipo de teste existe por um bug real: o `lido` some se alguém mexer
# na guarda, e nenhum outro teste nota porque todos montam a resolução na mão.
limpar_memorias(TORVIN)
motor._remember_route(pasta(ELGA), ROTA, "Portão Lateral")
_visto = {}


def _loop_conversa(_s, _u, _t, execute, _m):
    r, _ = execute("ask_directions", {"quem": ELGA, "disposicao": 9})
    _visto["resposta"] = r
    return {"stopped": "tools", "text": ""}


dado(20)
_r = arbiter.resolve_with_tools({"action": "pergunta o caminho"},
                                motor.get_context(TORVIN), _loop_conversa)
check("`ask_directions` devolve os caminhos que ela sabe",
      _visto["resposta"].get("caminhos"), str(_visto.get("resposta")))
check("e devolve o que ela lembra de QUEM pergunta",
      "lembra_de_voce" in _visto["resposta"], str(_visto["resposta"].keys()))
check("o caminho JÁ foi ensinado NA MESMA chamada — sem learn_routes nenhum",
      motor.knows_route(TORVIN, ROTA), str(_visto["resposta"]))
check("`informes` desce para A Mente narrar a fala",
      bool(_r.get("informes")), str(_r.get("informes")))
check("a resposta ao Árbitro leva `informes` e NUNCA a nota",
      "disposicao" not in str(_r.get("informes")), str(_r.get("informes")))

# a régua fechada (spec 034): nota 0 não ensina nada, numa chamada só
limpar_memorias(TORVIN)
_visto2 = {}


def _loop_fechado(_s, _u, _t, execute, _m):
    r, _ = execute("ask_directions", {"quem": ELGA, "disposicao": 0})
    _visto2["r"] = r
    return {"stopped": "tools", "text": ""}


# spec 043: a nota vem do MUNDO (`ctx.ask`), não de args — injeta por ali.
_r_fechado = arbiter.resolve_with_tools({"action": "pergunta"},
                                        motor.get_context(TORVIN), _loop_fechado,
                                        ask=lambda _s, _u: "0")
check("disposicao 0 recusa SEM dado, e nada é ensinado",
      _visto2["r"].get("erro") and rotas_de(TORVIN) == set(), str(_visto2))
check("mesmo na recusa, o contexto (o que ela sabe/o afeto) chega ao Árbitro",
      "lembra_de_voce" in _visto2["r"] and "saldo_afeto" in _visto2["r"],
      str(_visto2["r"].keys()))

# um `fonte` estranho em learn_routes não derruba a tool (KeyError/crash) —
# só deixa de existir como campo lido; a validação de sempre (citação contra
# `lido`) continua se aplicando igual, sem `fonte` nenhuma para mudar o rumo.
limpar_memorias(TORVIN)
_ignorado = {}


def _loop_fonte_fantasma(_s, _u, _t, execute, _m):
    r, _ = execute("learn_routes", {
        "rotas": [{"rota": ROTA, "trecho": prosa_de(ROTA)}],
        "fonte": ELGA, "disposicao": 9, "atitude": "cordial"})
    _ignorado["r"] = r
    return {"stopped": "tools", "text": ""}


dado(20)
_r_ign = arbiter.resolve_with_tools({"action": "aprende"},
                                    motor.get_context(TORVIN), _loop_fonte_fantasma)
check("`fonte`/disposicao/atitude extra não impedem o enfileiramento (sem crash)",
      _ignorado["r"].get("ok"), str(_ignorado))
_out_ign = motor.apply_resolution(TORVIN, _r_ign)
check("mas na aplicação final, sem ter LIDO antes, a citação não confere"
      " (fonte extra não vira atalho — spec 034)",
      any(r.get("regra") == "citacao_nao_confere"
          for r in _out_ign.get("rejected") or []),
      str(_out_ign.get("rejected")))

# a guarda não é autoridade: o Motor tem de recusar sozinho uma resolução
# montada sem fonte, com a fala presente em `lido` e em `falas`
limpar_memorias(TORVIN)
dado(20)
_out_sf = motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)],
    falas=[{"informante": ELGA, "rota": ROTA, "prosa": prosa_de(ROTA)}],
    learn_ops=[{"rotas": [ROTA],
                "citacoes": [{"rota": ROTA, "trecho": prosa_de(ROTA)[:40]}]}]))
check("o MOTOR recusa mesmo que a guarda seja contornada",
      rotas_de(TORVIN) == set(), str(rotas_de(TORVIN)))
check("e a regra é `fonte_omitida`",
      any(r.get("regra") == "fonte_omitida" for r in _out_sf.get("rejected") or []),
      str([r.get("regra") for r in _out_sf.get("rejected") or []]))

# e o caminho da spec 014 (material lido, sem fala nenhuma) segue intacto
limpar_memorias(TORVIN)
dado(20)
motor.apply_resolution(TORVIN, res(
    lido=[prosa_de(ROTA)],
    learn_ops=[{"rotas": [ROTA],
                "citacoes": [{"rota": ROTA, "trecho": prosa_de(ROTA)[:40]}]}]))
check("sem fala no turno, aprender sem fonte continua valendo (spec 014)",
      ROTA in rotas_de(TORVIN), str(rotas_de(TORVIN)))

_chamadas = []


def _loop_sem_perguntar(_s, _u, _t, execute, _m):
    """Spec 034: sem `fonte` no schema, o único jeito de aprender de uma
    PESSOA que não está na cena é `ask_directions` — e ela barra `quem` fora
    do enum de presentes, antes de qualquer coisa."""
    r, _ = execute("ask_directions", {"quem": "sarga-do-cais", "disposicao": 8})
    _chamadas.append(r)
    return {"stopped": "tools", "text": ""}


_r = arbiter.resolve_with_tools({"action": "pergunta"}, _ctx, _loop_sem_perguntar)
check("perguntar a quem não está presente é barrado",
      _chamadas and _chamadas[0].get("erro"), str(_chamadas))
check("e nada entrou na fila", not (_r.get("learn_ops") or []),
      str(_r.get("learn_ops")))


print("\n--- Sem ninguém a quem perguntar, a capacidade some ------------------")

# SC-012 fica por último de propósito: apagar a Elga esvazia a cena, e o que
# vem depois disso mede outra coisa.
shutil.rmtree(pasta(ELGA))
check("SC-012: o que se aprendeu sobrevive ao sumiço de quem ensinou",
      motor.knows_route(TORVIN, ROTA))
_tools_so = {t["name"] for t in arbiter.build_tools(motor.get_context(TORVIN))}
check("sozinho na cena, `ask_directions` nem é oferecida",
      "ask_directions" not in _tools_so, str(_tools_so))
_lr_so = [t for t in arbiter.build_tools(motor.get_context(TORVIN))
          if t["name"] == "learn_routes"][0]
check("e `learn_routes` continua só `rotas` — spec 034: nunca teve fonte",
      "fonte" not in _lr_so["parameters"]["properties"],
      str(sorted(_lr_so["parameters"]["properties"])))


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 18 (spec 015) passaram.")
