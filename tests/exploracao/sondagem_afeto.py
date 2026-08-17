"""Sondagem: o saldo de afeto pré-computado conserta a nota do agressor? (spec 016)

NÃO É TESTE DE REGRESSÃO. Depende do modelo real, imprime e NUNCA falha.

A spec 015 mediu o Árbitro dando nota 7 (desconhecido cordial) à mulher que o
personagem espancou: ele LEU a agressão e não soube SOMÁ-la. A spec 016 entrega o
saldo pronto (`saldo_afeto`) na resposta do `ask_directions`. Duas perguntas:

  1. Com o saldo negativo entregue de bandeja, a nota de disposição CAI?
  2. O Árbitro ainda LÊ `lembra_de_voce`, ou passa a decidir só pelo rótulo
     (o saldo virar muleta)?

Uso:  python3 server/tests/exploracao/sondagem_afeto.py [repeticoes]
"""

from __future__ import annotations

import os
import re as _re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-sonda-"))
shutil.copytree(RAIZ.parent / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
_log = _tmp / "devlog.log"
os.environ["LOREFORGE_LOG"] = "1"
os.environ["LOREFORGE_LOG_FILE"] = str(_log)
sys.path.insert(0, str(RAIZ))

import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import motor  # noqa: E402

ATOR = "torvin-ferreiro"
INFORMANTE = "elga-taverneira"
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def pasta(cid):
    return motor.find_character_folder(cid)


def limpar(cid):
    d = pasta(cid) / "memories"
    if d.is_dir():
        for p in d.glob("*.md"):
            p.unlink()


def preparar():
    limpar(INFORMANTE)
    limpar(ATOR)
    for rota in motor.all_route_ids():
        motor._remember_route(pasta(INFORMANTE), rota, motor.name_of(rota))
    # a agressão, agora COM valência (o mundo a derivaria; aqui montamos à mão
    # para a sondagem, no formato que _record_events produz)
    motor._write_memory(
        pasta(INFORMANTE),
        "O punho do ferreiro pegou-me de lado, no meio do meu próprio salão, e o "
        "chão veio ao encontro do meu rosto.",
        intensity="large", involved=[ATOR], valence={ATOR: motor.NEGATIVA},
        summary="Torvin me espancou na minha taverna.")


def rodar():
    marca = _log.stat().st_size if _log.exists() else 0
    ctx = motor.get_context(ATOR)
    intent = {"action": "pergunta a Elga por onde se chega ao cais",
              "target": INFORMANTE, "utterance": "Por onde se vai ao cais?",
              "movement": None, "note": "quer saber o caminho"}
    loop_fn = server_app.build_loop_fn(server_app.CONFIG["arbiter"])
    r = arbiter.resolve_with_tools(intent, ctx, loop_fn)
    trecho = ""
    if _log.exists():
        with _log.open(encoding="utf-8") as fh:
            fh.seek(marca)
            trecho = fh.read()
    ops = r.get("learn_ops") or []
    notas = [o.get("disposicao") for o in ops if o.get("fonte")]
    # o saldo que o mundo entregou neste turno
    saldo = motor.afeto_rotulo(motor.sentiment_toward(INFORMANTE, ATOR))
    return {
        "perguntou": "ask_directions" in trecho,
        "notas": notas,
        "saldo_entregue": saldo,
        "recusou": any(x.get("regra") == "recusou_informar"
                       for x in (r.get("rejected") or [])),
    }


print(f"\nSondagem do afeto pré-computado — {REPS} repetições")
print(f"modelo: {server_app.CONFIG['arbiter'].get('model')}")
print("caso: Torvin (que espancou Elga) pergunta o caminho a Elga")
print("esperado: com o saldo negativo entregue, a nota deve cair para 0-2\n")

notas_todas = []
for i in range(REPS):
    preparar()
    try:
        out = rodar()
    except Exception as exc:                          # noqa: BLE001
        print(f"  {i+1}: (erro: {type(exc).__name__}: {exc})", flush=True)
        continue
    notas_todas += [n for n in out["notas"] if n is not None]
    print(f"  {i+1}: perguntou={out['perguntou']} "
          f"notas={out['notas']} recusou={out['recusou']} "
          f"| saldo entregue ao Árbitro: '{out['saldo_entregue']}'", flush=True)

if notas_todas:
    print(f"\n  notas: {sorted(notas_todas)}  "
          f"(média {sum(notas_todas)/len(notas_todas):.1f})")
    print(f"  distribuição: {dict(Counter(notas_todas))}")
else:
    print("\n  nenhuma nota — o Árbitro não chegou a chamar learn_routes (ver 015)")

print("""
Leitura:
  - notas 0-2 = o saldo pré-computado consertou a nota 7 do agressor (spec 015)
  - notas altas ainda = nem o saldo pronto move este 8B; é caso de modelo maior
  - sem notas = a chamada learn_routes segue irregular (achado da 015, ortogonal)""")
shutil.rmtree(_tmp, ignore_errors=True)
