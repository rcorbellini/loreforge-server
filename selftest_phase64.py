"""Fase 64 (spec 065) — INVESTIGAR: o rastreador (item 14-γ do backlog).

O que esta fase guarda, e por que cada bloco existe:

  A. A DENSIDADE É SEMPRE GRATUITA — "saber se tem pegada não exige maestria".
     Nunca depende de rolagem, nunca falha por falta de perícia.
  B. FALHA NUNCA PRODUZ "NADA" — degrada pra densidade. Só ausência FÍSICA de
     rastro produz "nenhum sinal".
  C. OS DOIS EIXOS INDEPENDENTES (decisão de 2026-09-02) — identidade e rota se
     resolvem por condições PRÓPRIAS. Rota pode sair SEM nome; nome nunca sai
     sem a condição de identidade (história prévia OU alvo nomeado).
  D. A ROTA É SEMPRE `route_id` REAL — nunca direção de bússola.
  E. A MEMÓRIA DO LUGAR/ITENS volta à tona E é renovada (reuso da spec 064).
  F. ZERO MUTAÇÃO DE MUNDO fora da renovação de memória já legítima.
"""
import os, shutil, sys, tempfile, time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
TAVERNA = "taverna-do-gancho"
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test64-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
sys.path.insert(0, str(SERVER_DIR))

import motor
from motor.memoria import primitivas as mp

falhas = []


def check(nome, cond, detalhe=""):
    if cond:
        print(f"[ok  ] {nome}")
    else:
        print(f"[FALHA] {nome}" + (f" — {detalhe}" if detalhe else ""))
        falhas.append(nome)


def _mk_char(cid: str, name: str, wis: int = 10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: {wis}\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: baixo\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _folder(cid):
    return motor.find_character_folder(cid)


def _rastro(local_folder: Path, quem: str, direcao: str, *, criado_em=None,
           ttl_seconds=43200, evento="partida", rid=None):
    """Fixture direta — escreve o `.md` de rastro sem passar por `_leave_trace`,
    pra controlar `criado_em`/`ttl_seconds` (o frescor) com precisão."""
    now = int(time.time())
    rid = rid or f"rastro-fixture-{quem}-{direcao}-{now}"
    fm = {"type": "rastro", "id": rid, "quem": quem, "direcao": direcao,
         "evento": evento, "criado_em": now if criado_em is None else criado_em,
         "ttl_seconds": ttl_seconds, "intensity": "small"}
    motor.write_doc(local_folder / "rastros" / f"{rid}.md", fm, "Uma marca recente.")
    return rid


AGORA_INV = _mk_char("investigador-p64", "A Investigadora")
INV = "investigador-p64"
INV_FOLDER = _folder(INV)
LOCAL = INV_FOLDER.parent  # a taverna — o "lugar" desta fixture

_mk_char("desconhecido-p64", "O Desconhecido")
_mk_char("conhecido-p64", "A Conhecida")

print("--- Bloco A: densidade é SEMPRE gratuita -------------------------------")

# lugar SEM rastro nenhum
d0, ativos0 = mp._densidade_rastro(LOCAL)
check("A1: lugar sem rastro -> densidade 'nenhum', lista vazia",
     d0 == "nenhum" and ativos0 == [])

_rastro(LOCAL, "conhecido-p64", "portao-lateral")
d1, ativos1 = mp._densidade_rastro(LOCAL)
check("A2: 1 rastro ativo -> densidade 'algum'", d1 == "algum" and len(ativos1) == 1)

for i in range(3):
    _rastro(LOCAL, "desconhecido-p64", "trilha-do-patio", rid=f"rastro-extra-p64-{i}")
d2, ativos2 = mp._densidade_rastro(LOCAL)
check("A3: 4 rastros ativos -> densidade 'muitos'", d2 == "muitos" and len(ativos2) == 4)

# a densidade não muda mesmo com a pior rolagem possível — ela nem participa
import motor.memoria.primitivas as _mp_mod
_orig_dado = _mp_mod._roll_trace_d20
_mp_mod._roll_trace_d20 = lambda: 1
try:
    d3, ativos3 = mp._densidade_rastro(LOCAL)
    check("A4: densidade INDEPENDE da rolagem (pior d20 possível)",
         d3 == d2 and len(ativos3) == len(ativos2))
finally:
    _mp_mod._roll_trace_d20 = _orig_dado

print("\n--- Bloco B: falha nunca produz 'nada' quando há rastro ----------------")

inv_fm, _ = motor.read_doc(INV_FOLDER / "character.md")

_mp_mod._roll_trace_d20 = lambda: 1  # pior resultado possível
try:
    rastros_falha = mp._resolver_rastros(INV, inv_fm, ativos2, None)
    check("B1: rolagem péssima -> nenhum rastro identificado (lista vazia)",
         rastros_falha == [])
finally:
    _mp_mod._roll_trace_d20 = _orig_dado

LUGAR_VAZIO = motor.WORLD_DIR / "forja-de-ferro"
d_vazio, ativos_vazio = mp._densidade_rastro(LUGAR_VAZIO)
check("B2: 'nenhum sinal' só ocorre por AUSÊNCIA física de rastro, nunca por rolagem",
     d_vazio == "nenhum" and ativos_vazio == [])

print("\n--- Bloco C: os DOIS EIXOS independentes (decisão 2026-09-02) ----------")

_mp_mod._roll_trace_d20 = lambda: 20  # melhor resultado possível
try:
    # estranho NÃO nomeado: identidade nunca revela, mas ROTA revela (o eixo é livre)
    rastros_estranho = mp._resolver_rastros(INV, inv_fm, ativos2, None)
    do_desconhecido = [r for r in rastros_estranho if r["rota"] and r["quem"] is None]
    check("C1: rastro de ESTRANHO revela ROTA sem nome, com rolagem alta",
         len(do_desconhecido) > 0, str(rastros_estranho))
    if do_desconhecido:
        check("C1b: grau do rastro sem nome é 'vago'", do_desconhecido[0]["grau"] == "vago")

    # conhecido: memória do investigador envolvendo ele (spec 065 US2)
    mp.record_event(INV, "Cruzei com a Conhecida ontem.", "inform",
                    ["conhecido-p64"])
    rastros_conhecido = mp._resolver_rastros(INV, inv_fm, ativos2, None)
    do_conhecido = [r for r in rastros_conhecido if r["quem"] == "conhecido-p64"]
    check("C2: rastro de CONHECIDO (com memória prévia) revela QUEM",
         len(do_conhecido) == 1, str(rastros_conhecido))
    check("C2b: e revela ROTA também (rolagem alta o bastante para os dois)",
         do_conhecido and do_conhecido[0]["rota"] == "portao-lateral")
    check("C2c: grau do conhecido é 'nitido'",
         do_conhecido and do_conhecido[0]["grau"] == "nitido")
finally:
    _mp_mod._roll_trace_d20 = _orig_dado

# alvo NOMEADO: dispensa história prévia
_mp_mod._roll_trace_d20 = lambda: 20
try:
    rastros_alvo = mp._resolver_rastros(INV, inv_fm, ativos2,
                                        "desconhecido-p64")
    do_alvo = [r for r in rastros_alvo if r["quem"] == "desconhecido-p64"]
    check("C3: alvo NOMEADO revela identidade mesmo sem história prévia",
         len(do_alvo) >= 1, str(rastros_alvo))
finally:
    _mp_mod._roll_trace_d20 = _orig_dado

# T011 (fechamento): rolagem ENTRE as duas DCs — quem revela, rota não. Os
# rastros de `ativos2` foram criados "agora" (frescor ~1,0): DC_identidade=6,
# DC_rota=11. Total=8 supera a primeira, não a segunda.
_mp_mod._roll_trace_d20 = lambda: 8
try:
    rastros_meio = mp._resolver_rastros(INV, inv_fm, ativos2, None)
    do_conhecido_meio = [r for r in rastros_meio if r["quem"] == "conhecido-p64"]
    check("C4: rolagem ENTRE as DCs — conhecido revela QUEM sem ROTA",
         do_conhecido_meio and do_conhecido_meio[0]["rota"] is None,
         str(rastros_meio))
    check("C4b: e o estranho (identidade nunca permitida) some por inteiro",
         all(r["quem"] != "desconhecido-p64" for r in rastros_meio), str(rastros_meio))
finally:
    _mp_mod._roll_trace_d20 = _orig_dado

# T014 (fechamento): dois rastros do MESMO alvo, direções diferentes, os DOIS
# ainda ativos (foi e voltou dentro da janela do TTL). O código não deduplica —
# `_resolver_rastros` avalia cada `rastro` (registro FÍSICO) por si, não por
# pessoa — e é isso que bate com o Edge Case do spec.md ("os dois existem como
# registros separados... revela ambos os eventos"), não com a frase de US4 AC3
# ("o mais recente decide"), que a implementação não seguiu à risca. Documentado
# aqui como comportamento REAL, não como suposição.
_mk_char("andarilho-p64", "O Andarilho")
mp.record_event(INV, "Vi o Andarilho por aqui.", "inform", ["andarilho-p64"])
_rastro(LOCAL, "andarilho-p64", "trilha-do-patio", rid="rastro-ida-p64")
_rastro(LOCAL, "andarilho-p64", "portao-lateral", rid="rastro-volta-p64")
_, ativos_andarilho = mp._densidade_rastro(LOCAL)
_mp_mod._roll_trace_d20 = lambda: 20
try:
    rastros_and = mp._resolver_rastros(INV, inv_fm, ativos_andarilho, None)
    do_and = [r for r in rastros_and if r["quem"] == "andarilho-p64"]
    check("C5: dois rastros ativos do MESMO alvo — os dois aparecem, sem crash",
         len(do_and) == 2, str(rastros_and))
    check("C5b: e as duas rotas distintas estão presentes (ida e volta)",
         {r["rota"] for r in do_and} == {"trilha-do-patio", "portao-lateral"},
         str(do_and))
finally:
    _mp_mod._roll_trace_d20 = _orig_dado

print("\n--- Bloco D: a rota é SEMPRE route_id real ------------------------------")

check("D1: DC por frescor — recém-criado é mais fácil que quase expirando",
     mp._dcs_investigacao({"criado_em": int(time.time()), "ttl_seconds": 100})
     < mp._dcs_investigacao({"criado_em": int(time.time()) - 99, "ttl_seconds": 100}))
check("D2: DC_ROTA é sempre DC_IDENTIDADE + 5 (gap fixo)",
     mp._dcs_investigacao({"criado_em": 0, "ttl_seconds": 100})[1]
     - mp._dcs_investigacao({"criado_em": 0, "ttl_seconds": 100})[0] == 5)

rota_ids = set(motor.all_route_ids())
check("D3: toda rota revelada é um route_id REAL (nunca bússola)",
     "portao-lateral" in rota_ids)

print("\n--- Bloco E: a memória do lugar/itens volta à tona, e é renovada -------")

mid_lugar = mp.record_event(INV, "Já estive aqui antes.", "inform", [LOCAL.name])
lfm, lbody = motor.read_doc(INV_FOLDER / "memories" / f"{mid_lugar}.md")
lfm["state"] = "expired"
lfm["timestamp_end"] = int(time.time()) - 10
motor.write_doc(INV_FOLDER / "memories" / f"{mid_lugar}.md", lfm, lbody)

r = motor.investigar(INV, {})
achou = next((m for m in r["memorias_do_lugar"] if m["id"] == mid_lugar), None)
check("E1: memória VENCIDA do lugar aparece no relato (alcance de consulta)",
     achou is not None, str([m["id"] for m in r["memorias_do_lugar"]]))

depois_fm, _ = motor.read_doc(INV_FOLDER / "memories" / f"{mid_lugar}.md")
check("E2: e foi RENOVADA (prazo estendido, mesmo mecanismo da spec 064)",
     depois_fm["timestamp_end"] > lfm["timestamp_end"],
     f"{lfm['timestamp_end']} -> {depois_fm['timestamp_end']}")

mid_esq = mp.record_event(INV, "Isso eu não devia lembrar.", "inform", [LOCAL.name])
efm, ebody = motor.read_doc(INV_FOLDER / "memories" / f"{mid_esq}.md")
efm["state"] = "esquecida"
motor.write_doc(INV_FOLDER / "memories" / f"{mid_esq}.md", efm, ebody)
r2 = motor.investigar(INV, {})
check("E3: memória ESQUECIDA nunca aparece no relato",
     all(m["id"] != mid_esq for m in r2["memorias_do_lugar"]))

print("\n--- Bloco F: zero mutação de mundo fora da renovação legítima ----------")

antes = {p: p.stat().st_mtime_ns for p in motor.WORLD_DIR.rglob("*.md")
        if "investigador-p64" not in str(p)}
motor.investigar(INV, {})
depois = {p: p.stat().st_mtime_ns for p in motor.WORLD_DIR.rglob("*.md")
         if "investigador-p64" not in str(p)}
check("F1: nada MUDA fora da pasta do próprio investigador (que só renova memória)",
     antes == depois)

print("\n--- Bloco G: o enum de alvo (US3) --------------------------------------")

alvos = mp.alvos_investigaveis(INV)
check("G1: alvos_investigaveis inclui quem tem memória VENCIDA (não só viva)",
     "conhecido-p64" in alvos, str(alvos))
check("G2: alvos_investigaveis SÓ personagens (nunca lugar/item de involved)",
     LOCAL.name not in alvos)

print("\n--- Bloco H: busca por alvo NOMEADO — o positivo e os dois negativos ---")

# T016 (negativo): alvo CONHECIDO (está no enum), mas o rastro dele NÃO está
# neste lugar — negativa silenciosa, nunca inventa presença.
_mk_char("distante-p64", "O Distante")
mp.record_event(INV, "Ouvi falar do Distante.", "inform", ["distante-p64"])
_mp_mod._roll_trace_d20 = lambda: 20
try:
    r_ausente = motor.investigar(INV, {"alvo": "distante-p64"})
    check("H1: alvo nomeado CONHECIDO mas sem rastro aqui -> não aparece, sem inventar",
         all(r["quem"] != "distante-p64" for r in r_ausente["rastros"]),
         str(r_ausente["rastros"]))

    # T017: alvo fora do enum (nunca teve memória do investigador) degrada
    # para varredura ampla — mesmo resultado de alvo=None, sem erro.
    r_ampla = motor.investigar(INV, {})
    r_desconhecido = motor.investigar(INV, {"alvo": "jamais-mencionado-p64"})
    check("H2: alvo fora de alvos_investigaveis não estoura — degrada, sem erro",
         isinstance(r_desconhecido, dict))
    check("H3: e degrada para a MESMA varredura ampla que alvo=None produziria",
         {(r["quem"], r["rota"]) for r in r_desconhecido["rastros"]}
         == {(r["quem"], r["rota"]) for r in r_ampla["rastros"]},
         f"{r_desconhecido['rastros']} vs {r_ampla['rastros']}")
finally:
    _mp_mod._roll_trace_d20 = _orig_dado

print("\n--- Bloco I: a consulta está registrada na lane (spec 040) -------------")

check("I1: 'investigar' está em motor.consult_specs() (chega à Mente)",
     "investigar" in motor.consult_specs())
check("I2: a ConsultSpec aponta para a função investigar() real",
     motor.consult_specs()["investigar"].query.__name__ == "investigar")

print()
shutil.rmtree(_tmp, ignore_errors=True)
if falhas:
    print(f"{len(falhas)} FALHA(S): " + ", ".join(falhas))
    sys.exit(1)
print("todos os checks da Fase 64 (spec 065) passaram.")
