"""Auto-teste da Fase 17 — Aprender Caminhos pela Prosa (spec 014).

Cobre:
  - o ENCANAMENTO: a prosa de uma entidade alcança quem arbitra, sob demanda,
    respeitando alcance e fecho de contêiner
  - o CREATOR MODE (SC-001/SC-002): item que ensina e item que não ensina têm
    exatamente os mesmos campos declarados; nenhum campo existe para ensinar
  - prosa não cria mundo (SC-006): rota inexistente nunca é aprendida
  - o teste POR ROTA (SC-003): um material de N pode render de 0 a N
  - rota já conhecida renova SEM rolagem (SC-005)
  - INT importa (SC-004) e a fonte é dispensável depois (SC-007)
  - o relato das DUAS metades: o que decifrou e o que não

Feature com rolagem: `motor._roll_d20` é forçado em todo teste de desfecho — a
fase 15 já custou caro por deixar uma rolagem solta.

Uso:  python3 server/selftest_phase17.py
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
import validator  # noqa: E402

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
MAPA, MUDO = "mapa-do-salgado", "bilhete-mudo"
ROTA = "portao-lateral"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# todo aprendizado exige uma FONTE lida no turno: citação que não se pode
# conferir vale o mesmo que citação falsa. Os testes de rolagem passam um texto
# que contém as palavras citadas.
FONTE = ("Dois traços a carvão mostram o portão lateral, a trilha do pátio, "
         "a subida do corvo, o atalho fechado, o beco das sombras e o caminho "
         "da muralha.")


def aprender(*rotas):
    return [{"rotas": list(rotas),
             "citacoes": [{"rota": r, "trecho": "traços a carvão"} for r in rotas]}]


def res(**parts):
    base = {"narrative_hint": "lê", "movement": None, "mutations": [],
            "lido": [FONTE],
            "item_transfers": [], "equip_ops": [], "lock_ops": [],
            "persuade_ops": [], "attack_ops": [], "carry_ops": [],
            "trade_ops": [], "learn_ops": [], "travel_ops": [], "memories": []}
    base.update(parts)
    return base


def rotas_de(cid):
    return [motor.memory_about(m) for m in motor._iter_memories(cid)
            if motor.memory_kind(m) == motor.ROTA]


def fm_de(item_id):
    return motor.read_doc(motor.find_entity(item_id)[0])[0]


def dado(v):
    motor._roll_d20 = lambda: v


print("\n--- O encanamento: a prosa alcança quem decide -----------------------")

texto = motor.prose_of(TORVIN, MAPA)
check("a prosa de um item chega a quem arbitra", bool(texto), str(texto))
check("e vai COMO ESTÁ, sem resumo",
      texto and "portão lateral" in texto.lower(), str(texto))
check("a prosa de um LUGAR também chega",
      bool(motor.prose_of(TORVIN, "taverna-do-gancho")))
check("entidade inexistente devolve nada",
      motor.prose_of(TORVIN, "nao-existe-nada") is None)
check("item sem texto nenhum não inventa prosa",
      motor.prose_of(TORVIN, "seixo-branco") in (None, "")
      or isinstance(motor.prose_of(TORVIN, "seixo-branco"), str))

# SC-009: o que se manda ao Árbitro não cresce com o número de itens da cena
ctx = motor.get_context(TORVIN)
prompt = arbiter._context_for_prompt(ctx)
itens_no_prompt = prompt.get("itens_presentes") or []
check("SC-009: a descrição NÃO entra no contexto de toda cena",
      all("descricao" not in i and "texto" not in i for i in itens_no_prompt),
      str(itens_no_prompt[:1]))
check("e a cena tem itens de sobra para isso importar",
      len(itens_no_prompt) > 5, f"{len(itens_no_prompt)} itens")


print("\n--- O creator mode: nenhum campo declarado ---------------------------")

campos_mapa, campos_mudo = set(fm_de(MAPA)), set(fm_de(MUDO))
check("SC-001: item que ensina e item que não ensina têm os MESMOS campos",
      campos_mapa == campos_mudo, f"{sorted(campos_mapa)} vs {sorted(campos_mudo)}")
check("SC-002: nenhum campo do schema existe para ensinar caminhos",
      "teaches" not in campos_mapa)
check("o validador não conhece mais 'teaches'",
      not any("teaches" in e for e in validator.validate(
          {"type": "item", "id": "x", "name": "X", "teaches": 123})))
check("o Motor não expõe mais consulta de campo declarado",
      not hasattr(motor, "teaches_of"))
check("a tool `study` saiu do manifest",
      not any(t["name"] == "study" for t in arbiter.build_tools(ctx)))
check("`examine` e `learn_routes` entraram",
      {"examine", "learn_routes"} <= {t["name"] for t in arbiter.build_tools(ctx)})

enum_rotas = [t for t in arbiter.build_tools(ctx) if t["name"] == "learn_routes"]
_item = enum_rotas[0]["parameters"]["properties"]["rotas"]["items"] if enum_rotas else {}
check("o enum de learn_routes traz as rotas do MUNDO, não só as daqui",
      set(motor.all_route_ids()) <= set(_item.get("properties", {})
                                        .get("rota", {}).get("enum", [])),
      str(_item))
check("e a tool exige o TRECHO citado junto de cada caminho",
      "trecho" in (_item.get("required") or []), str(_item.get("required")))


print("\n--- Prosa não cria mundo --------------------------------------------")

dado(20)
antes = len(rotas_de(TORVIN))
out = motor.apply_resolution(TORVIN, res(learn_ops=aprender("rota-que-nao-existe")))
regras = {r.get("regra") for r in out.get("rejected") or []}
check("SC-006: rota inexistente é recusada", "rota_inexistente" in regras, str(regras))
check("e nada é aprendido por isso", len(rotas_de(TORVIN)) == antes)


print("\n--- O teste por rota -------------------------------------------------")

dado(20)
out = motor.apply_resolution(TORVIN, res(
    learn_ops=aprender("portao-lateral", "trilha-do-patio", "subida-do-corvo")))
check("dado alto: as três são decifradas",
      len(out.get("learn_ops_applied") or []) == 3,
      str(out.get("learn_ops_applied")))
check("uma rolagem POR ROTA, não uma para o conjunto",
      len([r for r in out.get("rolls") or [] if r.get("tipo") == "leitura"]) == 3,
      str(out.get("rolls")))

# limpa o conhecimento para testar a falha
for _p in (motor.find_character_folder(ELGA) / "memories").glob("*.md"):
    _p.unlink()
dado(1)
out = motor.apply_resolution(ELGA, res(learn_ops=aprender("trilha-do-patio")))
check("dado baixo: não decifra", not (out.get("learn_ops_applied") or []))
check("e a recusa é leitura_falhou",
      any(r.get("regra") == "leitura_falhou" for r in out.get("rejected") or []))
check("SC-003: nada foi aprendido nessa leitura",
      "trilha-do-patio" not in rotas_de(ELGA))

dado(20)
motor.apply_resolution(ELGA, res(learn_ops=aprender("trilha-do-patio")))
check("voltar ao material dá nova chance", "trilha-do-patio" in rotas_de(ELGA))

# SC-005: já conhecido renova SEM rolagem
dado(1)
out = motor.apply_resolution(ELGA, res(learn_ops=aprender("trilha-do-patio")))
check("SC-005: rota já conhecida NUNCA falha, mesmo com dado 1",
      bool(out.get("learn_ops_applied")), str(out.get("rejected")))
check("e não gasta rolagem nenhuma",
      not [r for r in out.get("rolls") or [] if r.get("tipo") == "leitura"])
check("e vem marcada como renovação, não como descoberta",
      out["learn_ops_applied"][0].get("renovou") is True)

# SC-004: INT importa
fm_t, _ = motor.read_doc(motor.find_character_folder(TORVIN) / "character.md")
fm_e, _ = motor.read_doc(motor.find_character_folder(ELGA) / "character.md")
mod_t = motor.attr_modifier((fm_t.get("attributes") or {}).get("INT", 10))
mod_e = motor.attr_modifier((fm_e.get("attributes") or {}).get("INT", 10))
if mod_t != mod_e:
    dificil = motor.LEARN_ROUTE_DC - max(mod_t, mod_e)
    check("SC-004: o de INT maior passa num dado em que o outro falharia",
          dificil <= motor.LEARN_ROUTE_DC - min(mod_t, mod_e),
          f"mods {mod_t} vs {mod_e}")
check("a dificuldade é FIXA, não dada pelo Árbitro",
      isinstance(motor.LEARN_ROUTE_DC, int))


print("\n--- SC-007: o material é professor, não fonte ------------------------")

pasta = motor.find_entity("trilha-do-patio")
shutil.rmtree(motor.find_entity(MAPA)[0].parent)
check("perder o material NÃO desfaz o que se aprendeu",
      "trilha-do-patio" in rotas_de(ELGA))
check("e a prosa dele deixa de existir", motor.prose_of(ELGA, MAPA) is None)


print("\n--- O relato: as DUAS metades ---------------------------------------")

dado(20)
out = motor.apply_resolution(TORVIN, res(learn_ops=aprender("atalho-fechado")))
efeitos = server_app.inworld_effects(out)
check("o que decifrou chega à narração", bool(efeitos), str(efeitos))
check("com NOME do caminho, nunca id",
      efeitos and "atalho-fechado" not in efeitos[0], str(efeitos))

dado(1)
out = motor.apply_resolution(ELGA, res(learn_ops=aprender("subida-do-corvo")))
falhas = server_app.inworld_failures(out.get("rejected") or [])
check("o que NÃO decifrou também chega", bool(falhas), str(falhas))
check("e soa como dificuldade de leitura, não como proibição",
      falhas and "não foi movido" not in falhas[0]["o_que_falhou"]
      and "entender" in falhas[0]["o_que_falhou"], str(falhas))
check("SC-008: nem id, nem DC, nem dado no que chega ao jogador",
      falhas and not any(t in falhas[0]["o_que_falhou"]
                         for t in ("subida-do-corvo", "12", "d20", "DC")),
      str(falhas))

check("aprender deixa memória em quem aprendeu (Princípio X)",
      any("Decifrei" in (m.get("summary") or "")
          for m in motor._iter_memories(TORVIN)),
      str([m.get("summary") for m in motor._iter_memories(TORVIN)][-3:]))


print("\n--- A citação do trecho (spec 014, ajuste do mantenedor) --------------")

import version as _v  # noqa: E402

check("o server declara versão SemVer",
      _v.__version__.count(".") == 2 and _v.__version__[0].isdigit(), _v.__version__)

# a citação NÃO é validada pelo Motor — existe para o devlog. O que se cobra é
# que ela ATRAVESSE até o resultado, senão o log não a teria.
dado(20)
out = motor.apply_resolution(ELGA, res(
    lido=["um atalho curto e barrado por um portão"],
    learn_ops=[{"rotas": ["atalho-fechado"],
                "citacoes": [{"rota": "atalho-fechado",
                              "trecho": "um atalho curto e barrado"}]}]))
aplicado = out.get("learn_ops_applied") or []
check("a citação chega ao resultado, para o log",
      aplicado and aplicado[0].get("trecho") == "um atalho curto e barrado",
      str(aplicado))

# o Motor confere PRESENÇA, não sentido: ele não avalia se o texto "quer dizer"
# a rota — só se as palavras citadas estão lá. Trecho ausente da fonte é recusa.
for _p in (motor.find_character_folder(TORVIN) / "memories").glob("*.md"):
    _p.unlink()
dado(20)
out = motor.apply_resolution(TORVIN, res(learn_ops=[{
    "rotas": ["subida-do-corvo"],
    "citacoes": [{"rota": "subida-do-corvo", "trecho": "isto não está no texto"}]}]))
check("trecho ausente da fonte é RECUSADO",
      not out.get("learn_ops_applied"), str(out.get("learn_ops_applied")))
check("mas o Motor não julga SENTIDO: citação presente basta, ainda que a "
      "ligação com a rota seja frouxa",
      bool(motor.apply_resolution(TORVIN, res(
          lido=["a subida do corvo fica adiante"],
          learn_ops=[{"rotas": ["subida-do-corvo"],
                      "citacoes": [{"rota": "subida-do-corvo",
                                    "trecho": "fica adiante"}]}]
      )).get("learn_ops_applied")))

# a falha também carried_item_ids a citação: auditar por que ele propôs algo importa mais
# quando não deu certo
# rota que ela NÃO conhece: conhecida renovaria sem rolagem e não haveria recusa
for _p in (motor.find_character_folder(ELGA) / "memories").glob("*.md"):
    _p.unlink()
dado(1)
out = motor.apply_resolution(ELGA, res(learn_ops=[{
    "rotas": ["subida-do-corvo"],
    "citacoes": [{"rota": "subida-do-corvo", "trecho": "degraus cavados na pedra"}]}]))
rej = out.get("rejected") or []
check("a recusa também registra a citação",
      any(r.get("trecho") == "degraus cavados na pedra" for r in rej), str(rej))


print("\n--- A citação passa a ser CONFERIDA (decisão do mantenedor) ----------")

_carta = "Dois traços a carvão. Um mostra a subida do corvo, degraus cavados."

check("citação literal confere", motor.quote_matches("subida do corvo", _carta))
check("citação cortada nas pontas confere (margem)",
      motor.quote_matches("mostra a subida do corvo degraus", _carta))
check("acento e caixa não atrapalham",
      motor.quote_matches("DOIS TRACOS A CARVAO", _carta))
check("citação INVENTADA não confere",
      not motor.quote_matches("A carta menciona a ladeira do sal", _carta))
check("citação vazia não confere", not motor.quote_matches("", _carta))

# no turno: sem o texto lido, nada é conferido (retrocompatível); com o texto,
# a rota que a citação não sustenta é RECUSADA
for _p in (motor.find_character_folder(TORVIN) / "memories").glob("*.md"):
    _p.unlink()
dado(20)
out = motor.apply_resolution(TORVIN, res(
    lido=[_carta],
    learn_ops=[{"rotas": ["subida-do-corvo", "trilha-do-patio"],
                "citacoes": [
                    {"rota": "subida-do-corvo", "trecho": "a subida do corvo"},
                    {"rota": "trilha-do-patio",
                     "trecho": "A carta menciona a trilha do pátio"}]}]))
aprendidas = {a["rota"] for a in (out.get("learn_ops_applied") or [])}
check("a rota com citação REAL é aprendida", "subida-do-corvo" in aprendidas,
      str(aprendidas))
check("a rota com citação INVENTADA é recusada",
      "trilha-do-patio" not in aprendidas, str(aprendidas))
check("e a recusa diz que aquilo não está escrito ali",
      any(r.get("regra") == "citacao_nao_confere" for r in out.get("rejected") or []),
      str([r.get("regra") for r in out.get("rejected") or []]))
# a brecha que a medição fechou: sem nada lido, o modelo inventava a citação e
# a conferência não se aplicava. Citação que não se pode conferir vale o mesmo
# que citação falsa.
_sem_leitura = motor.apply_resolution(ELGA, res(
    learn_ops=[{"rotas": ["atalho-fechado"],
                "citacoes": [{"rota": "atalho-fechado",
                              "trecho": "qualquer coisa"}]}]))
check("sem NADA lido no turno, a rota é recusada",
      not _sem_leitura.get("learn_ops_applied"),
      str(_sem_leitura.get("learn_ops_applied")))
check("e o motivo é a citação que não confere",
      any(r.get("regra") == "citacao_nao_confere"
          for r in _sem_leitura.get("rejected") or []))


print("\n--- O elo examine -> conferência, PELO ÁRBITRO ------------------------")

# Este teste existe por um bug real: o registro do texto lido some se alguém
# mexer no guard do `examine`, e a suíte não notava — todos os outros testes
# montam a resolução NA MÃO, passando `lido` explicitamente. O furo vivia
# exatamente no elo que ninguém exercitava.
# o mapa foi destruído no teste da SC-007 lá em cima (perder a fonte não desfaz
# o aprendizado). Refaz o material para exercitar o elo.
motor.write_doc(motor.WORLD_DIR / "taverna-do-gancho" / MAPA / "item.md",
                {"type": "item", "id": MAPA, "name": "Mapa do Salgado",
                 "size": "PP", "weight_kg": 0.2},
                "O pergaminho desenha o portão lateral, a porta baixa que liga o "
                "salão ao calor da forja.")
_ctx_arb = motor.get_context(ELGA)


def _loop_falso(_sys, _user, _tools, execute, _max):
    """Simula o Árbitro: lê, e cita uma verdade e uma invenção."""
    execute("examine", {"alvo": MAPA})
    execute("learn_routes", {"rotas": [
        {"rota": ROTA, "trecho": "portão lateral"},
        {"rota": "subida-do-corvo", "trecho": "isto o mapa jamais disse"},
    ]})
    return {"stopped": "tools", "text": ""}


# spec 020: o learn aplica-e-registra DENTRO do resolve_with_tools (fase única),
# na pasta do ator (ELGA). Limpa a memória e injeta o dado ANTES, e confere o
# outcome direto — não há mais um apply_resolution separado depois.
for _p in (motor.find_character_folder(ELGA) / "memories").glob("*.md"):
    _p.unlink()
dado(20)
_r = arbiter.resolve_with_tools({"action": "lê o mapa"}, _ctx_arb, _loop_falso)
check("o texto lido pelo `examine` FICA registrado no turno",
      bool(_r.get("lido")), str(_r.get("lido")))
check("e é o texto real do material",
      _r.get("lido") and "portão lateral" in _r["lido"][0].lower(),
      str(_r.get("lido"))[:120])

_ok = {a["rota"] for a in (_r.get("learn_ops_applied") or [])}
_barradas = {x.get("rota") for x in (_r.get("rejected") or [])
             if x.get("regra") == "citacao_nao_confere"}
check("pelo Árbitro: citação VERDADEIRA é aprendida", ROTA in _ok, str(_ok))
check("pelo Árbitro: citação INVENTADA é barrada",
      "subida-do-corvo" in _barradas, str(_barradas))


print("\n--- Aprender NÃO se perde quando o turno também ANDA -----------------")

# Bug real (mapa da Sarga): o Árbitro aprendeu do mapa E pediu enter_route no
# mesmo turno; o atalho do movimento no topo de apply_resolution descartava o
# learn_ops em silêncio. Agora o enter_route vem POR ÚLTIMO — aprende no lugar,
# depois parte.
for _p in (motor.find_character_folder(TORVIN) / "memories").glob("*.md"):
    _p.unlink()
dado(20)
_out = motor.apply_resolution(TORVIN, res(
    movement={"enter_route": ROTA},
    lido=[FONTE],
    learn_ops=aprender("subida-do-corvo")))
check("aprendeu do mapa MESMO com enter_route no turno (não foi engolido)",
      motor.knows_route(TORVIN, "subida-do-corvo"),
      str(_out.get("learn_ops_applied")))
check("e também partiu (o movimento vem por último, não descarta)",
      any(a.get("movement") for a in _out.get("applied") or []),
      str(_out.get("applied")))


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 17 (spec 014) passaram.")
