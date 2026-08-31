"""Auto-teste da Fase 60 — A cadeia que completa, e o pedido que emagrece (spec 060).

O QUE ESTA FASE CUIDA, e o que ela NÃO cuida.

O grosso desta spec é de CONECTOR (research R1: o mundo não muda o que envia; o
conector passa a decidir o que a Mente vê), e o que é de conector se testa com
`node --test` em `loreforge-connector/test/`. O que sobra para o SERVER é pouco,
e é o que esta fase guarda:

  · os enums que FICAM continuam na face — vocabulário fechado, lugares que ele
    sabe alcançar, ids de memória e os SUBCONJUNTOS CALCULADOS (`heal.alvo` só
    incapacitados, `butcher_alvo` só mortos, instrumentos só o que dá para
    empunhar). Esses não são lista de cena: são a única fonte daquele fato, e
    tirá-los perderia conhecimento, não peso (FR-015/FR-016);
  · a face nunca expõe capacidade com enum obrigatório VAZIO — a garantia de
    `arbiter.py` ("tool sem candidato válido devolve None e some") que sustenta
    o desenho de dois estados do conector (não existe "sem lista de candidato");
  · `motor._match_scene_ref` continua honrando a regra que o resolvedor do
    conector replica (research R7, conformidade cruzada): resolve só com
    candidato único, e devolve None em ambiguidade — nunca chuta.

Uso:  python3 selftest_phase60.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test60-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor      # noqa: E402
import arbiter    # noqa: E402
import face       # noqa: E402
import mcp_core   # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _personagens():
    out = []
    for c in motor.list_characters():
        cid = c["id"] if isinstance(c, dict) else c
        try:
            out.append((cid, motor.get_context(cid)))
        except Exception:
            pass
    return out


print("--- (face) a garantia que sustenta os dois estados do conector ---------")

# A face NUNCA expõe capacidade com enum obrigatório vazio. É isso que torna
# impossível o terceiro estado ("o conector não tem lista de candidato"): se não
# há candidato, a capacidade não está lá para ser chamada.
vazios = []
for cid, ctx in _personagens():
    for cap in face.build(ctx):
        esq = mcp_core.input_schema(cap)
        req = set(esq.get("required") or [])
        for p, v in (esq.get("properties") or {}).items():
            if isinstance(v, dict) and "enum" in v and not v["enum"] and p in req:
                vazios.append(f"{cid}/{cap['nome']}.{p}")
check("face nunca expõe enum OBRIGATÓRIO vazio (arbiter: tool sem candidato some)",
      not vazios, "; ".join(vazios[:5]))

print("\n--- (enum) o que FICA, e por que não é preguiça ------------------------")

# Os subconjuntos CALCULADOS são a única fonte daquele fato: o contexto não diz
# de um jeito utilizável quem está caído nem o que dá para empunhar. Se um deles
# sumir da declaração, esta fase acusa — porque a informação teria ido junto.
CALCULADOS = {
    "heal": "alvo",                 # só quem está incapacitado
    "butcher": "alvo",              # só quem está morto
    "write": "instrumento",         # só o que dá para empunhar
    "sing": "instrumento",          # idem (opcional, mas mesmo predicado)
}
faltando = []
for cid, ctx in _personagens():
    caps = {c["nome"]: c for c in face.build(ctx)}
    for tool, param in CALCULADOS.items():
        cap = caps.get(tool)
        if cap is None:
            continue                        # a cena não oferece: nada a conferir
        alvos = cap.get("alvos") or {}
        if param not in alvos:
            faltando.append(f"{cid}/{tool}.{param}")
check("os subconjuntos CALCULADOS continuam declarando os candidatos",
      not faltando, "; ".join(faltando[:5]))

print("\n--- (resolução) a regra que o conector replica -------------------------")

CAND = [("moeda-cobre-025", "Moeda de Cobre"),
        ("moeda-cobre-026", "Moeda de Cobre"),
        ("cantil-de-agua-fresca", "Cantil de Água Fresca"),
        ("obadiah-mascate", "Obadiah, o Mascate")]

check("id exato resolve nele mesmo",
      motor._match_scene_ref("cantil-de-agua-fresca", CAND) == "cantil-de-agua-fresca")
check("nome exato resolve no id",
      motor._match_scene_ref("Cantil de Água Fresca", CAND) == "cantil-de-agua-fresca")
check("nome sem acento resolve igual",
      motor._match_scene_ref("cantil de agua fresca", CAND) == "cantil-de-agua-fresca")
check("referência que não existe NÃO resolve (nunca chuta)",
      motor._match_scene_ref("destilador", CAND) is None)
check("ambiguidade NÃO resolve — é o piso da regra que o conector replica",
      motor._match_scene_ref("Moeda de Cobre", CAND) is None,
      str(motor._match_scene_ref("Moeda de Cobre", CAND)))
check("referência vazia não resolve",
      motor._match_scene_ref("", CAND) is None)

print("\n" + "=" * 70)
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("Fase 60 (A cadeia que completa, spec 060) OK.")
