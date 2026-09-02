"""Fase 63 (spec 064) — A MEMÓRIA EM CAMADAS.

O que esta fase guarda, e por que cada bloco existe:

  A. A CONTENÇÃO `CONTEXTO ⊆ CONSULTA ⊆ AGREGADO`, verificada com DADO. É o contrato
     inteiro da spec numa linha, e antes dela o mundo era binário na prática: 9 dos 12
     consumidores perguntavam só "está viva?", e `recall` tinha exatamente o mesmo
     alcance que `get_context`.
  B. A ASSIMETRIA DA CURA: `esquecida` sai da consulta e do contexto, mas PESA no
     agregado. "A marca fica; a lembrança não" — e é o que torna o custo de `heal`
     mais duro, não mais brando.
  C. A RENOVAÇÃO POR EVOCAÇÃO, e a guarda que a torna segura: leitura interna do
     Motor NÃO renova. Sem esta, a expiração deixaria de existir.
  D. A POSSE GRADUADA, e o segredo que não pode descer (nenhum número de certeza).
  E. O `about` das testemunhas — o que faz a crença ter de que se alimentar.
"""
import os, shutil, sys, tempfile, time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test63-"))
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


CID = next(c["id"] for c in motor.list_characters())
FOLDER = motor.find_character_folder(CID)
AGORA = time.time()


def _mem(mid, estado, *, intensity="medium", evento="mutate", involved=None,
         about=None, kind="acontecimento", vencida_em=None):
    """Escreve uma memória num estado escolhido, direto — é fixture, não jogo."""
    fim = vencida_em if vencida_em is not None else int(AGORA) + 999999
    fm = {"type": "memory", "id": mid, "kind": kind,
          "involved": involved or [], "timestamp_start": int(AGORA) - 10,
          "timestamp_end": fim, "intensity": intensity, "state": estado,
          "summary": f"fixture {mid}", "evento": evento}
    if about:
        fm["about"] = about
    motor.write_doc(FOLDER / "memories" / f"{mid}.md", fm, f"corpo de {mid}")
    return fm


print("--- Bloco A: a contenção CONTEXTO ⊆ CONSULTA ⊆ AGREGADO ---------------")

viva = _mem("mem-p63-viva", "active")
venc = _mem("mem-p63-venc", "expired", evento="inform", vencida_em=int(AGORA) - 10)
esq = _mem("mem-p63-esq", "esquecida", vencida_em=int(AGORA) - 10)

for nome, fm in (("viva", viva), ("vencida", venc), ("esquecida", esq)):
    c = motor.alcance_contexto(fm, AGORA)
    q = motor.alcance_consulta(fm, AGORA)
    a = motor.alcance_agregado(fm, AGORA)
    check(f"A1 {nome}: contexto ⟹ consulta", (not c) or q)
    check(f"A2 {nome}: consulta ⟹ agregado", (not q) or a)

check("A3 a contenção é ESTRITA: existe memória na consulta que o contexto não vê",
      motor.alcance_consulta(venc, AGORA) and not motor.alcance_contexto(venc, AGORA),
      "sem isto, 'parar pra lembrar' não alcança nada além do que já está na cabeça")
check("A4 `esquecida` NÃO está na consulta",
      not motor.alcance_consulta(esq, AGORA),
      "é o que mantém o custo da cura definitivo")
check("A5 `esquecida` ESTÁ no agregado", motor.alcance_agregado(esq, AGORA))

print("\n--- Bloco B: a assimetria da cura — a marca fica, a lembrança não ------")

_mem("mem-p63-peso-esq", "esquecida", intensity="giant",
     involved=["alvo-p63"], vencida_em=int(AGORA) - 10)
peso_esq = motor.familiarity_with(CID, "alvo-p63")
check("B1 memória `esquecida` PESA no apego (era ZERO antes da spec 064)",
      peso_esq > 0, f"apego = {peso_esq}")
check("B2 e pesa MENOS que a vencida equivalente",
      peso_esq < mp._MEMORY_WEIGHT["giant"] * 0.25 + 1e-9,
      f"esquecida {peso_esq} vs vencida {mp._MEMORY_WEIGHT['giant'] * 0.25}")
check("B3 `esquecida` NUNCA revive, por nenhum caminho",
      not mp._renew_memory(FOLDER, memoria_ids={"mem-p63-esq"}, modo="evocacao"),
      "o `continue` de `esquecida` vem antes de qualquer checagem")

print("\n--- Bloco C: evocar renova; LER não ------------------------------------")

antes = motor.read_doc(FOLDER / "memories" / "mem-p63-venc.md")[0]["timestamp_end"]
mp._renew_memory(FOLDER, memoria_ids={"mem-p63-venc"}, modo="evocacao")
depois, _ = motor.read_doc(FOLDER / "memories" / "mem-p63-venc.md")
check("C1 evocar ESTENDE o prazo da vencida", depois["timestamp_end"] > antes,
      f"{antes} -> {depois['timestamp_end']}")
check("C2 e a revive (volta a ser alcançável pelo contexto)",
      motor.alcance_contexto(depois, time.time()))
check("C3 a extensão é FRACIONÁRIA, nunca reset pleno",
      depois["timestamp_end"] - max(antes, int(AGORA))
      <= mp._TTL_BY_INTENSITY["medium"] // 2 + 5,
      "metade do TTL-base da própria intensidade")

# A GUARDA QUE IMPORTA (A4 da spec): leitura interna do Motor não pode renovar.
_mem("mem-p63-naotoca", "expired", evento="inform", involved=["alvo-p63"],
     vencida_em=int(AGORA) - 10)
te_antes = motor.read_doc(FOLDER / "memories" / "mem-p63-naotoca.md")[0]["timestamp_end"]
for _ in range(5):
    motor.familiarity_with(CID, "alvo-p63")
    motor.sentiment_toward(CID, "alvo-p63")
    motor.remembered_about(CID, "alvo-p63")
    motor.recall(CID, {"sobre": "fixture"})
te_depois = motor.read_doc(FOLDER / "memories" / "mem-p63-naotoca.md")[0]["timestamp_end"]
check("C4 medir afeto/apego, ler o contexto e chamar `recall` NÃO renovam nada",
      te_antes == te_depois,
      f"{te_antes} -> {te_depois}. Se renovassem, a expiração deixaria de existir")

# C5 — DECISÃO DE JOGO, e ela está aqui para ser vista, não escondida.
#
# `_EVENTOS_SEM_RENOVACAO` = {mutate, lock, equip, travel}: os registros de ESTADO, que
# a spec 030 excluiu da renovação automática ("registro de estado não se renova"). A
# spec 064 MANTEVE a exclusão também para a evocação — evocar um registro de estado o
# ENCONTRA (ele está na consulta, é só `expired`), mas não o faz durar.
#
# O que isso significa em números, e é grande: `mutate` é 31% do acervo (834 de 2.692),
# e 828 deles são `status.action` — prosa de cena escrita pela Mente, não escrituração.
# Manter a exclusão foi a escolha CONSERVADORA (preserva a intenção da 030); o outro
# caminho — deixar a evocação renovar prosa de cena — é decisão do mantenedor, não minha.
_mem("mem-p63-estado", "expired", evento="mutate", vencida_em=int(AGORA) - 10)
te_estado = motor.read_doc(FOLDER / "memories" / "mem-p63-estado.md")[0]["timestamp_end"]
mp._renew_memory(FOLDER, memoria_ids={"mem-p63-estado"}, modo="evocacao")
check("C5 evocar ENCONTRA um registro de estado, mas não o faz durar (decisão da 030)",
      motor.read_doc(FOLDER / "memories" / "mem-p63-estado.md")[0]["timestamp_end"]
      == te_estado
      and motor.alcance_consulta(
          motor.read_doc(FOLDER / "memories" / "mem-p63-estado.md")[0], time.time()),
      "mutate/lock/equip/travel: alcançáveis pela consulta, não renováveis")

print("\n--- Bloco D: a posse graduada, e o número que não desce ----------------")

check("D1 `dono` e `dono_reconhecido` são DUAS funções (molde knows/recognizes_route)",
      callable(motor.dono) and callable(motor.dono_reconhecido))
_mem("mem-p63-posse", "expired", evento="transfer", involved=["item-p63"],
     about="alguem-p63", vencida_em=int(AGORA) - 10)
check("D2 posse VENCIDA: `dono` (certeza) não afirma",
      motor.dono("item-p63", CID) is None)
check("D3 posse VENCIDA: `dono_reconhecido` reconhece",
      motor.dono_reconhecido("item-p63", CID) == "alguem-p63",
      "é o 'acho que era do Torvin'")

import json as _json
bruto = _json.dumps(motor.recognition_of.__doc__ or "")
for proibido in ('"certeza"', '"probabilidade"', '"saldo"'):
    check(f"D4 nenhum número de sistema no vocabulário da posse ({proibido})",
          proibido not in bruto)

print("\n--- Bloco E: o `about` das testemunhas ---------------------------------")

src = (SERVER_DIR / "motor" / "memoria" / "primitivas.py").read_text(encoding="utf-8")
check("E1 `witness_transfer` carrega `about` (o destinatário)",
      '"evento": "witness_transfer", "about": destino' in src,
      "eram 61 memórias no mundo, NENHUMA com about")
check("E2 `witness_emprestimo` segue com o EMPRESTADOR (spec 036, intacto)",
      '"evento": "witness_emprestimo", "about": character_id' in src)
check("E3 `stolen` carrega `about` (a vítima)", "about=dono," in src)
check("E4 `witness_theft` cai na vítima quando a testemunha não tem reivindicação",
      'dono(fato["item_furtado"], wid) or fato.get("vitima")' in src)

print()
shutil.rmtree(_tmp, ignore_errors=True)
if falhas:
    print(f"{len(falhas)} FALHA(S): " + ", ".join(falhas))
    sys.exit(1)
print("todos os checks da Fase 63 (spec 064) passaram.")
