"""Auto-teste da Fase 36 (spec 035) — location aninhada dentro de location.

Cobre o bug encontrado ao planejar hierarquia de mundo (cidade > taverna > quarto):
`_scene_entities` usava `iterdir` (raso) para personagens/objects mas `rglob`
(recursivo) para itens — uma sub-location (quarto dentro da taverna, cidade
dentro de região) tinha os PERSONAGENS corretamente escondidos da cena de fora,
mas os ITENS deles vazavam para o escopo do lugar que a contém.

Roda sobre uma CÓPIA temporária do mundo. Uso:  python3 server/selftest_phase36.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")

sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def author(relpath: str, text: str) -> None:
    p = motor.WORLD_DIR / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


TAVERNA = motor.WORLD_DIR / "taverna-do-gancho"

# --- sub-location aninhada de verdade, dentro da pasta da taverna ---------- #
author(
    "taverna-do-gancho/quarto-oculto/location.md",
    "---\ntype: location\nid: quarto-oculto\nname: Quarto Oculto\nsize: P\n"
    "entry_point: null\norigin: editorial\n---\n\nUm quarto pequeno e trancado.\n",
)
author(
    "taverna-do-gancho/quarto-oculto/hospede-oculto/character.md",
    "---\ntype: character\nid: hospede-oculto\nname: Hóspede Oculto\n"
    "controlled_by: npc\nattributes: {STR: 10, DEX: 10, CON: 10, INT: 10, WIS: 10, CHA: 10}\n"
    "skills: {}\nstatus: {}\n---\n\nAlguém que não quer ser visto.\n",
)
author(
    "taverna-do-gancho/quarto-oculto/hospede-oculto/item-na-mao/item.md",
    "---\ntype: item\nid: item-na-mao\nname: Item na Mão\n---\n\nAlgo que ele segura.\n",
)
author(
    "taverna-do-gancho/quarto-oculto/item-oculto/item.md",
    "---\ntype: item\nid: item-oculto\nname: Item Oculto\n---\n\nUm pertence solto no quarto.\n",
)

# --- cena vista de FORA (a taverna, escopo de quem está no salão) ---------- #
chars_fora, objs_fora, items_fora = motor._scene_entities(TAVERNA)
check("personagem da sub-location não aparece na cena de fora (já valia antes)",
      "hospede-oculto" not in chars_fora, str(sorted(chars_fora)))
check("item da sub-location NÃO vaza para a cena de fora (o bug corrigido)",
      "item-oculto" not in items_fora, str(sorted(items_fora)))

ctx_elga = motor.get_context("elga-taverneira")
ctx_item_ids = {i["id"] for i in ctx_elga.get("items_present", [])}
check("get_context de quem está na taverna não lista o item do quarto",
      "item-oculto" not in ctx_item_ids, str(ctx_item_ids))

# --- cena vista de DENTRO (o quarto, escopo de quem está lá) --------------- #
QUARTO = TAVERNA / "quarto-oculto"
chars_dentro, _objs_dentro, items_dentro = motor._scene_entities(QUARTO)
check("personagem do quarto aparece na própria cena",
      "hospede-oculto" in chars_dentro, str(sorted(chars_dentro)))
check("item do quarto aparece na própria cena",
      "item-oculto" in items_dentro, str(sorted(items_dentro)))

ctx_hospede = motor.get_context("hospede-oculto")
check("localização do hóspede resolve para a sub-location (parent direto)",
      ctx_hospede["location"]["id"] == "quarto-oculto",
      str(ctx_hospede["location"]))
hospede_item_ids = {i["id"] for i in ctx_hospede.get("items_present", [])}
check("get_context de quem está no quarto vê o item solto do quarto",
      "item-oculto" in hospede_item_ids, str(hospede_item_ids))

# --- o mundo continua validando (nenhum schema novo, só estrutura) --------- #
check("World Validator não reprova o mundo com location aninhada",
      motor.validate_world() == [], str(motor.validate_world()))

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 36 (spec 035) passaram.")
