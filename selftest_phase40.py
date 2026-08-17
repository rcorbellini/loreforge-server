"""Auto-teste da Fase 40 — US2 do item 038: ativação de tools por-mundo (SC-005).

Prova, sem LLM real, que DOIS mundos com manifestos de ativação diferentes oferecem
CONJUNTOS de tools diferentes, sem tocar em nenhum arquivo de engine:
  - mundo A (`tools_desativadas: [attack]`): `attack` NÃO aparece na FACE e NÃO
    resolve (o _execute recusa mesmo se nomeada);
  - mundo B (sem manifesto): TODAS ativas — `attack` aparece;
  - mundo C (`tools_ativas: [take, narrate, bogus-xyz]`): oferece SÓ essas, e o id
    órfão `bogus-xyz` vira AVISO em world_warnings (ignorado, sem derrubar o boot).

Cada mundo é sondado num SUBPROCESSO (o `WORLD_DIR` fixa no import). Uso:
    python3 server/selftest_phase40.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
FIXTURE = SERVER_DIR / "tests" / "world"

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _make_world(manifest: str | None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="loreforge-us2-")) / "world"
    shutil.copytree(FIXTURE, d)
    if manifest is not None:
        (d / "world.md").write_text(manifest, encoding="utf-8")
    return d


_PROBE = r'''
import sys, json
sys.path.insert(0, %r)
import motor, arbiter, selftest_helpers
ACTOR = "torvin-ferreiro"
ctx = motor.get_context(ACTOR)
names = sorted(t["name"] for t in arbiter.build_tools(ctx))
capt = []
out = selftest_helpers.resolve_scripted(
    {"action": "ataca Elga", "target": "elga-taverneira"}, ctx,
    [("attack", {"alvo": "elga-taverneira", "vantagem": 5}),
     ("narrate", {"narrative_hint": "x"})],
    captured=capt)
attack_r = capt[0] if capt and isinstance(capt[0], dict) else {}
print(json.dumps({
    "names": names,
    "attack_active": motor.ativacao.is_active("attack"),
    "attack_erro": attack_r.get("erro", ""),
    "attack_resolveu": bool(out.get("attack_ops_applied")),
    "orfas": sorted(w["id"] for w in motor.world_warnings()
                    if w.get("kind") == "tool_ativacao_orfa"),
    "boot_ok": True,
}))
''' % (str(SERVER_DIR),)


def probe(world_dir: Path) -> dict:
    env = dict(os.environ, LOREFORGE_WORLD=str(world_dir), LOREFORGE_LOG="0")
    r = subprocess.run([sys.executable, "-c", _PROBE], env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {"boot_ok": False, "stderr": r.stderr[-800:]}
    return json.loads(r.stdout.strip().splitlines()[-1])


A = probe(_make_world("---\ntools_desativadas: [attack]\n---\nManifesto do mundo A.\n"))
B = probe(_make_world(None))
C = probe(_make_world("---\ntools_ativas: [take, narrate, bogus-xyz]\n---\nMundo C.\n"))

check("US2: os três mundos sobem sem derrubar", A.get("boot_ok") and B.get("boot_ok")
      and C.get("boot_ok"), str({"A": A.get("stderr"), "C": C.get("stderr")}))

# --- SC-005: conjuntos diferentes por manifesto -----------------------------------
check("US2: mundo B (sem manifesto) oferece `attack`", "attack" in B.get("names", []))
check("US2: mundo A (desativada) NÃO oferece `attack` na FACE",
      "attack" not in A.get("names", []))
check("US2: A e B oferecem conjuntos DIFERENTES de tools",
      set(A.get("names", [])) != set(B.get("names", [])))
check("US2: a diferença A×B é exatamente `attack`",
      set(B.get("names", [])) - set(A.get("names", [])) == {"attack"},
      str(set(B.get("names", [])) - set(A.get("names", []))))

# --- attack desativada NÃO resolve (nem nomeada por prosa) -------------------------
check("US2: em A, `attack` é recusada pelo despacho (não está ativa)",
      "não está ativa" in A.get("attack_erro", ""), A.get("attack_erro"))
check("US2: em A, nada de attack foi aplicado", not A.get("attack_resolveu"))
check("US2: em B, `attack` está ativa (is_active)", B.get("attack_active") is True)

# --- mundo C: tools_ativas restringe; id órfão vira aviso, não erro ----------------
check("US2: mundo C oferece SÓ o que `tools_ativas` lista (take/narrate)",
      set(C.get("names", [])) == {"take", "narrate"}, str(C.get("names")))
check("US2: id órfão `bogus-xyz` vira AVISO em world_warnings",
      "bogus-xyz" in C.get("orfas", []), str(C.get("orfas")))
check("US2: o id órfão foi IGNORADO (não virou tool, boot íntegro)",
      "bogus-xyz" not in C.get("names", []) and C.get("boot_ok"))

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S):", ", ".join(FAILS))
    sys.exit(1)
print("Fase 40 (US2 — ativação por mundo, spec 038) OK.")
