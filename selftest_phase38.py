"""Auto-teste da Fase 38 — Fronteira Primitiva × Tool (spec 037, Princípio XII).

Teste de FRONTEIRA (não de mecânica): trava, por análise estática do código do
Motor, os dois invariantes que a spec 037 promete e que nenhum teste de fase pega:

  SC-001  Nenhum EXECUTOR de tool (`_apply_*_ops` / `_apply_item_transfers`) chama o
          executor de OUTRA tool — nem no mesmo módulo, nem qualificado por módulo.
          O reuso mora na PRIMITIVA (ex.: `transfer_item`), nunca tool→tool.
          O wrapper de registro (`_h_*`) chamando o PRÓPRIO core é o padrão legítimo
          e NÃO conta (só se inspeciona o corpo dos cores).

  SC-002  Nenhum `os.replace` de pasta fora de `server/motor/io.py` — mover pasta é a
          básica `io.move_entity`, num lugar só.

Uso:  python3 server/selftest_phase38.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

MOTOR = Path(__file__).resolve().parent / "motor"
FAILS: list[str] = []


def check(desc: str, ok: bool, detail: str = "") -> None:
    mark = "ok  " if ok else "FALHA"
    print(f"[{mark}] {desc}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(desc + (f" ({detail})" if detail else ""))


def _is_core(name: str) -> bool:
    """Executor de tool: `_apply_*_ops` ou o core de transferência `_apply_item_transfers`.
    Fica de fora o que é BÁSICA/helper e pode ser composto à vontade
    (`_set_field`, `_apply_mutations`, `_apply_movement`)."""
    return name.startswith("_apply_") and (
        name.endswith("_ops") or name == "_apply_item_transfers")


def _called_name(call: ast.Call):
    fn = call.func
    if isinstance(fn, ast.Attribute):
        return fn.attr, True   # qualificado (mod.attr)
    if isinstance(fn, ast.Name):
        return fn.id, False
    return None, False


files = sorted(MOTOR.glob("*.py"))
check("há módulos do Motor para inspecionar", len(files) > 5, f"{len(files)} arquivos")

for f in files:
    src = f.read_text(encoding="utf-8")

    # SC-002 — os.replace só em io.py
    if f.name != "io.py":
        check(f"SC-002: {f.name} sem os.replace de pasta (usar io.move_entity)",
              "os.replace(" not in src, "encontrado os.replace")

    tree = ast.parse(src, filename=f.name)

    # SC-001a — nenhum core chama outro core (mesmo módulo)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _is_core(node.name):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    name, _q = _called_name(sub)
                    if name and _is_core(name) and name != node.name:
                        check(f"SC-001: {f.name}:{node.name} NÃO chama outro executor",
                              False, f"chama {name} — tool→tool; reuse a primitiva")

    # SC-001b — nenhuma chamada QUALIFICADA a um core (ex.: itens._apply_item_transfers)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name, qualified = _called_name(node)
            if qualified and name and _is_core(name):
                check(f"SC-001: {f.name} sem chamada qualificada a executor de tool",
                      False, f"chama .{name}() — reuse a primitiva")

# resumo positivo (quando tudo passa, os checks acima nem imprimem falha)
check("SC-001: nenhum tool→tool no Motor (executores só compõem primitivas)", not FAILS)

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS))
    sys.exit(1)
print("Fase 38 (Fronteira Primitiva × Tool, spec 037, Princípio XII) OK.")
