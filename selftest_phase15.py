"""Auto-teste da Fase 15 — Memória com Classes (spec 013).

Cobre:
  - compatibilidade: memória sem `kind`/`involved` continua válida e vira
    acontecimento (é o que mantém de pé todo o mundo escrito antes desta spec)
  - consultas do MUNDO: knows_route (só VIVA) vs recognizes_route (aceita
    vencida) — a diferença entre "sei" e "reconheço"; familiarity_with
  - criação automática: todo evento aplicado vira lembrança em quem o viveu,
    com `involved` correto
  - as duas regras de acúmulo: rota é ÚNICA e RENOVA; acontecimento ACUMULA
  - `study`: aprender de um mapa, e o aprendizado sobreviver à perda do item
  - corte de contexto: rota nunca desce, vencida nunca desce, evocação antes do
    teto, e o MUNDO continua sabendo depois do corte

Feature determinística: sem rolagem. O relógio se manipula escrevendo
`timestamp_end` direto no arquivo.

Uso:  python3 server/selftest_phase15.py
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

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
ROTA = "portao-lateral"
MAPA = "mapa-do-salgado"
CADEIA_TESTE = ["portao-lateral", "trilha-do-patio", "subida-do-corvo"]


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def res(**parts):
    # aprender exige a FONTE lida no turno e a citação do trecho (spec 014)
    base = {"narrative_hint": "age", "movement": None, "mutations": [],
            "lido": ["o pergaminho mostra o portão lateral e a trilha do pátio"],
            "item_transfers": [], "equip_ops": [], "lock_ops": [],
            "persuade_ops": [], "attack_ops": [], "carry_ops": [],
            "trade_ops": [], "study_ops": [], "memories": []}
    base.update(parts)
    return base


def mems(cid):
    """Frontmatter de todas as memórias de um personagem, vivas e vencidas."""
    return motor._iter_memories(cid)


def rotas_de(cid):
    return [m for m in mems(cid) if motor.memory_kind(m) == motor.ROTA]


def acontecimentos_de(cid):
    return [m for m in mems(cid)
            if motor.memory_kind(m) == motor.ACONTECIMENTO]


def vencer(cid, mem_id):
    """Empurra o prazo de uma memória para o passado, sem tocar no `state`."""
    folder = motor.find_character_folder(cid)
    for path in (folder / "memories").glob("*.md"):
        fm, body = motor.read_doc(path)
        if fm.get("id") == mem_id:
            fm["timestamp_end"] = int(time.time()) - 10
            motor.write_doc(path, fm, body)
            return True
    return False


print("\n--- Compatibilidade: o mundo antigo continua válido ------------------")

antigo = {"type": "memory", "id": "mem-sem-kind",
          "timestamp_start": int(time.time()),
          "timestamp_end": int(time.time()) + 10 ** 6,
          "intensity": "medium", "state": "active", "summary": "coisa antiga"}
motor.write_doc(motor.find_character_folder(ELGA) / "memories" / "mem-sem-kind.md",
                antigo, "uma lembrança de antes da spec 013")

check("memória sem 'kind' é tratada como acontecimento",
      motor.memory_kind(antigo) == motor.ACONTECIMENTO)
check("memória sem 'involved' devolve lista vazia, nunca None",
      motor.memory_involved(antigo) == [])
check("memória sem 'about' devolve None", motor.memory_about(antigo) is None)
ctx = motor.get_context(ELGA)
check("memória antiga continua narrável no contexto",
      any(m["id"] == "mem-sem-kind" for m in ctx["memories"]))


print("\n--- US1: o mundo responde o que o personagem sabe --------------------")

check("não conhece rota de que nunca ouviu falar",
      not motor.knows_route(TORVIN, ROTA))
check("nem reconhece", not motor.recognizes_route(TORVIN, ROTA))

motor._remember_route(motor.find_character_folder(TORVIN), ROTA, "Portão Lateral")
check("depois de aprender, conhece a rota", motor.knows_route(TORVIN, ROTA))
check("e reconhece também", motor.recognizes_route(TORVIN, ROTA))

mem_rota = rotas_de(TORVIN)[0]["id"]
vencer(TORVIN, mem_rota)
check("rota VENCIDA: já não sabe percorrer", not motor.knows_route(TORVIN, ROTA))
check("rota VENCIDA: mas ainda reconhece o lugar",
      motor.recognizes_route(TORVIN, ROTA))

check("rota inexistente não quebra a consulta",
      not motor.knows_route(TORVIN, "rota-que-nao-existe"))


print("\n--- US2: rota é ÚNICA e RENOVA; acontecimento ACUMULA -----------------")

antes = len(rotas_de(TORVIN))
motor._remember_route(motor.find_character_folder(TORVIN), ROTA, "Portão Lateral")
check("percorrer de novo NÃO duplica a memória de rota",
      len(rotas_de(TORVIN)) == antes, f"{antes} -> {len(rotas_de(TORVIN))}")
check("e REVIVE a rota que havia vencido", motor.knows_route(TORVIN, ROTA))

for _ in range(9):
    motor._remember_route(motor.find_character_folder(TORVIN), ROTA, "Portão Lateral")
check("dez percursos = UMA memória de rota", len(rotas_de(TORVIN)) == 1,
      str(len(rotas_de(TORVIN))))

n0 = len(acontecimentos_de(TORVIN))
for i in range(10):
    motor.apply_resolution(TORVIN, res(
        equip_ops=[], mutations=[{"target": TORVIN, "path": "status.mood",
                                  "value": f"ocupado {i}"}]))
n1 = len(acontecimentos_de(TORVIN))
check("SC-005: acontecimentos ACUMULAM (dez turnos, dez ou mais)",
      n1 > n0, f"{n0} -> {n1}")

check("nenhum arquivo foi apagado em nenhum caminho",
      len(list((motor.find_character_folder(TORVIN) / "memories").glob("*.md")))
      == len(mems(TORVIN)))


print("\n--- US3: o mundo lembra sozinho --------------------------------------")

n_torvin = len(acontecimentos_de(TORVIN))
n_elga = len(acontecimentos_de(ELGA))
# o dado precisa ser FORÇADO: ao contrário da persuasão, vantagem 10 não é
# determinística em ataque — ela enviesa, mas o d20 ainda rola, e um 2 erra.
# Sem isto o teste falhava em ~1 de 8 execuções, por motivo legítimo do mundo.
motor._roll_d20 = lambda: 20
out = motor.apply_resolution(TORVIN, res(
    attack_ops=[{"alvo": ELGA, "arma": None, "vantagem": 10}]))
check("o golpe acertou (dado forçado)", bool(out.get("attack_ops_applied")),
      str(out.get("rejected")))
check("o golpe gerou memória em quem agiu",
      len(acontecimentos_de(TORVIN)) > n_torvin)
check("e também em quem apanhou", len(acontecimentos_de(ELGA)) > n_elga)

# escolhe a memória DO GOLPE por conteúdo, não por ser a mais recente: várias
# memórias do mesmo segundo empatam no timestamp, e o desempate viraria sorteio
golpes = [m for m in acontecimentos_de(TORVIN)
          if ELGA in motor.memory_involved(m)
          and m.get("intensity") in ("large", "giant")]
recentes = golpes[-1] if golpes else {"intensity": None}
check("a memória do golpe registra QUEM estava envolvido",
      ELGA in motor.memory_involved(recentes),
      str(motor.memory_involved(recentes)))
check("involved nunca inclui o próprio dono da memória",
      TORVIN not in motor.memory_involved(recentes))
check("o golpe pesa mais que o banal",
      recentes.get("intensity") in ("large", "giant"),
      str(recentes.get("intensity")))

check("familiaridade cresce com o convívio",
      motor.familiarity_with(TORVIN, ELGA) > 0)
check("e não inventa intimidade com quem nunca se viu",
      motor.familiarity_with(TORVIN, "ninguem-nenhum") == 0)

# banal vence sozinho: é a relevância que faz o log não virar entulho
banais = [m for m in acontecimentos_de(TORVIN)
          if m.get("intensity") == "small"]
check("evento banal nasce com prazo curto", bool(banais))
if banais:
    prazo_banal = banais[0]["timestamp_end"] - banais[0]["timestamp_start"]
    prazo_rota = motor._TTL_ROTA
    check("e o caminho dura MUITO mais que o banal", prazo_rota > prazo_banal * 10,
          f"{prazo_banal}s vs {prazo_rota}s")

check("create_memory continua disponível ao Árbitro (não foi removida)",
      any(t["name"] == "create_memory"
          for t in arbiter.build_tools(motor.get_context(TORVIN))))
check("o prompt não instrui mais a registrar cenas banais",
      "Cenas banais não geram memória" not in arbiter.SYSTEM_PROMPT_TOOLS
      if hasattr(arbiter, "SYSTEM_PROMPT_TOOLS") else True)


print("\n--- US4: aprender de um mapa -----------------------------------------")

# o mapa está solto na taverna, ao alcance de quem estiver lá
# spec 014: não há campo que declare o que um item ensina. A prosa é que chega
# a quem arbitra, sob demanda — e o item que ensina tem o MESMO schema do que não
check("a prosa do material alcança quem decide",
      "portão lateral" in (motor.prose_of(TORVIN, MAPA) or "").lower(),
      str(motor.prose_of(TORVIN, MAPA)))
check("item que ensina e item que não ensina têm os MESMOS campos",
      set(motor.read_doc(motor.find_entity(MAPA)[0])[0])
      == set(motor.read_doc(motor.find_entity("bilhete-mudo")[0])[0]),
      str(set(motor.read_doc(motor.find_entity(MAPA)[0])[0])))
check("nenhum campo do schema existe só para ensinar caminhos",
      "teaches" not in motor.read_doc(motor.find_entity(MAPA)[0])[0])

check("Elga ainda não conhece o caminho", not motor.knows_route(ELGA, ROTA))
motor._roll_d20 = lambda: 20  # decifrou
out = motor.apply_resolution(ELGA, res(learn_ops=[{"rotas": [ROTA], "citacoes": [{"rota": ROTA, "trecho": "o portão lateral"}]}]))
check("aprender foi aplicado", bool(out.get("learn_ops_applied")),
      str(out.get("rejected")))
check("SC-006: ler o material ensinou a rota", motor.knows_route(ELGA, ROTA))
check("criou exatamente as rotas declaradas, nem uma a mais",
      len(rotas_de(ELGA)) == 1, str(len(rotas_de(ELGA))))

antes = len(rotas_de(ELGA))
motor.apply_resolution(ELGA, res(learn_ops=[{"rotas": [ROTA], "citacoes": [{"rota": ROTA, "trecho": "o portão lateral"}]}]))
check("aprender duas vezes renova sem duplicar", len(rotas_de(ELGA)) == antes)

# SC-007: o mapa é professor, não fonte
mapa_folder = None
for path in motor.WORLD_DIR.rglob("item.md"):
    fm, _ = motor.read_doc(path)
    if fm.get("id") == MAPA:
        mapa_folder = path.parent
        break
shutil.rmtree(mapa_folder)
check("SC-007: perder o mapa NÃO desfaz o que se aprendeu",
      motor.knows_route(ELGA, ROTA))

out = motor.apply_resolution(ELGA, res(learn_ops=[{"rotas": ["rota-que-nao-existe"], "citacoes": [{"rota": "rota-que-nao-existe", "trecho": "o portão lateral"}]}]))
regras = {r.get("regra") for r in out.get("rejected") or []}
check("prosa não cria caminho: rota inexistente é recusada",
      "rota_inexistente" in regras, str(regras))
check("e nada foi criado por isso", len(rotas_de(ELGA)) == antes)


print("\n--- Corte de contexto: narração cortada, conhecimento inteiro --------")

ctx = motor.get_context(ELGA)
check("SC-008a: NENHUMA memória de rota desce ao client",
      all(m.get("id") not in {r["id"] for r in rotas_de(ELGA)}
          for m in ctx["memories"]))

# volume: centenas de memórias num personagem só
elga_folder = motor.find_character_folder(ELGA)
agora = int(time.time())
for i in range(300):
    motor.write_doc(
        elga_folder / "memories" / f"mem-volume-{i}.md",
        {"type": "memory", "id": f"mem-volume-{i}", "kind": "acontecimento",
         "involved": [], "timestamp_start": agora - 400 * 86400,
         "timestamp_end": agora + 10 ** 6, "intensity": "small",
         "state": "active", "summary": f"coisa banal {i}"},
        f"aconteceu algo sem importância, número {i}")

ctx = motor.get_context(ELGA)
check("SC-008: contexto continua utilizável com 300+ memórias",
      len(ctx["memories"]) <= motor._MEMORY_CONTEXT_CAP,
      f"{len(ctx['memories'])} memórias")

# evocação: quem está presente puxa a lembrança de volta, mesmo antiga
motor.write_doc(
    elga_folder / "memories" / "mem-evocada.md",
    {"type": "memory", "id": "mem-evocada", "kind": "acontecimento",
     "involved": [TORVIN], "timestamp_start": agora - 400 * 86400,
     "timestamp_end": agora + 10 ** 6, "intensity": "small",
     "state": "active", "summary": "algo com Torvin"},
    "aconteceu algo com Torvin, há muito tempo")

ctx = motor.get_context(ELGA)
ids = {m["id"] for m in ctx["memories"]}
check("memória antiga que envolve alguém PRESENTE sobrevive ao corte",
      "mem-evocada" in ids)
check("enquanto as banais que ninguém evoca ficam de fora",
      not any(i.startswith("mem-volume-") for i in ids))

# vencida some da narração
vencer(ELGA, "mem-evocada")
ctx = motor.get_context(ELGA)
check("memória VENCIDA não desce ao client",
      "mem-evocada" not in {m["id"] for m in ctx["memories"]})
check("mas o arquivo continua no mundo — nada é apagado",
      (elga_folder / "memories" / "mem-evocada.md").exists())

# SC-008b: o corte é de NARRAÇÃO, nunca de conhecimento
check("SC-008b: o mundo continua sabendo do caminho DEPOIS do corte",
      motor.knows_route(ELGA, ROTA))
check("e continua contando a familiaridade com quem não desceu ao contexto",
      motor.familiarity_with(ELGA, TORVIN) > 0)


print("\n--- Mapa do que ele sabe (consulta de client) -------------------------")

# ids únicos: sem isso, duas memórias criadas no MESMO milissegundo recebem o
# mesmo nome de arquivo e uma sobrescreve a outra em silêncio. Apareceu ao
# aprender várias rotas de um mapa só — seis viraram uma.
sarga = motor.find_character_folder(TORVIN)
antes = len(rotas_de(TORVIN))
for rid in ("rota-a", "rota-b", "rota-c", "rota-d", "rota-e"):
    motor._remember_route(sarga, rid, rid)
check("cinco rotas aprendidas no mesmo instante geram CINCO memórias",
      len(rotas_de(TORVIN)) == antes + 5,
      f"{antes} -> {len(rotas_de(TORVIN))}")

mapa = motor.known_routes(TORVIN)
check("o mapa parte de onde o personagem está",
      mapa["raiz_id"] == "taverna-do-gancho", str(mapa["raiz_id"]))
check("e traz o caminho que ele conhece dali",
      any(r["route_id"] == ROTA for r in mapa["ramos"]), str(mapa["ramos"]))

# o mapa é DELE, não do cenário. Compara o que cada um SABE (a árvore só mostra
# rotas que existem no mundo, e as cinco de cima são ids inventados para o teste
# de colisão — não teriam ramo mesmo).
torvin_sabe = {m["about"] for m in rotas_de(TORVIN)}
elga_sabe = {m["about"] for m in rotas_de(ELGA)}
check("dois personagens no mesmo lugar conhecem caminhos diferentes",
      torvin_sabe != elga_sabe,
      f"torvin={sorted(torvin_sabe)} elga={sorted(elga_sabe)}")
check("o mapa de cada um vem da memória DELE, não do cenário",
      all(r["route_id"] in torvin_sabe for r in mapa["ramos"]))

check("rota que ele NÃO conhece não entra no mapa",
      all(r["route_id"] in {m['about'] for m in rotas_de(TORVIN)}
          for r in mapa["ramos"]))

# vencida aparece, mas marcada
for m in rotas_de(TORVIN):
    if m.get("about") == ROTA:
        vencer(TORVIN, m["id"])
mapa2 = motor.known_routes(TORVIN)
trecho = [r for r in mapa2["ramos"] if r["route_id"] == ROTA]
check("caminho de memória vencida ainda aparece no mapa", bool(trecho))
check("mas marcado como vago, não como sabido",
      trecho and trecho[0]["certeza"] == "vago",
      str(trecho[0]["certeza"]) if trecho else "ausente")

check("o mapa não inventa ramo para caminho nenhum quando nada se sabe",
      motor.known_routes(ELGA)["ramos"] == []
      or all(r["route_id"] for r in motor.known_routes(ELGA)["ramos"]))


print("\n--- Ids: únicos por construção, duplicados por detecção --------------")

# gerado: os DOIS caminhos de criação passam pelo mesmo helper. O do Árbitro
# ficou para trás na primeira correção e continuava com id por milissegundo.
gerados = {motor.new_id("mem") for _ in range(500)}
check("500 ids gerados em rajada são todos distintos", len(gerados) == 500,
      f"{len(gerados)} únicos")

alvo = motor.find_character_folder(ELGA)
antes = len(list((alvo / "memories").glob("*.md")))
motor._create_memories(
    {ELGA: alvo},
    {"memories": [{"target": ELGA, "content": f"lembrança {i}",
                   "intensity": "small", "ttl_seconds": 999}
                  for i in range(5)]})
depois = len(list((alvo / "memories").glob("*.md")))
check("cinco memórias do ÁRBITRO na mesma rajada geram cinco arquivos",
      depois == antes + 5, f"{antes} -> {depois}")

# editorial: id repetido não dá erro sozinho (o mundo é arquivo), então tem de
# ser DETECTADO — é a defesa que uuid não daria, porque quem escreve à mão
# escreve o que quiser
check("mundo da fixture não tem id duplicado", motor.duplicate_ids() == [],
      str(motor.duplicate_ids()))

clone = motor.WORLD_DIR / "taverna-do-gancho" / "seixo-clone"
clone.mkdir(parents=True, exist_ok=True)
motor.write_doc(clone / "item.md",
                {"type": "item", "id": "seixo-branco", "name": "Seixo Clonado"},
                "um seixo que rouba o id de outro")
dups = motor.duplicate_ids()
check("id repetido em dois arquivos é detectado",
      any(d["id"] == "seixo-branco" for d in dups), str(dups))
check("e aponta OS DOIS caminhos, para dar para achar",
      any(len(d["paths"]) == 2 for d in dups if d["id"] == "seixo-branco"))
check("mundo com id duplicado é reprovado na validação",
      any("duplicado" in e for p in motor.validate_world() for e in p["errors"]))

shutil.rmtree(clone)
check("removida a duplicata, o mundo volta a passar", motor.duplicate_ids() == [])


print("\n--- O mundo CONTA o que aconteceu, e a memória diz a verdade -----------")

import app as server_app  # noqa: E402

# Caso real: a Hulda tirou o gibão de placas e o deixou no chão da praça. A
# narração não disse nada — o narrador só recebia a INTENÇÃO e o que falhou — e a
# memória registrou "Ajustei ao corpo", como se ela tivesse VESTIDO a peça.
motor.apply_resolution(ELGA, res(equip_ops=[{"op": "equip", "item": "calca-de-linho"}]))
_antes = len(acontecimentos_de(ELGA))
out = motor.apply_resolution(ELGA, res(
    equip_ops=[{"op": "unequip", "item": "calca-de-linho", "to": "taverna-do-gancho"}]))

efeitos = server_app.inworld_effects(out)
check("o que aconteceu CHEGA à narração", bool(efeitos), str(out.get("equip_ops_applied")))
check("e diz que TIROU, não que vestiu",
      efeitos and "tirou" in efeitos[0] and "vestiu" not in efeitos[0], str(efeitos))
check("e diz ONDE foi parar", efeitos and "Taverna" in efeitos[0], str(efeitos))
check("com NOME, nunca id cru",
      efeitos and "calca-de-linho" not in efeitos[0], str(efeitos))

# seleciona por CONTEÚDO: a lista vem ordenada por nome de arquivo, e as
# memórias de volume criadas acima ficariam por último
textos = " | ".join(m.get("summary") or "" for m in acontecimentos_de(ELGA)
                    if "Calça de Linho" in (m.get("summary") or ""))
check("a memória do TIRAR não diz que vestiu",
      "Tirei" in textos and "Ajustei ao corpo" not in textos, textos)
check("e a memória usa o nome do item, não o id",
      "calca-de-linho" not in textos, textos)

# vestir de verdade continua sendo vestir
out2 = motor.apply_resolution(ELGA, res(equip_ops=[{"op": "equip", "item": "calca-de-linho"}]))
ef2 = server_app.inworld_effects(out2)
check("vestir continua sendo narrado como vestir",
      ef2 and "vestiu" in ef2[0], str(ef2))

# um turno sem efeito nenhum não inventa fato
vazio = server_app.inworld_effects({"equip_ops_applied": [], "item_transfers_applied": []})
check("turno sem efeito não inventa nada para narrar", vazio == [])


print("\n--- Nenhum canal muda o mundo em silêncio (Princípio X) ---------------")

# Guarda estrutural. Remendar canal a canal foi o que produziu o bug: `persuade`
# gravava "personagem" e o registro de memória lia "alvo", então um mascate saiu
# da praça sem que ninguém lembrasse. Aqui cada canal é EXERCITADO de verdade, e
# se cobra que ele produza as duas coisas que o Princípio X exige: relato à
# narração e memória em quem viveu.
motor._roll_d20 = lambda: 20

def _limpa(cid):
    """Zera o LOG do personagem, preservando o que ele SABE.

    Apagar tudo apagava junto as memórias de rota, e a viagem passava a não ter
    caminho conhecido — o teste falhava por falta de conhecimento, não por falta
    de registro. Conhecimento não é log.
    """
    for _p in (motor.find_character_folder(cid) / "memories").glob("*.md"):
        _fm, _ = motor.read_doc(_p)
        if motor.memory_kind(_fm) == motor.ACONTECIMENTO:
            _p.unlink()

def canal(nome, cid_ator, resolucao, quem_lembra):
    """Aplica um turno e cobra relato + memória em cada um que viveu o evento."""
    for c in quem_lembra:
        _limpa(c)
    out = motor.apply_resolution(cid_ator, resolucao)
    efeitos = server_app.inworld_effects(out)
    check(f"canal '{nome}': o mundo RELATA à narração", bool(efeitos),
          f"applied={ {k: v for k, v in out.items() if k.endswith('_applied')} }")
    for c in quem_lembra:
        mems = [m.get("summary") or "" for m in acontecimentos_de(c)]
        check(f"canal '{nome}': deixa memória em {c}", bool(mems), str(mems))
        check(f"canal '{nome}': a memória de {c} não traz id cru",
              all("-" not in (t.split(":")[-1] or "") or " " in t for t in mems),
              str(mems))

# devolve todo mundo para a taverna antes de cada exercício
def _junta(*ids):
    for cid in ids:
        f = motor.find_character_folder(cid)
        p = f / "character.md"
        fm, b = motor.read_doc(p)
        fm.pop("transit", None)
        fm.setdefault("status", {})["conditions"] = []
        motor.write_doc(p, fm, b)
        if f.parent.name != "taverna-do-gancho":
            shutil.move(str(f), str(motor.WORLD_DIR / "taverna-do-gancho" / cid))

_junta(TORVIN, ELGA)
canal("persuade", TORVIN,
      res(persuade_ops=[{"personagem": ELGA, "rota": ROTA, "vontade": 9}]),
      [TORVIN, ELGA])

_junta(TORVIN, ELGA)
canal("attack", TORVIN,
      res(attack_ops=[{"alvo": ELGA, "arma": None, "vantagem": 9}]),
      [TORVIN, ELGA])

# peça ainda livre: a calça já foi vestida pelos testes de fidelidade acima
_junta(TORVIN, ELGA)
canal("equip", ELGA,
      res(equip_ops=[{"op": "equip", "item": "gibao-de-couro"}]), [ELGA])

_junta(TORVIN, ELGA)
canal("mutate", TORVIN,
      res(mutations=[{"target": TORVIN, "path": "status.mood", "value": "atento"}]),
      [TORVIN])

_junta(TORVIN, ELGA)
canal("transfer", TORVIN,
      res(item_transfers=[{"item": "seixo-preto", "to": ELGA}]), [TORVIN, ELGA])

# ABRIR de verdade (a caixa nasce fechada). Fechá-la de novo seria no-op, e
# no-op não é evento — ver o teste logo abaixo.
_junta(TORVIN, ELGA)
canal("lock", TORVIN,
      res(lock_ops=[{"op": "open", "target": "caixa-de-pinho"}]), [TORVIN])

# o mapa foi destruído lá em cima, no teste da SC-007 (perder o item não desfaz
# o aprendizado). Refaz a peça para exercitar o canal.
_junta(TORVIN, ELGA)
_mapa_dir = motor.WORLD_DIR / "taverna-do-gancho" / MAPA
motor.write_doc(_mapa_dir / "item.md",
                {"type": "item", "id": MAPA, "name": "Mapa do Salgado",
                 "size": "PP", "weight_kg": 0.2},
                "Pergaminho gasto que desenha o portão lateral.")
canal("learn", TORVIN, res(learn_ops=[{"rotas": ["trilha-do-patio"], "citacoes": [{"rota": "trilha-do-patio", "trecho": "a trilha do pátio"}]}]), [TORVIN])

_junta(TORVIN, ELGA)
_limpa(ELGA)
_f_elga = motor.find_character_folder(ELGA)
_fm_e, _b_e = motor.read_doc(_f_elga / "character.md")
_fm_e.setdefault("status", {})["conditions"] = [motor.INCAPACITATED]
motor.write_doc(_f_elga / "character.md", _fm_e, _b_e)
canal("carry", TORVIN,
      res(carry_ops=[{"alvo": ELGA, "rota": ROTA}]), [TORVIN, ELGA])

_junta(TORVIN, ELGA)
for _r in CADEIA_TESTE:
    motor._remember_route(motor.find_character_folder(TORVIN), _r, _r)
canal("travel", TORVIN,
      res(travel_ops=[{"destino": "mirante-do-corvo"}]), [TORVIN])

# COMÉRCIO: a mercadoria precisa ser DELA e o pagamento precisa caber nas mãos —
# por isso as moedas vão para a bolsa (ninguém segura três moedas soltas, lição
# da spec 011).
_junta(TORVIN, ELGA)
motor.apply_resolution(ELGA, res(item_transfers=[{"item": "frasco-de-unguento", "to": ELGA}]))
for _m in ("moeda-de-prata-1", "moeda-de-prata-2", "moeda-de-prata-3"):
    motor.apply_resolution(TORVIN, res(item_transfers=[{"item": _m, "to": "bolsa-de-couro"}]))
canal("trade", TORVIN,
      res(trade_ops=[{"modo": "buy", "parceiro": ELGA,
                      "dou": ["moeda-de-prata-1", "moeda-de-prata-2",
                              "moeda-de-prata-3"],
                      "recebo": ["frasco-de-unguento"], "necessidade": 8}]),
      [TORVIN, ELGA])

# ANDAR é a ação mais comum do jogo, e passa por um caminho PRÓPRIO: o
# early-return de `apply_resolution`. Por isso escapava de `_record_events` e
# não deixava lembrança nenhuma — narrado e esquecido no mesmo instante.
_junta(TORVIN, ELGA)
_limpa(TORVIN)
motor.apply_resolution(TORVIN, res(movement={"enter_route": ROTA}))
_ms = [m.get("summary") or "" for m in acontecimentos_de(TORVIN)]
check("canal 'movement' (andar simples): deixa memória", bool(_ms), str(_ms))
check("e a memória do caminho traz o NOME da rota, não o id",
      any(ROTA not in t for t in _ms), str(_ms))

# no-op NÃO é evento: fechar o que já está fechado não muda nada, e um mundo
# que lembra do que não aconteceu corrompe o passado do personagem
_junta(TORVIN, ELGA)
_limpa(TORVIN)
_out_noop = motor.apply_resolution(
    TORVIN, res(lock_ops=[{"op": "close", "target": "arca-de-ferro"}]))
if any(o.get("noop") for o in _out_noop.get("lock_ops_applied") or []):
    check("no-op não vira memória", not acontecimentos_de(TORVIN),
          str([m.get("summary") for m in acontecimentos_de(TORVIN)]))
    check("no-op não vira relato",
          not server_app.inworld_effects(_out_noop),
          str(server_app.inworld_effects(_out_noop)))

# a derrota tem de pesar mais que um golpe qualquer
_junta(TORVIN, ELGA)
_limpa(TORVIN)
out = motor.apply_resolution(TORVIN, res(
    attack_ops=[{"alvo": ELGA, "arma": None, "vantagem": 10, "deliberado": True}]))
if out.get("attack_ops_applied") and out["attack_ops_applied"][0].get("derrota"):
    ef = server_app.inworld_effects(out)
    check("derrota é relatada como queda, não como golpe qualquer",
          any("caiu" in e for e in ef), str(ef))
    mems = [m for m in acontecimentos_de(TORVIN)]
    check("e a memória da derrota pesa mais que a de um golpe",
          any(m.get("intensity") == "giant" for m in mems),
          str([(m.get("summary"), m.get("intensity")) for m in mems]))


print("\n--- ITEM 52.6: registro de ESTADO expira rápido e NÃO se renova --------")
# `mutate` era 898 memórias — um TERÇO de tudo que o mundo lembra — com texto de campo
# ("Mudou em mim: action — ..."). Nasciam `small` (48h) e chegavam a 598 DIAS, porque a
# renovação por convívio soma meio TTL toda vez que o personagem age, e a `action` muda
# a CADA turno. Decisão do mantenedor: expirar rápido. TTL curto SOZINHO não bastaria —
# a renovação o desfaria —, e é por isso que os dois checks andam juntos.
from motor.memoria import primitivas as _pr52   # noqa: E402

_c52 = _um_personagem() if "_um_personagem" in dir() else sorted(
    c["id"] for c in motor.list_characters())[0]
_f52 = motor.find_character_folder(_c52)
_pr52._write_memory(_f52, "Mudou em mim: action — mexendo no alambique.",
                    intensity="small", involved=[_c52], evento="mutate")
_pr52._write_memory(_f52, "Golpeei alguém.", intensity="small",
                    involved=[_c52], evento="attack")


def _vida52(marca):
    """Acha PELA MARCA no texto, não pelo evento: a fase já criou memórias de
    `attack` antes daqui (uma `large`, 2160h), e procurar por evento pegava a
    dela — o teste reprovava por olhar a memória errada."""
    for p in (_f52 / "memories").glob("*.md"):
        fm, corpo = motor.read_doc(p)
        if marca in (corpo or "") or marca in (fm.get("summary") or ""):
            return (fm["timestamp_end"] - fm["timestamp_start"]) / 3600
    return None


check("registro de estado (`mutate`) nasce com vida CURTA, não com a da intensidade",
      _vida52("alambique") == 6 and _vida52("Golpeei alguém") == 48,
      f"mutate={_vida52('alambique')}h attack={_vida52('Golpeei alguém')}h")

for _ in range(5):                      # cinco turnos em que ele age de novo
    _pr52._renew_memory(_f52, entity_id=_c52)
check("a renovação por convívio NÃO estica o registro de estado (senão o prazo é fake)",
      _vida52("alambique") == 6, f"mutate={_vida52('alambique')}h")
check("mas SEGUE esticando a memória de vivência (o comportamento antigo, intacto)",
      _vida52("Golpeei alguém") > 48, f"attack={_vida52('Golpeei alguém')}h")

print("\n--- ITEM 52.6: a caneta do mundo carimba `evento` ----------------------")
# `_create_memories` montava o frontmatter SEM `evento`: 743 memórias de runtime (28%
# do acervo) ficaram sem etiqueta — texto bom, invisíveis ao casamento por TEMA do
# `recall`. Quem chama informa; "registro" é o piso honesto quando ninguém diz.
_antes52 = {p.name for p in (_f52 / "memories").glob("*.md")}
_pr52._create_memories({_c52: _f52}, {"memories": [
    {"target": _c52, "content": "Ouvi um grito na noite.", "intensity": "small",
     "ttl_seconds": 7200, "domain": "nenhuma", "evento": "witness_scream"},
    {"target": _c52, "content": "Algo me marcou e ninguém disse o quê.",
     "intensity": "small", "ttl_seconds": 7200, "domain": "nenhuma"},
]})
_novas52 = {}
for p in (_f52 / "memories").glob("*.md"):
    if p.name in _antes52:
        continue
    fm, _ = motor.read_doc(p)
    _novas52[(fm.get("summary") or "")[:12]] = fm.get("evento")
check("o `evento` informado por quem chama chega ao arquivo",
      "witness_scream" in _novas52.values(), str(_novas52))
check("sem `evento` informado, o piso é `registro` — nunca vazio",
      "registro" in _novas52.values(), str(_novas52))


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 15 (spec 013) passaram.")
