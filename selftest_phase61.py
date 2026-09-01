"""Auto-teste da Fase 61 — A intenção na mão do jogador (spec 061).

ZERO LLM, e isto é o requisito, não a conveniência: a feature inteira existe para
o dono escrever o compromisso do personagem dele SEM passar por Árbitro, Mente ou
juízo. Um dos testes prova isso da forma mais direta possível — instala um `ask`
que EXPLODE se for chamado, e roda as três operações em cima dele.

O que esta fase guarda:

  1. as três operações fazem o que dizem, pelas primitivas que já existiam;
  2. NADA SE APAGA — abandonar marca `status`, o arquivo fica (Princípio IV);
  3. a intenção abandonada some do que desce à Mente;
  4. o que já acabou não se reescreve;
  5. o texto tem piso e teto, e o teto é de RECURSO (ela entra no prompt de todo
     turno), não de mérito;
  6. a INDISTINGUIBILIDADE: o `.md` escrito pelo jogador tem os MESMOS campos do
     escrito por `set_intention`. É o veredito da provocação virando teste — se um
     campo de proveniência aparecer um dia, este teste cai;
  7. NENHUMA MEMÓRIA nasce de uma edição (FR-014);
  8. ZERO LLM.

A AUTORIZAÇÃO e a TRAVA DE TURNO vivem em `app.py` (camada HTTP) e são exercidas
pelo quickstart à mão — aqui se testa o que é do Motor e do contrato.

Uso:  python3 selftest_phase61.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test61-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor      # noqa: E402

FAILS = []
LUGAR = "mirante-do-corvo"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str, nome: str) -> Path:
    d = motor.WORLD_DIR / LUGAR / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {nome}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n"
        f"  CHA: 10\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nAlguém com planos.\n", encoding="utf-8")
    return d


def _mems(cid: str) -> int:
    return len(list(motor._iter_memories(cid)))


DONO = _mk_char("dono-p61", "Dono")

print("--- (as três operações) ------------------------------------------------")

iid = motor.create_intention(DONO, "Vou buscar os cravos de ferro na forja.")
ativas = motor.get_active_intentions(DONO)
check("criar: a intenção nasce ATIVA e desce ao contexto",
      any(i["id"] == iid and i["status"] == "ativa" for i in ativas), str(ativas))

ok = motor.update_intention(DONO, iid, "Vou desistir dos cravos e cuidar da forja.")
depois = motor.get_active_intentions(DONO)
check("alterar: o texto muda", ok and any("desistir" in (i.get("content") or "")
                                          for i in depois), str(depois))
check("alterar: o ID NÃO muda — é o que distingue corrigir de recriar",
      any(i["id"] == iid for i in depois), str([i["id"] for i in depois]))

check("abandonar: a operação aceita", motor.close_intention(DONO, iid,
                                                            status="abandonada"))
check("abandonar: some do que desce à Mente",
      not any(i["id"] == iid for i in motor.get_active_intentions(DONO)),
      str(motor.get_active_intentions(DONO)))

print("\n--- (Princípio IV) nada se apaga ---------------------------------------")

arq = DONO / "intentions" / f"{iid}.md"
check("o arquivo CONTINUA no disco depois de abandonado", arq.exists())
fm, corpo = motor.read_doc(arq)
check("e carrega `status: abandonada`", fm.get("status") == "abandonada",
      str(fm.get("status")))
check("com o texto preservado — abandonar não apaga o que foi escrito",
      "desistir" in corpo, corpo[:60])

print("\n--- (o que acabou não se reescreve) ------------------------------------")

antes = arq.read_text(encoding="utf-8")
check("alterar uma intenção ABANDONADA é recusado",
      motor.update_intention(DONO, iid, "tentando ressuscitar") is False)
check("e o arquivo fica INTACTO — recusa não toca em disco",
      arq.read_text(encoding="utf-8") == antes)
check("abandonar de novo é recusado (já não está aberta)",
      motor.close_intention(DONO, iid, status="abandonada") is False)
check("id inexistente é recusado sem explodir",
      motor.update_intention(DONO, "int-que-nao-existe", "x") is False)

print("\n--- (indistinguibilidade) o veredito da provocação, como teste ----------")

# A spec decidiu, por escrito, que a edição do JOGADOR não ganha marca de
# proveniência: se é "a mesma escrita por outra mão", carimbar origem contradiz a
# justificativa da feature. Este teste é o que impede o campo de aparecer um dia
# sem ninguém notar.
do_jogador = motor.create_intention(DONO, "Compromisso escrito pelo dono.")
OUTRO = _mk_char("outro-p61", "Outro")
pela_mente = motor.create_intention(OUTRO, "Compromisso escrito pela Mente.")
fm_j, _ = motor.read_doc(DONO / "intentions" / f"{do_jogador}.md")
fm_m, _ = motor.read_doc(OUTRO / "intentions" / f"{pela_mente}.md")
check("os dois `.md` têm exatamente os MESMOS campos",
      set(fm_j) == set(fm_m), f"jogador={sorted(fm_j)} mente={sorted(fm_m)}")
check("e nenhum deles diz QUEM escreveu",
      not any(k in fm_j for k in ("origem", "editado_por", "autor", "escrito_por")),
      str(sorted(fm_j)))

print("\n--- (FR-014) nenhuma memória nasce de uma edição -----------------------")

antes_mem = _mems("dono-p61")
n2 = motor.create_intention(DONO, "Mais um plano.")
motor.update_intention(DONO, n2, "Plano corrigido.")
motor.close_intention(DONO, n2, status="abandonada")
check("criar + alterar + abandonar não criam memória nenhuma",
      _mems("dono-p61") == antes_mem,
      f"antes={antes_mem} depois={_mems('dono-p61')}")

print("\n--- (FR-004) ZERO LLM --------------------------------------------------")

# A prova mais direta que cabe num teste: se qualquer caminho pedir juízo, isto
# explode. O quickstart refaz o mesmo à mão, com o Ollama desligado.
class _AskProibido:
    def __call__(self, *a, **k):
        raise AssertionError("alguém pediu juízo a um caminho que não pode ter LLM")


_guardado = getattr(motor, "ask", None)
motor.ask = _AskProibido()
try:
    n3 = motor.create_intention(DONO, "Sem modelo nenhum no caminho.")
    motor.update_intention(DONO, n3, "Ainda sem modelo.")
    motor.close_intention(DONO, n3, status="abandonada")
    sem_llm = True
except AssertionError as e:
    sem_llm = False
    print("   ", e)
finally:
    if _guardado is not None:
        motor.ask = _guardado
check("as três operações rodam sem tocar em LLM", sem_llm)

print("\n--- (contrato do texto) ------------------------------------------------")

# O piso e o teto vivem na camada HTTP (`app.py`), porque são contrato de porta e
# não regra de mundo — uma primitiva que recusasse texto grande seria regra de
# jogo escondida numa peça de infraestrutura. Aqui se guarda que o NÚMERO existe
# e é o que a spec declarou.
import app  # noqa: E402
check("o teto do texto está declarado e é o da spec (2.000)",
      getattr(app.Handler, "LIMITE_TEXTO_INTENCAO", None) == 2000,
      str(getattr(app.Handler, "LIMITE_TEXTO_INTENCAO", None)))
for metodo in ("_autorizar_intencao", "_turno_em_voo", "_texto_de_intencao",
               "_handle_intencao_post"):
    check(f"a guarda `{metodo}` existe", hasattr(app.Handler, metodo))

print("\n" + "=" * 70)
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("Fase 61 (A intenção na mão do jogador, spec 061) OK.")
