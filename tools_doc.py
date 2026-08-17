"""Gerador da referência de tools (spec 038, US3) → `docs/tools.generated.md`.

Deriva a referência das DECLARAÇÕES (`@tool_spec`), das recusas
(`motor._WHY_BY_REGRA`) e das réguas canônicas (`arbiter.REGUA_*`) — a versão que
NÃO pode divergir do código. Companion do `docs/tools.md` hand-written (a rationale
de desenho): o selftest valida a cobertura dos dois contra as declarações, e que
esta versão está EM SYNC (regenerar para atualizar).

Uso:  python3 server/tools_doc.py          # (re)gera docs/tools.generated.md
      python3 server/tools_doc.py --check  # falha se o arquivo divergir do código
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
os.environ.setdefault("LOREFORGE_WORLD", str(SERVER_DIR / "tests" / "world"))
os.environ.setdefault("LOREFORGE_LOG", "0")
sys.path.insert(0, str(SERVER_DIR))

import arbiter  # noqa: E402
import motor  # noqa: E402

DOC = SERVER_DIR.parent / "docs" / "tools.generated.md"


def _param_row(pname: str, spec) -> str:
    sch = spec.params.get(pname)
    if callable(sch):
        tipo = "enum (dinâmico)"
    else:
        tipo = (sch or {}).get("type", "?")
        if pname in spec.enum_sources:
            tipo = f"{tipo} · enum"
    req = "sim" if pname in spec.required else "não"
    src = spec.enum_sources.get(pname)
    fonte = "—" if src is None else (src if isinstance(src, str) else "(cena)")
    return f"| `{pname}` | {tipo} | {req} | {fonte} |"


def gerar() -> str:
    L: list[str] = []
    L.append("# Tools do Árbitro — referência GERADA")
    L.append("")
    L.append("> **NÃO EDITE À MÃO.** Gerada de `server/tools_doc.py` a partir das")
    L.append("> declarações `@tool_spec`, das recusas `motor._WHY_BY_REGRA` e das réguas")
    L.append("> `arbiter.REGUA_*`. Para atualizar: `python3 server/tools_doc.py`. O")
    L.append("> `selftest.py` falha se divergir do código (spec 038, US3). A rationale de")
    L.append("> desenho (o porquê de cada regra) vive no companion hand-written")
    L.append("> `docs/tools.md`.")
    L.append("")

    specs = motor.registro.specs()
    L.append(f"## Tools ({len(specs)})")
    L.append("")
    for name in sorted(specs):
        spec = specs[name]
        L.append(f"### `{name}`")
        L.append("")
        desc = spec.description
        L.append(desc if isinstance(desc, str) else "_(descrição depende da cena)_")
        L.append("")
        if spec.params:
            L.append("| param | tipo | obrigatório | fonte-de-enum |")
            L.append("|---|---|---|---|")
            for pname in spec.params:
                L.append(_param_row(pname, spec))
        else:
            L.append("_(sem parâmetros)_")
        L.append("")

    regras = motor._WHY_BY_REGRA
    L.append(f"## Regras de recusa — `_WHY_BY_REGRA` ({len(regras)})")
    L.append("")
    L.append("| regra | motivo (in-world, devolvido ao modelo) |")
    L.append("|---|---|")
    for regra in sorted(regras):
        why = " ".join(str(regras[regra]).split()).replace("|", r"\|")
        L.append(f"| `{regra}` | {why} |")
    L.append("")

    reguas = sorted(n for n in dir(arbiter) if n.startswith("REGUA_"))
    L.append(f"## Réguas canônicas — `arbiter.REGUA_*` ({len(reguas)})")
    L.append("")
    for rn in reguas:
        L.append(f"### `{rn}`")
        L.append("")
        L.append("```")
        L.append(str(getattr(arbiter, rn)).rstrip())
        L.append("```")
        L.append("")

    return "\n".join(L).rstrip() + "\n"


def main() -> int:
    conteudo = gerar()
    if "--check" in sys.argv:
        atual = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
        if atual != conteudo:
            print("DOC GERADA DESATUALIZADA — rode `python3 server/tools_doc.py`")
            return 1
        print("docs/tools.generated.md em sync com o código")
        return 0
    DOC.write_text(conteudo, encoding="utf-8")
    print(f"gerado: {DOC.relative_to(SERVER_DIR.parent)} ({len(conteudo.splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
