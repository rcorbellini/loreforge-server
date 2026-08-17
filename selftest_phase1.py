"""Auto-teste da Fase 1 — loop server-side com Árbitro FAKE (sem Ollama).

Testa arbiter.normalize e motor.apply_resolution:
  - aplica mutações de status a personagens presentes
  - rejeita mutação de identidade (FR-016) e de alvo ausente
  - garante ao menos uma consequência ao ator (FR-014)
  - preserva o arquivo e mantém o schema válido após mutar (FR-036, Princípio VI)

Roda sobre uma CÓPIA temporária do mundo, para não tocar no mundo-semente.
Uso:  python3 server/selftest_phase1.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parent

# Copia o mundo para um tmp e aponta o Motor para lá ANTES de importar motor.
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")

sys.path.insert(0, str(SERVER_DIR))
import arbiter  # noqa: E402
import motor  # noqa: E402
import validator  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def status_of(char_id):
    folder = motor.find_character_folder(char_id)
    fm, _ = motor.read_doc(folder / "character.md")
    return fm.get("status", {})


try:
    # --- normalize tolera cercas ```json e texto ao redor ------------------ #
    fenced = "```json\n{\"narrative_hint\": \"x\", \"mutations\": []}\n```"
    norm = arbiter.normalize(fenced)
    check("normalize: parseia com cercas", norm["narrative_hint"] == "x")
    check("normalize: mutations vazias -> lista", norm["mutations"] == [])

    # --- 1) mutação de status em personagem presente (elga) ---------------- #
    resolution = {
        "narrative_hint": "Torvin resmunga um cumprimento seco para Elga.",
        "mutations": [
            {"target": "elga-taverneira", "path": "status.mood",
             "value": "levemente surpresa", "reason": "cumprimento inesperado"},
        ],
        "memories": [],
    }
    outcome = motor.apply_resolution("torvin-ferreiro", resolution)
    check("apply: mutação de elga aplicada",
          any(m["target"] == "elga-taverneira" for m in outcome["applied"]))
    check("apply: elga.mood mudou",
          status_of("elga-taverneira").get("mood") == "levemente surpresa")
    # FR-014: ator não foi tocado pela resolução -> baseline action garantida
    check("apply(FR-014): ator ganhou consequência",
          any(m["target"] == "torvin-ferreiro" for m in outcome["applied"]))

    # --- 2) rejeita mutação de identidade (FR-016) ------------------------- #
    before_str = status_of("torvin-ferreiro")
    res_id = {"narrative_hint": "x", "mutations": [
        {"target": "torvin-ferreiro", "path": "attributes.STR", "value": 99}]}
    out2 = motor.apply_resolution("torvin-ferreiro", res_id)
    folder = motor.find_character_folder("torvin-ferreiro")
    fm_after, _ = motor.read_doc(folder / "character.md")
    check("apply(FR-016): STR não mudou", fm_after["attributes"]["STR"] == 16)
    check("apply(FR-016): mutação de identidade rejeitada",
          any(r["path"] == "attributes.STR" for r in out2["rejected"]))

    # --- 3) rejeita alvo ausente ------------------------------------------- #
    res_absent = {"narrative_hint": "x", "mutations": [
        {"target": "fantasma-inexistente", "path": "status.mood", "value": "z"}]}
    out3 = motor.apply_resolution("torvin-ferreiro", res_absent)
    check("apply: alvo ausente rejeitado",
          any(r["target"] == "fantasma-inexistente" for r in out3["rejected"]))

    # --- 4) arquivo preservado e schema ainda válido ----------------------- #
    check("apply: character.md ainda existe", (folder / "character.md").exists())
    check("apply: schema válido após mutar", validator.validate(fm_after) == [])

    # --- 5) resolve() end-to-end com model_fn FAKE ------------------------- #
    def fake_model(system, user):
        return json.dumps({
            "narrative_hint": "Elga ergue os olhos da panela por um instante.",
            "mutations": [{"target": "elga-taverneira", "path": "status.action",
                           "value": "olhando para Torvin"}],
            "memories": [],
        })

    # spec 020: resolve() (o resolver clássico) foi removido; normalize + apply é o
    # que ele fazia por dentro, e é o que segue valendo como parse+aplicação.
    resolved = arbiter.normalize(fake_model("", ""))
    out5 = motor.apply_resolution("torvin-ferreiro", resolved)
    check("normalize+apply: narrative_hint presente", bool(resolved["narrative_hint"]))
    check("normalize+apply: elga.action aplicada",
          status_of("elga-taverneira").get("action") == "olhando para Torvin")
    check("normalize+apply: alguma mutação aplicada (FR-014)", len(out5["applied"]) >= 1)

finally:
    shutil.rmtree(_tmp, ignore_errors=True)

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
    sys.exit(1)
print("todos os checks da Fase 1 passaram.")
