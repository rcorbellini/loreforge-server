"""Auto-teste da Fase 44 — a DESCRIÇÃO da capacidade é player-facing (spec 043).

(Número de FASE ≠ número de SPEC.)

Herda a garantia que o `portal/selftest_portal.py` dava e que morreu com o portal:
o texto que descreve uma capacidade NÃO pode vazar mecânica. A diferença é o alvo —
antes se verificava uma cópia curada (`portal/rules/rules.json`), que podia divergir
do código; agora se verifica a FONTE ÚNICA, a `description` da própria `@tool_spec`,
que é exatamente o texto que desce à Mente.

Por que isto existe: a `description` nasceu Árbitro-facing, instruindo o modelo a
preencher a nota de uma régua ("'vantagem' é a nota 0-10... pela régua canônica do
prompt"). Duas delas chegavam a COLAR a régua inteira no manifesto. Com o juízo
dentro da tool (spec 043), ninguém preenche nota — nem a Mente, nem o Árbitro — e
essas frases viraram texto morto que vazava mecânica de graça. Foram reescritas; esta
fase impede que voltem pela mão de quem escrever a próxima capacidade.

Princípios V e IX: o que desce é linguagem de mundo. Sem número, sem régua, sem
atributo, sem nome de tool interna, sem termo de sistema.

Uso:  python3 server/selftest_phase44.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import types
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test44-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# O vocabulário que NUNCA pode aparecer no texto exposto. Cada entrada é um caso
# real que já esteve numa descrição deste projeto — não é lista defensiva teórica.
VAZAMENTOS = re.compile(
    r"\b0-10\b"              # a faixa da nota
    r"|\bnota\b"             # a nota em si
    r"|\brégua\b|\bregua\b"  # a régua que a produz
    r"|na aplicação"         # "resolvido na aplicação" — mecânica de turno
    r"|\bnarrate\b"          # nome de tool interna
    r"|\bDEX\b|\bCHA\b|\bWIS\b|\bSTR\b|\bCON\b|\bINT\b"   # atributos crus
    r"|segredo do mundo"     # a própria advertência de segredo
    r"|\bteste de\b"         # "teste de persuasão"
    r"|\bspec \d+"           # referência a spec
    r"|\bfrontmatter\b|\btimestamp\b|\bjson\b",           # termo de sistema
    re.I,
)

# Uma cena mínima para as descrições que dependem dela (callables).
CENA = types.SimpleNamespace(
    cand={"acusar_memorias": {"mem-1": {"sobre": "elga-taverneira",
                                        "resumo": "vi ela furtar uma moeda"}}},
    chars=["torvin-ferreiro"], routes=["portao-lateral"], place_id="taverna",
    mut_targets=[], active_intention_ids=[], actor_id="torvin-ferreiro",
    MEMORY_INTENSITIES=["medium"], INTENTION_STATUSES=["ativa"],
    REGUA_DISPOSICAO="", REGUA_CONFIDENCIA="",
)


def _texto(spec):
    """A descrição RESOLVIDA — a callable é chamada, porque é ela que desce."""
    d = spec.description
    return d if isinstance(d, str) else d(CENA)


def run() -> int:
    FAILS.clear()
    vistos, specs = set(), []
    for nome, spec in motor.registro.specs().items():
        if id(spec) in vistos:
            continue
        vistos.add(id(spec))
        specs.append((nome, spec))

    check("há capacidades declaradas", len(specs) > 0, f"{len(specs)}")

    # 1. NENHUMA descrição vaza mecânica.
    sujas = []
    for nome, spec in specs:
        try:
            texto = _texto(spec)
        except Exception as exc:
            sujas.append(f"{nome} (a descrição nem resolveu: {exc!r})")
            continue
        achados = sorted(set(m.group(0).lower() for m in VAZAMENTOS.finditer(texto)))
        if achados:
            sujas.append(f"{nome} ({', '.join(achados)})")
    check("nenhuma descrição de capacidade vaza mecânica (Princípios V/IX)",
          not sujas, "; ".join(sujas))

    # 2. Toda capacidade TEM descrição, e ela diz alguma coisa. Uma descrição vazia
    #    passaria no teste de vazamento e não serviria para nada — a Mente ficaria
    #    com um nome nu e voltaria a não saber o que pode tentar.
    curtas = [n for n, s in specs
              if len((_texto(s) or "").strip()) < 40]
    check("toda capacidade tem descrição com substância", not curtas,
          f"curtas demais: {', '.join(curtas)}")

    # 3. A DESCRIÇÃO não pode carregar a régua dentro dela. Duas descrições faziam
    #    isso (`ask_directions`/`ask_about` concatenavam `s.REGUA_*` no próprio
    #    texto), o que despejava a régua inteira no manifesto. A régua segue viva no
    #    prompt do Árbitro — é o caminho de compatibilidade, e ele ainda preenche
    #    nota até a Fase 4 mover o juízo para dentro da tool. O que não pode é ela
    #    voltar a viajar pela descrição.
    reguas = [nome for nome in dir(motor.registro) if nome.startswith("REGUA_")]
    import arbiter  # noqa: E402  (só para ler os textos de régua)
    trechos = [getattr(arbiter, n)[:80] for n in dir(arbiter)
               if n.startswith("REGUA_") and isinstance(getattr(arbiter, n), str)]
    com_regua = []
    for nome, spec in specs:
        texto = _texto(spec)
        if any(t and t in texto for t in trechos):
            com_regua.append(nome)
    check("nenhuma descrição carrega o texto de uma régua dentro de si",
          not com_regua, ", ".join(com_regua))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S) na Fase 44: {', '.join(FAILS)}")
        return 1
    print("todos os checks da Fase 44 passaram.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    finally:
        shutil.rmtree(_tmp, ignore_errors=True)
