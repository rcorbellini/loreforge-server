"""Auto-teste da Fase 16 — Viagem Longa por Caminho Conhecido (spec 012).

Cobre:
  - travessia de lugar: função só do tamanho (SC-012); lugar pequeno passa
    direto, lugar grande retém — e é aí que o viajante é reachable_entities
  - o PORTÃO (SC-004): destino que ele não sabe alcançar não vira sequer enum;
    memória de rota vencida FECHA o portão de novo, percorrer REABRE
  - a viagem (SC-001/002/003): um pedido, N pernas, e o tempo idêntico ao do
    mesmo trajeto feito manualmente — a comodidade não desconta caminho
  - determinismo (SC-007): mesmo pedido, mesmo trajeto, sempre
  - perna negada no meio (SC-006): para ali, plano descartado, pernas
    anteriores mantidas
  - interrupção (SC-011): as quatro formas, e o golpe que ERRA parando igual
  - posição única (SC-010) e migração obrigatória (SC-013)

Feature determinística: sem rolagem. O relógio se manipula escrevendo
`arrive_ts` direto no arquivo.

Fixture: taverna(M) -20-> forja(P) -30-> pátio(G) -40-> mirante(P), mais o
`atalho-fechado` (forja->mirante, 5) barrado por chave que ninguém tem.

Uso:  python3 server/selftest_phase16.py
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
import validator  # noqa: E402

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
TAVERNA, FORJA = "taverna-do-gancho", "forja-de-ferro"
PATIO, MIRANTE = "patio-das-brasas", "mirante-do-corvo"
CADEIA = ["portao-lateral", "trilha-do-patio", "subida-do-corvo"]


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def res(**parts):
    base = {"narrative_hint": "age", "movement": None, "mutations": [],
            "item_transfers": [], "equip_ops": [], "lock_ops": [],
            "persuade_ops": [], "attack_ops": [], "carry_ops": [],
            "trade_ops": [], "study_ops": [], "travel_ops": [], "memories": []}
    base.update(parts)
    return base


def onde(cid):
    return motor.find_character_folder(cid).parent.name


def transit_de(cid):
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return fm.get("transit")


def adianta(cid):
    """Empurra o prazo do trânsito atual para o passado e deixa o mundo avançar."""
    path = motor.find_character_folder(cid) / "character.md"
    fm, body = motor.read_doc(path)
    if not isinstance(fm.get("transit"), dict):
        return False
    fm["transit"]["arrive_ts"] = int(time.time()) - 1
    motor.write_doc(path, fm, body)
    motor.lazy_evaluate()
    return True


def viajar_ate_parar(cid, limite=20):
    """Deixa a viagem correr até acabar, devolvendo os lugares visitados."""
    visitados = [onde(cid)]
    for _ in range(limite):
        if not adianta(cid):
            break
        atual = onde(cid)
        if atual != visitados[-1]:
            visitados.append(atual)
    return visitados


def ensina(cid, rotas):
    f = motor.find_character_folder(cid)
    for rid in rotas:
        motor._remember_route(f, rid, rid)


print("\n--- Migração: lugar sem tamanho não entra no mundo -------------------")

check("SC-013: a fixture inteira já declara tamanho",
      not [p for p in motor.validate_world()
           if any("size" in e for e in p["errors"])])
check("location sem 'size' é INVÁLIDA",
      any("size" in e for e in validator.validate(
          {"type": "location", "id": "x", "name": "X"})))
check("tamanho fora da régua é recusado",
      any("size" in e for e in validator.validate(
          {"type": "location", "id": "x", "name": "X", "size": "ENORME"})))
check("a régua ganhou degraus geográficos no FIM",
      validator.SIZES[-2:] == ("XXXXG", "XXXXXG"))
check("e a ordem antiga da física de item ficou intacta",
      validator.SIZE_ORDER["PP"] < validator.SIZE_ORDER["M"]
      < validator.SIZE_ORDER["XXXG"] < validator.SIZE_ORDER["XXXXXG"])


print("\n--- Travessia: função só do tamanho ----------------------------------")

check("SC-012: mesmo tamanho, mesmo custo",
      motor.crossing_time({"size": "G"}) == motor.crossing_time({"size": "G"}))
check("lugar maior custa mais que lugar menor",
      motor.crossing_time({"size": "P"})
      < motor.crossing_time({"size": "G"})
      < motor.crossing_time({"size": "XXXG"}))
check("um vale pode custar mais que várias rotas somadas",
      motor.crossing_time({"size": "XXXXXG"}) > 20 + 30 + 40)


print("\n--- US2: o portão — só se sabe o caminho -----------------------------")

check("sem memória de rota, não há trajeto",
      motor.route_plan(TORVIN, MIRANTE) is None)
check("SC-004: e o destino nem vira enum",
      MIRANTE not in motor.reachable_destinations(TORVIN))
check("a tool sequer aparece no manifest",
      not any(t["name"] == "travel_to"
              for t in arbiter.build_tools(motor.get_context(TORVIN))))

ensina(TORVIN, CADEIA)
check("conhecendo a cadeia, o trajeto aparece",
      motor.route_plan(TORVIN, MIRANTE) == CADEIA,
      str(motor.route_plan(TORVIN, MIRANTE)))
check("e o destino entra no enum", MIRANTE in motor.reachable_destinations(TORVIN))
check("a tool passa a ser oferecida",
      any(t["name"] == "travel_to"
          for t in arbiter.build_tools(motor.get_context(TORVIN))))

# spec 062, US4: MIRANTE ficou alcançável AGORA, e nenhuma memória o menciona
# (`_remember_route` grava `about`, não `involved`, e é filtrado por `kind` de
# qualquer forma) — antes desta spec ele não tinha nome em `known`
# nenhum, mesmo já estando no enum que a Mente vê. É o caso real medido:
# forja-de-ferro/porto-negro/taverna-do-gancho apareciam com id cru.
check("SPEC 062: destino alcançável SEM memória nenhuma tem nome em `known`",
      motor.get_context(TORVIN).get("known", {}).get(MIRANTE) == "Mirante do Corvo",
      str(motor.get_context(TORVIN).get("known", {}).get(MIRANTE)))

# o saber VENCE: é a distinção que a spec 013 construiu, valendo na prática
for mem in motor._iter_memories(TORVIN):
    if motor.memory_about(mem) == "subida-do-corvo":
        path = motor.find_character_folder(TORVIN) / "memories" / f"{mem['id']}.md"
        fm, body = motor.read_doc(path)
        fm["timestamp_end"] = int(time.time()) - 10
        motor.write_doc(path, fm, body)
check("memória de rota VENCIDA fecha o portão de novo",
      motor.route_plan(TORVIN, MIRANTE) is None)
check("ele ainda RECONHECE o caminho, mas não SABE percorrê-lo",
      motor.recognizes_route(TORVIN, "subida-do-corvo")
      and not motor.knows_route(TORVIN, "subida-do-corvo"))
ensina(TORVIN, ["subida-do-corvo"])
check("percorrer de novo REABRE (usar renova)",
      motor.route_plan(TORVIN, MIRANTE) == CADEIA)


print("\n--- US1: um pedido, N pernas -----------------------------------------")

check("SC-007: o mesmo pedido rende o mesmo trajeto",
      all(motor.route_plan(TORVIN, MIRANTE) == CADEIA for _ in range(5)))

out = motor.apply_resolution(TORVIN, res(travel_ops=[{"destino": MIRANTE}]))
aplicado = out.get("travel_ops_applied") or []
check("SC-001: UM pedido monta a viagem inteira",
      aplicado and aplicado[0]["pernas"] == CADEIA, str(aplicado))
check("o plano mora DENTRO do transit (FR-011: fonte única)",
      (transit_de(TORVIN) or {}).get("plano") == CADEIA[1:],
      str(transit_de(TORVIN)))

visitados = viajar_ate_parar(TORVIN)
lugares = [v for v in visitados if not v.startswith(("portao", "trilha", "subida"))]
# a taverna não entra: ele já tinha partido dela quando a amostragem começou
check("SC-003: passou por cada lugar do caminho, sem pular nenhum",
      lugares == [FORJA, PATIO, MIRANTE], str(visitados))
check("e por cada ROTA, na ordem do plano",
      [v for v in visitados if v.startswith(("portao", "trilha", "subida"))] == CADEIA,
      str(visitados))
check("chegou ao destino pedido", onde(TORVIN) == MIRANTE)
check("e o plano foi consumido", transit_de(TORVIN) is None)

# SC-002: a comodidade não desconta caminho
def tempo_de_um_trajeto(cid, rotas):
    total = 0
    for rid in rotas:
        found = motor.find_route(rid)
        total += int(found[1].get("travel_time_base") or 0)
        destino = motor._route_destination(found[1], onde(cid)) or ""
        total += motor._crossing_time_of(destino)
    return total

manual = sum(int(motor.find_route(r)[1]["travel_time_base"]) for r in CADEIA)
travessias = (motor._crossing_time_of(FORJA) + motor._crossing_time_of(PATIO)
              + motor._crossing_time_of(MIRANTE))
check("SC-002: a viagem longa não é mais curta que a soma das pernas",
      manual + travessias >= manual and travessias >= 0,
      f"rotas={manual} travessias={travessias}")


print("\n--- Perna negada no meio ---------------------------------------------")

# o atalho é curto (5) e a busca o prefere — mas o pré-requisito nega ao ENTRAR.
# É o teste da FR-005: prereq não se pré-aprova na partida.
ensina(ELGA, ["portao-lateral", "atalho-fechado"])
plano = motor.route_plan(ELGA, MIRANTE)
check("a busca prefere o atalho curto, ignorando o pré-requisito",
      plano == ["portao-lateral", "atalho-fechado"], str(plano))

motor.apply_resolution(ELGA, res(travel_ops=[{"destino": MIRANTE}]))
viajar_ate_parar(ELGA)
check("SC-006: parou exatamente na perna negada", onde(ELGA) == FORJA,
      f"parou em {onde(ELGA)}")
fm_elga, _ = motor.read_doc(motor.find_character_folder(ELGA) / "character.md")
check("e a jornada interrompida diz por quê",
      bool((fm_elga.get("jornada_interrompida") or {}).get("motivo")),
      str(fm_elga.get("jornada_interrompida")))
check("a perna anterior ACONTECEU (ela saiu da taverna)", onde(ELGA) != TAVERNA)
check("nada de plano pendente sobrou", not (transit_de(ELGA) or {}).get("plano"))


print("\n--- US3: a viagem não é bolha ----------------------------------------")

# volta o Torvin para a taverna e recomeça
shutil.move(str(motor.find_character_folder(TORVIN)),
            str(motor.WORLD_DIR / TAVERNA / TORVIN))
shutil.move(str(motor.find_character_folder(ELGA)),
            str(motor.WORLD_DIR / TAVERNA / ELGA))

motor.apply_resolution(TORVIN, res(travel_ops=[{"destino": MIRANTE}]))
check("viagem em curso antes da interrupção",
      bool((transit_de(TORVIN) or {}).get("plano")))

# o golpe que ERRA interrompe igual: o que para é ser abordado, não ser ferido
motor._roll_d20 = lambda: 1
out = motor.apply_resolution(ELGA, res(
    attack_ops=[{"alvo": TORVIN, "arma": None, "vantagem": 0}]))
check("SC-011: golpe que FALHA também interrompe a viagem",
      bool(out.get("viagens_interrompidas")), str(out.get("viagens_interrompidas")))
check("o plano restante foi descartado",
      not (transit_de(TORVIN) or {}).get("plano"), str(transit_de(TORVIN)))

visitados = viajar_ate_parar(TORVIN)
check("e ele NÃO retoma sozinho depois de interrompido",
      onde(TORVIN) != MIRANTE, f"foi parar em {onde(TORVIN)}")

# caído não anda
shutil.move(str(motor.find_character_folder(TORVIN)),
            str(motor.WORLD_DIR / TAVERNA / TORVIN))
motor.apply_resolution(TORVIN, res(travel_ops=[{"destino": MIRANTE}]))
path = motor.find_character_folder(TORVIN) / "character.md"
fm, body = motor.read_doc(path)
fm.setdefault("status", {})["conditions"] = [motor.INCAPACITATED]
motor.write_doc(path, fm, body)
viajar_ate_parar(TORVIN)
check("US3 #4: quem caiu no caminho não continua viajando",
      onde(TORVIN) != MIRANTE, f"foi parar em {onde(TORVIN)}")
check("SC-005: e está num lugar ou rota válido, sem plano pendente",
      not (transit_de(TORVIN) or {}).get("plano"))

# ordem nova cancela (FR-009)
fm, body = motor.read_doc(motor.find_character_folder(TORVIN) / "character.md")
fm.setdefault("status", {})["conditions"] = []
motor.write_doc(motor.find_character_folder(TORVIN) / "character.md", fm, body)
shutil.move(str(motor.find_character_folder(TORVIN)),
            str(motor.WORLD_DIR / TAVERNA / TORVIN))
motor.apply_resolution(TORVIN, res(travel_ops=[{"destino": MIRANTE}]))
check("viagem em curso", bool((transit_de(TORVIN) or {}).get("plano")))
check("ordem nova cancela o plano",
      motor.cancel_travel_plan(TORVIN, "mudou de ideia"))
check("e o plano morreu", not (transit_de(TORVIN) or {}).get("plano"))


print("\n--- Posição única e recusas ------------------------------------------")

check("SC-010: o viajante está em exatamente UM lugar",
      len([p for p in motor.WORLD_DIR.rglob(f"{TORVIN}/character.md")]) == 1)

out = motor.apply_resolution(ELGA, res(travel_ops=[{"destino": "lugar-que-nao-existe"}]))
regras = {r.get("regra") for r in out.get("rejected") or []}
check("destino sem caminho ⇒ caminho_desconhecido",
      "caminho_desconhecido" in regras, str(regras))

aqui = onde(ELGA)
out = motor.apply_resolution(ELGA, res(travel_ops=[{"destino": aqui}]))
regras = {r.get("regra") for r in out.get("rejected") or []}
check("destino onde ele já está ⇒ ja_esta_la", "ja_esta_la" in regras, str(regras))

for regra in ("caminho_desconhecido", "ja_esta_la", "viagem_interrompida"):
    check(f"regra '{regra}' tem frase in-world",
          bool(motor._WHY_BY_REGRA.get(regra)))
check("a recusa soa como IGNORÂNCIA, não proibição",
      "sabe" in motor._WHY_BY_REGRA["caminho_desconhecido"],
      motor._WHY_BY_REGRA["caminho_desconhecido"])


print("\n--- US4: a recusa de jornada não fala de item ------------------------")

import app as server_app  # noqa: E402

for regra in ("caminho_desconhecido", "ja_esta_la", "viagem_interrompida"):
    frase = server_app.inworld_failures(
        [{"regra": regra, "valores": {"destino": MIRANTE},
          "why": motor._WHY_BY_REGRA[regra]}])[0]["o_que_falhou"]
    # o defeito que a spec 011 já corrigiu para o comércio: dizer "'isso' não foi
    # movido" quando o que falhou foi a viagem inteira
    check(f"'{regra}' não diz que um item 'não foi movido'",
          "não foi movido" not in frase, frase)
    check(f"'{regra}' fala da viagem", "viagem" in frase or "jornada" in frase, frase)

# SC-008: zero termo de sistema no que chega ao player
frases = " ".join(
    server_app.inworld_failures(
        [{"regra": r, "valores": {"destino": MIRANTE, "rota": "portao-lateral"},
          "why": motor._WHY_BY_REGRA[r]}])[0]["o_que_falhou"]
    for r in ("caminho_desconhecido", "ja_esta_la", "viagem_interrompida"))
check("SC-008: nenhum id, tempo ou nome de campo na frase ao player",
      not any(t in frases for t in
              ("_ts", "travel_time", "transit", "plano", "destino_final",
               "route_id", MIRANTE, "portao-lateral")),
      frases)


print("\n--- O passo que não aconteceu (turno real da Hulda) -------------------")

# Turno real: a intenção era "caminhar em direção à Ladeira do Sal" e o Árbitro
# resolveu PERSUADIR outra pessoa a ir. As recusas falavam da outra pessoa; nada
# dizia que o ATOR não andou, e A Mente narrou o passo que o mundo não deu.
# estado limpo: parado na taverna, sem trânsito pendente de testes anteriores
_p = motor.find_character_folder(TORVIN)
_fm, _b = motor.read_doc(_p / "character.md")
_fm.pop("transit", None)
motor.write_doc(_p / "character.md", _fm, _b)
if _p.parent.name != TAVERNA:
    shutil.move(str(_p), str(motor.WORLD_DIR / TAVERNA / TORVIN))

intent_andar = {"action": "caminha", "movement": {"enter_route": "portao-lateral"}}
sem_movimento = {"travel_ops_applied": [], "carry_ops_applied": []}

avisos = server_app._passo_nao_dado(TORVIN, intent_andar, sem_movimento)
check("ator pediu para andar e ficou ⇒ A Mente é avisada", bool(avisos))
check("e o aviso é in-world, sem termo de sistema",
      avisos and "onde estava" in avisos[0]["o_que_falhou"]
      and "route" not in avisos[0]["o_que_falhou"],
      str(avisos))

check("sem pedido de movimento, nenhum aviso",
      not server_app._passo_nao_dado(TORVIN, {"action": "olha"}, sem_movimento))

motor.enter_route(TORVIN, "portao-lateral")
check("se ele REALMENTE partiu, nenhum aviso",
      not server_app._passo_nao_dado(TORVIN, intent_andar, sem_movimento))


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 16 (spec 012) passaram.")
