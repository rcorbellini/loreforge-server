"""Sondagem: a régua da disposição responde à relação? (spec 015, Phase 6).

NÃO É TESTE DE REGRESSÃO. Depende do modelo real e é intermitente por natureza:
imprime o que o Árbitro fez e NUNCA falha. Misturar isto à suíte a tornaria não
confiável — a fase 15 já custou caro nessa lição.

Duas perguntas, e as duas nasceram de riscos escritos no plano:

  1. **O modelo pergunta antes de aprender?** A guarda o corrige no mesmo turno,
     mas corrigir gasta chamada — interessa saber se ele acerta de primeira.
  2. **A régua ancorada alto vira régua INÚTIL?** Se ele der 7 para todo mundo,
     inclusive para quem o personagem espancou, o portão não existe. Este é o
     modo de falha esperado de uma régua ancorada no alto: colar no alto.

O caso da pancada é o que motivou a spec inteira. Se a nota não cair aqui, o que
precisa de conserto é a REDAÇÃO da régua, não o código.

Uso:  python3 server/tests/exploracao/sondagem_disposicao.py [repeticoes]
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

ATOR = "torvin-ferreiro"        # quem pergunta
INFORMANTE = "elga-taverneira"  # quem sabe a cidade — mesma taverna
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def pasta(cid):
    return motor.find_character_folder(cid)


def limpar(cid):
    d = pasta(cid) / "memories"
    if d.is_dir():
        for p in d.glob("*.md"):
            p.unlink()


def preparar(*, com_pancada: bool):
    """A Elga conhece a cidade. A diferença entre os dois casos é UMA memória."""
    limpar(INFORMANTE)
    limpar(ATOR)
    for rota in motor.all_route_ids():
        motor._remember_route(pasta(INFORMANTE), rota, motor.name_of(rota))
    if com_pancada:
        motor._write_memory(
            pasta(INFORMANTE),
            "O punho do ferreiro pegou-me de lado, no meio do meu próprio salão, "
            "e o chão veio ao encontro do meu rosto. Ninguém o segurou, e ele "
            "não disse uma palavra depois.",
            intensity="large", involved=[ATOR],
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
    chamadas = _re.findall(r'"tool": "([a-z_]+)"', trecho)

    perguntou = "ask_directions" in chamadas
    ops = r.get("learn_ops") or []
    notas = [o.get("disposicao") for o in ops if o.get("fonte")]
    return {
        "perguntou": perguntou,
        "aprendeu": bool(ops),
        "notas": notas,
        "atitudes": [o.get("atitude") for o in ops if o.get("fonte")],
        # a guarda que manda perguntar primeiro deixa rastro no devlog
        "foi_corrigido": "pergunte primeiro" in trecho,
    }


print(f"\nSondagem da disposição a informar — {REPS} repetições por caso")
print(f"modelo: {server_app.CONFIG['arbiter'].get('model')}\n")

for rotulo, com_pancada, esperado in (
    ("ESTRANHA CORDIAL (sem história nenhuma)", False,
     "nota ALTA (6-9): informação de rota é trivial, o normal é atender"),
    ("A MESMA, MAS ELE A ESPANCOU", True,
     "nota 0-1: quem apanhou não indica caminho nenhum"),
):
    print(f"┌ {rotulo}", flush=True)
    print(f"│ esperado: {esperado}", flush=True)
    perguntas, aprendizados, correcoes = 0, 0, 0
    todas_notas, amostra_atitude = [], None
    for i in range(REPS):
        preparar(com_pancada=com_pancada)
        try:
            out = rodar()
        except Exception as exc:                      # noqa: BLE001
            print(f"│   {i+1}: (erro: {type(exc).__name__}: {exc})", flush=True)
            continue
        # imprime JÁ, e não só no fim do caso: um turno do Árbitro leva minutos
        # num modelo local, e a primeira execução desta sondagem foi morta pelo
        # timeout com TODO o trabalho ainda no buffer.
        print(f"│   {i+1}: perguntou={out['perguntou']} "
              f"aprendeu={out['aprendeu']} notas={out['notas']} "
              f"corrigido={out['foi_corrigido']}", flush=True)
        perguntas += int(out["perguntou"])
        aprendizados += int(out["aprendeu"])
        correcoes += int(out["foi_corrigido"])
        todas_notas += [n for n in out["notas"] if n is not None]
        if out["atitudes"] and amostra_atitude is None:
            amostra_atitude = out["atitudes"][0]
    print(f"│   perguntou antes:  {perguntas}/{REPS}")
    print(f"│   tentou aprender:  {aprendizados}/{REPS}")
    print(f"│   foi corrigido pela guarda: {correcoes}/{REPS}")
    if todas_notas:
        print(f"│   notas: {sorted(todas_notas)}  "
              f"(média {sum(todas_notas)/len(todas_notas):.1f})")
        print(f"│   distribuição: {dict(Counter(todas_notas))}")
    else:
        print("│   notas: nenhuma — ele não chegou a chamar learn_routes")
    if amostra_atitude:
        print(f"│   atitude: “{amostra_atitude}”")
    print("└")

print("""
Leitura:
  - notas altas no primeiro caso e 0-1 no segundo = a régua está viva
  - notas altas nos DOIS = ela colou no alto; conserte a REDAÇÃO, não o código
  - "foi corrigido" alto = ele tenta aprender sem perguntar; a guarda faz o
    trabalho, mas a instrução da tool pode ser mais explícita""")
shutil.rmtree(_tmp, ignore_errors=True)
