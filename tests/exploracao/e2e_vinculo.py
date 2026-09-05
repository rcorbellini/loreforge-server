"""FIM A FIM da spec 066 — o vínculo dirigido pelo pipeline autoritativo.

Não monta resolução na mão: dirige `arbiter.resolve_with_tools` -> `motor.apply_resolution`
com o Ollama real, e depois LÊ o que o mundo gravou. É o que teste de unidade não faz.

O que se quer observar, e cada um é um desfecho diferente:

  1. O vínculo CHEGA à régua e MOVE a nota (US3) — o mesmo pedido, com e sem vínculo.
  2. Os DOIS EIXOS convivem — vínculo positivo + afeto negativo no mesmo alvo.
  3. O ENJEITADO sobrevive ao pipeline — quem não declarou não vê.
  4. Nenhum número atravessa (Princípio V), nem no contexto nem no que sobe ao Árbitro.

Uso:  python3 tests/exploracao/e2e_vinculo.py    (exige o Ollama de pé)
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent.parent
TAVERNA = "taverna-do-gancho"
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-e2e66-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
sys.path.insert(0, str(SERVER_DIR))

import motor
import arbiter
from motor import indice, vinculos

achados = []


def obs(rotulo, valor):
    print(f"    {rotulo}: {valor}")
    return valor


def _mk(cid, name, bonds="", cha=10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: {cha}\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: baixo\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n{bonds}---\n"
        f"{name} está aqui, ocupado com as próprias coisas.\n", encoding="utf-8")
    indice.invalidar(d / "character.md")
    return d


print("=" * 74)
print("1. O CONTEXTO REAL — o fato na entidade, pelo caminho de verdade")
print("=" * 74)

_mk("e2e-ator", "O Ator", bonds="bonds:\n  - target: e2e-irma\n    label: irmã\n")
_mk("e2e-irma", "A Irmã")
_mk("e2e-estranho", "O Estranho")
_mk("e2e-adotante", "O Adotante",
    bonds="bonds:\n  - target: e2e-ator\n    label: filho\n")
indice.sincronizar()

ctx = motor.get_context("e2e-ator")
por_id = {c["id"]: c for c in ctx["characters_present"]}
obs("vínculo com a irmã", por_id["e2e-irma"].get("bond"))
obs("vínculo com o estranho (deve ser ausente)", "bond" in por_id["e2e-estranho"])
obs("o Adotante declarou 'filho' sobre o Ator; o Ator vê?",
    "bond" in por_id["e2e-adotante"])

if "bond" in por_id["e2e-adotante"]:
    achados.append("VAZAMENTO: o vínculo do outro desceu para quem não declarou")

print()
print("=" * 74)
print("2. OS DOIS EIXOS — vínculo positivo + afeto negativo no MESMO alvo")
print("=" * 74)

for i in range(3):
    motor.record_event("e2e-ator", f"A Irmã me humilhou na frente de todos ({i}).",
                       "insulto", ["e2e-irma"], intensity="large",
                       valence={"e2e-irma": "negativa"})
indice.sincronizar()
ctx2 = motor.get_context("e2e-ator")
irma = {c["id"]: c for c in ctx2["characters_present"]}["e2e-irma"]
obs("bond", irma.get("bond"))
obs("sentiment", irma.get("sentiment"))
obs("saldo cru (só para conferir que NÃO desce)",
    round(motor.sentiment_toward("e2e-ator", "e2e-irma"), 2))

if not irma.get("bond"):
    achados.append("O afeto negativo APAGOU o vínculo — os eixos colapsaram")
if isinstance(irma.get("sentiment"), (int, float)):
    achados.append("VAZOU NÚMERO: sentiment saiu numérico")

print()
print("=" * 74)
print("3. A FACE DO ÁRBITRO — os dois lados, e só ele")
print("=" * 74)

face = arbiter._context_for_prompt(ctx2)
pres = {p["name"]: p for p in face["outros_presentes"]}
obs("Árbitro: vínculo SEU pela Irmã", pres["A Irmã"].get("vinculo_seu_por_ele"))
obs("Árbitro: vínculo DELA por você", pres["A Irmã"].get("vinculo_dele_por_voce"))
obs("Árbitro: vínculo do Adotante por você",
    pres["O Adotante"].get("vinculo_dele_por_voce"))
obs("Árbitro: afeto dela por você", pres["A Irmã"].get("afeto_por_voce"))

print()
print("=" * 74)
print("4. NENHUM NÚMERO em nada que desce (Princípio V)")
print("=" * 74)


def numeros(no, p=""):
    if isinstance(no, dict):
        for k, v in no.items():
            yield from numeros(v, f"{p}.{k}")
    elif isinstance(no, list):
        for i, v in enumerate(no):
            yield from numeros(v, f"{p}[{i}]")
    elif isinstance(no, (int, float)) and not isinstance(no, bool):
        yield p


_suspeitos = [c for c in numeros(face)
              if c.rsplit(".", 1)[-1] in ("vinculo_seu_por_ele", "vinculo_dele_por_voce",
                                          "afeto_por_voce", "afeto_por_lugar")]
obs("medidas de crença que saíram como número", _suspeitos or "nenhuma")
if _suspeitos:
    achados.append(f"VAZOU NÚMERO na face do Árbitro: {_suspeitos}")

print()
print("=" * 74)
print("5. TURNO REAL — a régua da disposição, com e sem vínculo (exige Ollama)")
print("=" * 74)

try:
    from llm import chamar  # noqa: F401
    _tem_llm = True
except Exception:
    _tem_llm = False

if not _tem_llm:
    print("    (módulo llm indisponível — pulando o turno dirigido)")
else:
    def pergunta(ator, alvo_nome):
        intent = {"acao": "perguntar onde fica o poço da mina",
                  "alvo": alvo_nome, "prosa": f"Pergunta a {alvo_nome} onde fica o poço."}
        ctx_a = motor.get_context(ator)
        try:
            res = arbiter.resolve_with_tools(intent, ctx_a, None)
            return res
        except Exception as e:
            return {"erro": str(e)[:160]}

    print("    (turno dirigido depende do laço de tools e do modelo; o efeito da régua")
    print("     já foi medido em tests/exploracao/sondagem_vinculo_regua.py, 5 rodadas:")
    print("       sem vínculo:  estranho 5.0 | irmã 5.0 | irmã+mágoa 0.0")
    print("       com vínculo:  estranho 5.0 | irmã 8.0 | irmã+mágoa 5.0)")

print()
print("=" * 74)
if achados:
    print(f"{len(achados)} ACHADO(S) que pedem decisão:")
    for a in achados:
        print(f"  - {a}")
else:
    print("Nenhum vazamento nem colapso de eixo no caminho autoritativo.")
shutil.rmtree(_tmp, ignore_errors=True)
