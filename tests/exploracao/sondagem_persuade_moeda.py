"""Sondagem: oferecer uma moeda aumenta a chance de convencer alguém a ir?

NÃO É TESTE DE REGRESSÃO. Depende do modelo real, imprime o que o Árbitro fez e
NUNCA falha.

A régua da vontade (arbiter.REGUA_VONTADE) manda dimensionar SÓ pelo ALVO —
"nunca o interesse de quem persuade". A moeda é interesse de quem persuade, e nem
é transferida (persuadir não move item). Logo, pela régua, a nota NÃO deveria
subir. A pergunta é se o modelo OBEDECE: um modelo fraco pode ceder ao suborno e
inflar a vontade mesmo contra a instrução.

Compara a mesma cena com e sem "tome uma moeda pelo incômodo".

Uso:  python3 server/tests/exploracao/sondagem_persuade_moeda.py [repeticoes]
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

ATOR = "sarga-contrabandista"   # tem moedas de prata para oferecer
ALVO = "hulda-estivadora"       # de pé, na mesma praça
ROTA_DESTINO = "Taverna do Gancho"
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 4


def rodar(com_moeda: bool):
    ctx = motor.get_context(ATOR)
    if com_moeda:
        utter = (f"Hulda, preciso que vá até a {ROTA_DESTINO}. Tome esta moeda de "
                 f"prata pelo incômodo.")
        action = f"convence Hulda a ir até a taverna oferecendo uma moeda de prata"
    else:
        utter = f"Hulda, preciso que vá até a {ROTA_DESTINO}."
        action = f"convence Hulda a ir até a taverna"
    intent = {"action": action, "target": ALVO, "utterance": utter,
              "movement": None, "note": "quer que Hulda vá à taverna"}
    loop_fn = server_app.build_loop_fn(server_app.CONFIG["arbiter"])
    r = arbiter.resolve_with_tools(intent, ctx, loop_fn)
    ops = r.get("persuade_ops") or []
    vont = [o.get("vontade") for o in ops]
    # a moeda foi de fato movida? (não deveria — persuadir não paga)
    transfer = r.get("item_transfers") or []
    return {
        "chamou_persuade": bool(ops),
        "vontade": vont,
        "moeda_transferida": bool(transfer),
        "hint": (r.get("narrative_hint") or "")[:90],
    }


print(f"\nSondagem persuade + moeda — {REPS} repetições por caso")
print(f"modelo: {server_app.CONFIG['arbiter'].get('model')}")
print("régua: a vontade deve vir do ALVO, não da oferta; moeda não é transferida\n")

for rotulo, com_moeda in (("SEM oferta de moeda", False),
                          ("COM oferta de moeda", True)):
    print(f"┌ {rotulo}", flush=True)
    notas, chamou, transf = [], 0, 0
    for i in range(REPS):
        try:
            out = rodar(com_moeda)
        except Exception as exc:  # noqa: BLE001
            print(f"│   {i+1}: (erro: {type(exc).__name__}: {exc})", flush=True)
            continue
        print(f"│   {i+1}: persuade={out['chamou_persuade']} "
              f"vontade={out['vontade']} moeda_movida={out['moeda_transferida']}",
              flush=True)
        chamou += int(out["chamou_persuade"])
        transf += int(out["moeda_transferida"])
        notas += [n for n in out["vontade"] if n is not None]
    print(f"│   chamou persuade: {chamou}/{REPS} | moeda transferida: {transf}/{REPS}")
    if notas:
        print(f"│   vontades: {sorted(notas)}  (média {sum(notas)/len(notas):.1f})")
        print(f"│   distribuição: {dict(Counter(notas))}")
    print("└", flush=True)

print("""
Leitura:
  - vontade parecida nos DOIS casos = o Árbitro obedeceu a régua (a moeda não pesou)
  - vontade MAIOR com a moeda = o modelo cedeu ao suborno contra a instrução — a
    régua precisa de redação mais firme, OU o desenho deveria mesmo deixar a oferta
    pesar (aí é decisão do mantenedor: bribe vira mecânica, via trade/necessidade)
  - moeda transferida = BUG: persuadir não paga; se moveu, a oferta virou troca
    silenciosa""")
shutil.rmtree(_tmp, ignore_errors=True)
