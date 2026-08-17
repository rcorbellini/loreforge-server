"""Sondagem: o nudge faz o Árbitro CHAMAR ask_wares para iniciar comércio?

NÃO É TESTE DE REGRESSÃO. Depende do modelo real, imprime o que o Árbitro fez e
NUNCA falha.

Medido em jogo: pedir "o que o Obadiah vende" fazia o qwen3:8b chamar SÓ narrate,
sem ask_wares — o comércio não iniciava (wares vazio). Adicionou-se ao prompt a
regra "consulte antes de narrar". Esta sondagem mede se ele passa a chamar
ask_wares antes do narrate.

Uso:  python3 server/tests/exploracao/sondagem_ask_wares.py [repeticoes]
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-sonda-"))
shutil.copytree(RAIZ.parent / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(RAIZ))

import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import motor  # noqa: E402

ELGA = "elga-taverneira"       # quem pergunta (na taverna com o Obadiah)
OBADIAH = "obadiah-mascate"
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def rodar():
    chamadas: list[str] = []
    loop_base = server_app.build_loop_fn(server_app.CONFIG["arbiter"])

    def loop_espia(system, user, tools, execute, max_calls):
        def execute_espia(name, args):
            chamadas.append(name)
            return execute(name, args)
        return loop_base(system, user, tools, execute_espia, max_calls)

    ctx = motor.get_context(ELGA)
    intent = {
        "action": "Elga chama o mascate ao balcão para saber o que ele vende",
        "target": OBADIAH,
        "utterance": "Obadiah. O que traz na caixa que valha moeda e não só poeira?",
        "movement": None, "note": "quer ver a mercadoria do mascate",
    }
    r = arbiter.resolve_with_tools(intent, ctx, loop_espia)
    return {
        "chamou_ask_wares": "ask_wares" in chamadas,
        "wares_trouxe": bool(r.get("wares")),
        "chamadas": chamadas,
    }


print(f"\nSondagem ask_wares (iniciar comércio) — {REPS} repetições")
print(f"modelo: {server_app.CONFIG['arbiter'].get('model')}")
print("esperado: chamar ask_wares ANTES de narrate; wares volta preenchido\n")

acertos, trouxe = 0, 0
for i in range(REPS):
    try:
        out = rodar()
    except Exception as exc:  # noqa: BLE001
        print(f"  {i+1}: (erro: {type(exc).__name__}: {exc})", flush=True)
        continue
    print(f"  {i+1}: ask_wares={out['chamou_ask_wares']} wares_trouxe={out['wares_trouxe']} "
          f"chamadas={out['chamadas']}", flush=True)
    acertos += int(out["chamou_ask_wares"])
    trouxe += int(out["wares_trouxe"])

print(f"\n  chamou ask_wares: {acertos}/{REPS} | trouxe a mercadoria: {trouxe}/{REPS}")
print("""
Leitura:
  - ask_wares alto = o nudge pegou; o comércio inicia (o modelo consulta antes de narrar)
  - ask_wares baixo = teto do modelo; o nudge não bastou — um Árbitro mais forte resolve""")
shutil.rmtree(_tmp, ignore_errors=True)
