"""Auto-teste da Fase 58 — Cantar o feito (spec 058).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com `ask`
forçado) para o comportamento da GUARDA (enum de memórias, dedup, zero-LLM
estrutural). Cobre os doze invariantes de `contracts/sing-tool.md`:

  1. `ask_about` byte-idêntico — coberto por `selftest_phase20.py` (SC-011); não
     duplicado aqui.
  2. `juizo.julgamento` recupera quebra de linha crua; 4 formatos válidos idênticos;
     resposta truncada cai no default.
  3. Intensidade do reconto <= a da fonte (o TETO), para desfecho ótimo.
  4. NÃO existe caminho que recuse cantar por cena/plateia/banalidade — só o portão
     de estado (dormindo).
  5. Cantar sozinho: acontece, grava só no cantor, carimba `musica`.
  6. Re-tentar o MESMO `memoria_id` no turno é barrado; outro episódio passa.
  7. Fonte que já era boato -> reconto 3º grau anônimo, cantor fora de `involved`.
  8. Sujeito presente NÃO recebe reconto, mas RECEBE `witness_musica`.
  9. Dez canções iguais -> 2 memórias por ouvinte, `vezes` crescendo, intensidade
     igual à da primeira.
  10. `witness_accuse` intacto depois do conserto de valência — coberto por
      `selftest_phase30.py`; não duplicado aqui.
  11. Nenhuma nota/DC/dado/proficiência em nenhum payload de aplicação.
  12. Todo desfecho (inclusive fracasso e o portão) produz uma frase in-world.

Uso:  python3 selftest_phase58.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test58-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
import app as server_app  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"
HEROI = "torvin-ferreiro"          # já existe no fixture — não precisa estar presente


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def pasta(cid):
    return motor.find_character_folder(cid)


def _mk_char(cid: str, name: str, cha: int = 16, presente_em: str = TAVERNA):
    d = motor.WORLD_DIR / presente_em / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n"
        f"  CHA: {cha}\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_memoria(cid: str, texto: str, intensity="large", involved=None,
                ouvido_de=None, evento="attack"):
    folder = pasta(cid)
    return motor.memoria._write_memory(
        folder, texto, intensity=intensity, involved=involved or [],
        ouvido_de=ouvido_de, evento=evento, domain="combate")


def _mems(cid, evento=None):
    out = list(motor._iter_memories(cid))
    if evento:
        out = [m for m in out if m.get("evento") == evento]
    return out


def res(**parts):
    return {"musica_ops": [], **parts}


force = motor._roll_d20

# =========================================================================== #
# Fixture: um cantor (CHA alto, proficiência musica alta via memória prévia
# recorrente-manual) e três ouvintes na mesma taverna.
# =========================================================================== #

CANTOR = "renn-cantor-p58"
_mk_char(CANTOR, "Renn, o Trovador (teste)", cha=16)
OUV_A, OUV_B, OUV_SUJEITO = "ouvinte-a-p58", "ouvinte-b-p58", "ouvinte-sujeito-p58"
_mk_char(OUV_A, "Ouvinte A")
_mk_char(OUV_B, "Ouvinte B")
_mk_char(OUV_SUJEITO, "Ouvinte Sujeito")


def _proficiencia_alta(cid):
    """Empurra `proficiencies_for(cid)['musica']` bem acima de 0, via memórias
    reais de domínio `musica` — nunca via `skills` (FR-019)."""
    for _ in range(8):
        motor.memoria._write_memory(pasta(cid), "Cantei muito bem.",
                                    intensity="giant", involved=[], domain="musica",
                                    evento="sing_otimo")


_proficiencia_alta(CANTOR)
NIVEL_MUSICA = motor.proficiencies_for(CANTOR)["musica"]
check("fixture: proficiência em musica > 0 antes de qualquer canção real",
      NIVEL_MUSICA > 0, str(NIVEL_MUSICA))
for m in list((pasta(CANTOR) / "memories").glob("*.md")):
    m.unlink()   # limpa as memórias de fixture — os testes abaixo contam arquivo

print("\n--- 2. juizo.julgamento: quebra de linha crua e formatos já válidos ------")

_raw_quebrada = ('{\n  "letra": "verso um,\nverso dois,\nverso tres,\nverso um."\n}')
_r = motor.juizo.julgamento(_raw_quebrada, {}, {"letra": ""})
check("2a. quebra de linha CRUA dentro de string é recuperada",
      _r["letra"] == "verso um,\nverso dois,\nverso tres,\nverso um.", repr(_r))

_r2 = motor.juizo.julgamento('{"cancao": 8, "letra": "uma linha só"}',
                             {"cancao": 5}, {"letra": ""})
check("2b. resposta de uma linha (JÁ válida) segue idêntica",
      _r2 == {"cancao": 8, "letra": "uma linha só"}, str(_r2))

_r3 = motor.juizo.julgamento(
    'texto antes {"a": 1, "b": "com \\"aspas\\" dentro"} texto depois',
    {"a": 0}, {"b": ""})
check("2c. texto antes/depois do objeto + aspas escapadas seguem idênticos",
      _r3 == {"a": 1, "b": 'com "aspas" dentro'}, str(_r3))

_r4 = motor.juizo.julgamento('{"letra": "com \\n escapado de verdade"}',
                             {}, {"letra": ""})
check("2d. \\n JÁ escapado (de verdade) segue idêntico",
      _r4["letra"] == "com \n escapado de verdade", repr(_r4))

_r5 = motor.juizo.julgamento('{"letra": "Refrao: \n incompleta e trunca',
                             {}, {"letra": "default"})
check("2e. resposta TRUNCADA (nunca fecha) cai no default — nada a recuperar",
      _r5["letra"] == "default", repr(_r5))

print("\n--- 3/9/11/12. desfecho ÓTIMO: teto, réplica, segredo, narração --------")

mem_id = _mk_memoria(CANTOR, "Vi Torvin derrubar o que saiu do poço.",
                     intensity="large", involved=[HEROI])
op = {"memoria_id": mem_id, "instrumento": None,
     "letra": "No Gancho, onde o fogo arde / Torvin desceu ao poço "
              "/ ninguém falou nada / No Gancho, onde o fogo arde",
     "instrumento_nota": 0}

motor._roll_d20 = lambda: 20      # CHA 16 (+3) + nivel alto + 20 -> ótimo, folga
out = motor.apply_resolution(CANTOR, res(musica_ops=[op]))
motor._roll_d20 = force

aplicadas = out.get("musica_ops_applied") or []
check("3/9. uma op aplicada, desfecho ótimo", len(aplicadas) == 1
     and aplicadas[0].get("desfecho") == "otimo", str(aplicadas))

check("11. nenhuma nota/DC/dado/proficiência no payload aplicado",
      aplicadas and not ({"nota", "dc", "d20", "nivel_musica", "roll_info",
                          "rolagem"} & set(aplicadas[0])),
      str(aplicadas[0] if aplicadas else None))

reconto_a = [m for m in _mems(OUV_A) if m.get("evento") == "hearsay_reconto"]
reconto_b = [m for m in _mems(OUV_B) if m.get("evento") == "hearsay_reconto"]
check("3. ouvinte A ganhou reconto do feito, intensidade == fonte (0 degraus, ótimo)",
      len(reconto_a) == 1 and reconto_a[0].get("intensity") == "large",
      str(reconto_a))
check("3. teto: NUNCA giant (a fonte é large) mesmo com d20=20 e proficiência alta",
      len(reconto_a) == 1 and reconto_a[0].get("intensity") != "giant", str(reconto_a))
check("3. reconto: o HERÓI está em involved (a reputação alcança quem não estava lá)",
      len(reconto_a) == 1 and HEROI in motor.memory_involved(reconto_a[0]),
      str(reconto_a))
check("3. ouvinte B também ganhou reconto (broadcast, não 1-para-1)",
      len(reconto_b) == 1, str(reconto_b))

wit_a = [m for m in _mems(OUV_A) if m.get("evento") == "witness_musica"]
check("witness_musica: ouvinte ganhou memória de reputação do cantor, POSITIVA",
      len(wit_a) == 1 and (wit_a[0].get("valence") or {}).get(CANTOR)
      == motor.POSITIVA, str(wit_a))

mem_cantor = [m for m in _mems(CANTOR) if m.get("evento") == "sing_otimo"]
check("cantor: uma memória do ato, domain=musica, about=memoria_id (recorrente)",
      len(mem_cantor) == 1 and mem_cantor[0].get("domain") == "musica"
      and mem_cantor[0].get("about") == mem_id, str(mem_cantor))

_fbol = server_app.inworld_effects(out)
check("12. o desfecho ÓTIMO produz frase in-world (Princípio X, nunca silêncio)",
      any("cantou" in f for f in _fbol) if _fbol else False, str(_fbol))

print("\n--- 8. sujeito PRESENTE: não recebe reconto, mas recebe witness_musica ---")

mem_id2 = _mk_memoria(CANTOR, "Vi o Ouvinte Sujeito salvar uma criança.",
                      intensity="medium", involved=[OUV_SUJEITO])
op2 = {"memoria_id": mem_id2, "instrumento": None,
      "letra": "No Gancho, sob o teto velho / o Sujeito salvou uma vida "
               "/ ninguém esqueceu aquilo / No Gancho, sob o teto velho",
      "instrumento_nota": 0}
motor._roll_d20 = lambda: 20
out2 = motor.apply_resolution(CANTOR, res(musica_ops=[op2]))
motor._roll_d20 = force

reconto_sujeito = [m for m in _mems(OUV_SUJEITO) if m.get("evento") == "hearsay_reconto"
                   and mem_id2 in (m.get("id") or "")]
# reconto_ids reportado pelo executor é a fonte de verdade de quem recebeu:
reconto_ids2 = (out2.get("musica_ops_applied") or [{}])[0].get("reconto_ids") or []
check("8a. o SUJEITO presente NÃO está entre os que receberam reconto",
      all(r.get("target") != OUV_SUJEITO for r in reconto_ids2), str(reconto_ids2))
wit_sujeito = [m for m in _mems(OUV_SUJEITO) if m.get("evento") == "witness_musica"]
check("8b. o SUJEITO presente RECEBE witness_musica (ouve cantarem sobre ele)",
      len(wit_sujeito) >= 1, str(wit_sujeito))

print("\n--- 7. fonte que já era BOATO: reconto 3º grau, anônimo, cantor fora ------")

mem_boato = _mk_memoria(CANTOR, "Dizem por aí: Torvin derrubou o que saiu do poço.",
                        intensity="medium", involved=[HEROI], ouvido_de="alguem-p58")
op3 = {"memoria_id": mem_boato, "instrumento": None,
      "letra": "No cais, sob a névoa fria / dizem que Torvin venceu algo "
               "/ ninguém sabe ao certo quem contou / No cais, sob a névoa fria",
      "instrumento_nota": 0}
_ouv_c = "ouvinte-c-p58"
_mk_char(_ouv_c, "Ouvinte C")
motor._roll_d20 = lambda: 20
out3 = motor.apply_resolution(CANTOR, res(musica_ops=[op3]))
motor._roll_d20 = force
reconto_c = [m for m in _mems(_ouv_c) if m.get("evento") == "hearsay_reconto"]
_corpo_c = ""
if reconto_c:
    _, _corpo_c = motor.read_doc(pasta(_ouv_c) / "memories" / f"{reconto_c[0]['id']}.md")
check("7a. reconto de fonte-boato nasce ANÔNIMO (3º grau: 'Dizem por aí')",
      len(reconto_c) == 1 and "Dizem por aí" in _corpo_c,
      f"{reconto_c} corpo={_corpo_c!r}")
check("7b. o CANTOR NÃO entra em involved do reconto de 3º grau (origem anônima)",
      len(reconto_c) == 1 and CANTOR not in motor.memory_involved(reconto_c[0]),
      str(reconto_c))

print("\n--- 5. cantar SOZINHO: acontece, não propaga, carimba musica -------------")

SOLO = "solitario-p58"
_mk_char(SOLO, "Solitário", presente_em="patio-das-brasas")
prof_antes = motor.proficiencies_for(SOLO)["musica"]
mem_solo = _mk_memoria(SOLO, "Vi uma estrela cair no rio.", intensity="medium",
                       involved=[HEROI])
op_solo = {"memoria_id": mem_solo, "instrumento": None,
          "letra": "No rio, sob o céu sem lua / a estrela caiu devagar "
                   "/ ninguém além de mim estava lá / No rio, sob o céu sem lua",
          "instrumento_nota": 0}
motor._roll_d20 = lambda: 15
out_solo = motor.apply_resolution(SOLO, res(musica_ops=[op_solo]))
motor._roll_d20 = force
aplicadas_solo = out_solo.get("musica_ops_applied") or []
check("5a. cantar sozinho ACONTECE (sem recusa)", len(aplicadas_solo) == 1,
      str(out_solo.get("rejected")))
check("5b. cantar sozinho NÃO grava reconto em ninguém",
      not (aplicadas_solo[0].get("reconto_ids") if aplicadas_solo else True),
      str(aplicadas_solo))
mem_solo_ator = [m for m in _mems(SOLO) if m.get("evento") in
                ("sing_otimo", "sing", "sing_ruim")]
check("5c. a memória do próprio cantor É gravada, mesmo sem plateia",
      len(mem_solo_ator) == 1, str(mem_solo_ator))
check("5d. a proficiência em musica CRESCEU depois de cantar sozinho",
      motor.proficiencies_for(SOLO)["musica"] > prof_antes,
      f"{prof_antes} -> {motor.proficiencies_for(SOLO)['musica']}")
_fbol_solo = server_app.inworld_effects(out_solo)
check("12b. cantar sozinho também narra (nunca silêncio)",
      bool(_fbol_solo) and any("ninguém" in f or "sozinho" not in f
                               for f in _fbol_solo), str(_fbol_solo))

print("\n--- 4. NENHUM caminho recusa por cena/plateia/banalidade ------------------")

# feito banal + plateia vazia SIMULTANEAMENTE — o pior caso, e ainda assim canta
BANAL_ATOR = "banal-p58"
_mk_char(BANAL_ATOR, "Ator Banal", presente_em="mirante-do-corvo")
mem_banal = _mk_memoria(BANAL_ATOR, "Comprei três pães na praça.",
                        intensity="small", involved=[HEROI])
op_banal = {"memoria_id": mem_banal, "instrumento": None,
           "letra": "Na praça, sob o sol fraco / comprei pão e nada mais "
                    "/ ninguém ali pra ouvir / Na praça, sob o sol fraco",
           "instrumento_nota": 0}
motor._roll_d20 = lambda: 1       # o pior dado possível
out_banal = motor.apply_resolution(BANAL_ATOR, res(musica_ops=[op_banal]))
motor._roll_d20 = force
aplicadas_banal = out_banal.get("musica_ops_applied") or []
check("4a. feito banal + plateia vazia + dado péssimo: AINDA ASSIM acontece "
     "(sem gate de mérito)",
      len(aplicadas_banal) == 1 and not out_banal.get("rejected"),
      str(out_banal.get("rejected")))
check("4b. o pior caso produz o desfecho FRACASSO, não uma recusa estrutural",
      aplicadas_banal and aplicadas_banal[0].get("desfecho") == "fracasso",
      str(aplicadas_banal))
check("4c. fracasso: NENHUM reconto (mas a memória do cantor existe)",
      aplicadas_banal and not aplicadas_banal[0].get("reconto_ids"),
      str(aplicadas_banal))
mem_banal_ator = [m for m in _mems(BANAL_ATOR) if m.get("evento") == "sing_ruim"]
check("4d. fracasso também carimba (sing_ruim) — cantar mal também fica",
      len(mem_banal_ator) == 1, str(mem_banal_ator))
_fbol_banal = server_app.inworld_effects(out_banal)
check("12c. o fracasso produz frase in-world própria (nunca silêncio)",
      bool(_fbol_banal), str(_fbol_banal))

print("\n--- 4/estado: o ÚNICO portão real é dormir (\"descansando\") ---------------")

DORMINDO = "dormindo-p58"
d = _mk_char(DORMINDO, "Dorminhoco")
fm, body = motor.read_doc(d / "character.md")
fm["status"]["descansando_desde"] = 1  # qualquer valor truthy -> is_resting=True
motor.write_doc(d / "character.md", fm, body)
mem_x = _mk_memoria(DORMINDO, "Vi algo.", intensity="small", involved=[HEROI])
out_dorme = motor.apply_resolution(DORMINDO, res(musica_ops=[
    {"memoria_id": mem_x, "instrumento": None, "letra": "x", "instrumento_nota": 0}]))
regras_dorme = {r.get("regra") for r in out_dorme.get("rejected") or []}
check("4e. cantor dormindo: ÚNICA recusa possível ('descansando')",
      "descansando" in regras_dorme, str(regras_dorme))

print("\n--- 6. dedup de turno (guarda) e a listagem na FACE -----------------------")

DEDUP = "dedup-p58"
d_dedup = _mk_char(DEDUP, "Dedup Cantor")
(d_dedup / "alaude-dedup-p58").mkdir()
(d_dedup / "alaude-dedup-p58" / "item.md").write_text(
    "---\ntype: item\nid: alaude-dedup-p58\nname: Alaúde\norigin: editorial\n"
    "size: M\nweight_kg: 2.0\nstate:\n  slot: mao\n---\nUm alaúde qualquer.\n",
    encoding="utf-8")
mem_dedup_a = _mk_memoria(DEDUP, "Vi um dragão pousar.", intensity="large",
                          involved=[HEROI])
mem_dedup_b = _mk_memoria(DEDUP, "Vi uma ponte desabar.", intensity="large",
                          involved=[HEROI])


def _ask_conta_chamadas(estado):
    def _f(_s, _u):
        estado["n"] += 1
        return '{"letra": "verso / verso / verso / verso"}'
    return _f


ctx_dedup = arbiter.build_ctx(motor.get_context(DEDUP),
                              ask=_ask_conta_chamadas({"n": 0}),
                              prosa={"acao": "cantar na taverna"})
res_1 = ctx_dedup.execute("sing", {"memoria_id": mem_dedup_a})
# args DIFERENTES da 1ª chamada (instrumento varia) — de propósito: o anti-loop
# GENÉRICO de `execute()` (chamada idêntica ignorada em silêncio) já barraria
# uma repetição BYTE A BYTE sozinho, e não mediria o dedup PRÓPRIO de `sing`
# (`ctx.sung_asked`, chaveado só por `memoria_id`) — que é o que este check
# quer provar.
res_2 = ctx_dedup.execute("sing", {"memoria_id": mem_dedup_a,
                                   "instrumento": "alaude-dedup-p58"})
check("6a. re-tentar o MESMO memoria_id no turno é BARRADO (mesmo com args "
     "diferentes — o dedup é por memoria_id, não pela chamada inteira)",
      res_2[0].get("ok") is not True
      and "já foi" in (res_2[0].get("erro") or ""), str(res_2))
res_3 = ctx_dedup.execute("sing", {"memoria_id": mem_dedup_b})
check("6b. cantar OUTRO episódio no MESMO turno PASSA",
      res_3[0].get("ok") is True, str(res_3))

manifest = arbiter.build_tools(motor.get_context(DEDUP))
face_sing = next((t for t in manifest if t["name"] == "sing"), None)
check("6c. a FACE de 'sing' lista as lembranças com resumo (medido, research M1)",
      face_sing is not None
      and mem_dedup_a in face_sing["description"]
      and mem_dedup_b in face_sing["description"], str(face_sing))
check("6d. a nota/DC/proficiência NÃO aparecem na face (Princípio IX)",
      face_sing is not None
      and "letra" not in face_sing["parameters"]["properties"]
      and "instrumento_nota" not in face_sing["parameters"]["properties"],
      str(face_sing))

print("\n--- US4: régua de instrumento — bônus só soma, nunca recusa --------------")

INSTR_ATOR = "instrumentista-p58"
d_instr = _mk_char(INSTR_ATOR, "Instrumentista")
(d_instr / "alaude-p58").mkdir()
(d_instr / "alaude-p58" / "item.md").write_text(
    "---\ntype: item\nid: alaude-p58\nname: Alaúde\norigin: editorial\n"
    "size: M\nweight_kg: 2.0\nstate:\n  slot: mao\n---\n"
    "Um alaúde velho, rachado e colado.\n", encoding="utf-8")
mem_instr = _mk_memoria(INSTR_ATOR, "Vi algo notável.", intensity="medium",
                        involved=[HEROI])
op_sem = {"memoria_id": mem_instr, "instrumento": None, "letra": "x / x / x / x",
         "instrumento_nota": 0}
op_com = {"memoria_id": mem_instr, "instrumento": "alaude-p58", "letra": "x / x / x / x",
         "instrumento_nota": 7}
motor._roll_d20 = lambda: 10
out_sem = motor.apply_resolution(INSTR_ATOR, res(musica_ops=[op_sem]))
d_sem = (out_sem.get("musica_ops_applied") or [{}])[0].get("desfecho")
out_com = motor.apply_resolution(INSTR_ATOR, res(musica_ops=[op_com]))
d_com = (out_com.get("musica_ops_applied") or [{}])[0].get("desfecho")
motor._roll_d20 = force
_ORDEM = {"fracasso": 0, "ruim": 1, "comum": 2, "otimo": 3}
check("US4a. com instrumento (nota 7 -> bônus +3) o desfecho é >= sem instrumento, "
     "no mesmo d20",
      _ORDEM.get(d_com, -1) >= _ORDEM.get(d_sem, -1), f"sem={d_sem} com={d_com}")
check("US4b. nota de instrumento 0 nunca vira recusa (bônus zero, segue igual)",
      d_sem in _ORDEM, str(d_sem))

print("\n--- 9. dez canções iguais: renova, não infla; intensidade estável -------")

DEZ = "cantor-dez-p58"
_mk_char(DEZ, "Cantor de Dez Noites", cha=16)
OUV_DEZ = "ouvinte-dez-p58"
_mk_char(OUV_DEZ, "Ouvinte de Dez Noites")
mem_dez = _mk_memoria(DEZ, "Vi um segredo revelado na praça.", intensity="large",
                      involved=[HEROI])
op_dez = {"memoria_id": mem_dez, "instrumento": None,
         "letra": "Na praça, sob o sol quente / um segredo veio à tona "
                  "/ ninguém mais o esquece / Na praça, sob o sol quente",
         "instrumento_nota": 0}
motor._roll_d20 = lambda: 20      # a MESMA noite perfeita, dez vezes
for _ in range(10):
    motor.apply_resolution(DEZ, res(musica_ops=[op_dez]))
motor._roll_d20 = force

reconto_dez = [m for m in _mems(OUV_DEZ) if m.get("evento") == "hearsay_reconto"]
wit_dez = [m for m in _mems(OUV_DEZ) if m.get("evento") == "witness_musica"]
mem_dez_ator = [m for m in _mems(DEZ) if m.get("evento") == "sing_otimo"]
check("9a. dez canções -> UM reconto por ouvinte (renovado, não 10 arquivos)",
      len(reconto_dez) == 1, str(len(reconto_dez)))
check("9b. dez canções -> UMA witness_musica por ouvinte (renovada)",
      len(wit_dez) == 1, str(len(wit_dez)))
check("9c. dez canções -> UMA memória no cantor (renovada, não 10 arquivos)",
      len(mem_dez_ator) == 1, str(len(mem_dez_ator)))
check("9d. `vezes` do reconto cresceu com as reprises",
      reconto_dez and int(reconto_dez[0].get("vezes") or 1) == 10,
      str(reconto_dez[0].get("vezes") if reconto_dez else None))
check("9e. intensidade do reconto igual à da PRIMEIRA noite (nunca sobe)",
      reconto_dez and reconto_dez[0].get("intensity") == "large",
      str(reconto_dez))

print("\n" + "=" * 70)
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("Fase 58 (Cantar o feito, spec 058) OK.")
