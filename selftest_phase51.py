"""Auto-teste da Fase 51 — Fome e sede aumentam com o tempo real (spec 049,
US1+US2+US3+US4).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution` para
`eat`/`drink`, já cobertos pelas fases 48/49) e a LEITURA de `get_context`
(`motor.get_context`, que chama `hunger_label`/`thirst_label` por baixo).
Como o mecanismo depende de tempo REAL decorrido, os cenários manipulam
`status.hunger_ts`/`status.thirst_ts` diretamente no frontmatter em vez de
esperar horas de verdade — equivalente a "avançar o relógio". Cobre:

  - US1: comer grava `hunger_ts`/`hunger_note`; `get_context` deriva
    `fome` do tempo real decorrido contra os limiares da nota daquele ato
    (`"sem fome"` -> `"com fome"` -> `"faminto"`)
  - US2: mesmo mecanismo para `sede`, limiares próprios mais curtos — à
    mesma distância de tempo real e mesma nota, sede aperta antes de fome
  - US3: régua mais farta (nota alta) segura mais tempo real que uma
    régua baixa, mesmo `*_ts`
  - US4: personagem sem `*_ts` (nunca comeu/bebeu, ou ficção autorada à
    mão com texto livre) não sofre decadência nenhuma — comportamento
    idêntico ao pré-feature

Uso:  python3 selftest_phase51.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test51-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str, name: str, con: int = 10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: {con}\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_item(parent_folder: Path, item_id: str, name: str, descricao: str):
    d = parent_folder / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {item_id}\nname: {name}\nsize: P\nweight_kg: 0.3\n"
        f"origin: editorial\n---\n{descricao}\n", encoding="utf-8")
    return d


def eat_op(item, comestibilidade=5, saciedade=5, toxicidade=0, consumo=5, nova_descricao="resto"):
    return {"item": item, "comestibilidade": comestibilidade, "saciedade": saciedade,
            "toxicidade": toxicidade, "consumo": consumo, "nova_descricao": nova_descricao}


def drink_op(alvo, bebibilidade=5, hidratacao=5, embriaguez=0, toxicidade=0,
            consumo=5, nova_descricao="resto"):
    return {"alvo": alvo, "bebibilidade": bebibilidade, "hidratacao": hidratacao,
            "embriaguez": embriaguez, "toxicidade": toxicidade, "consumo": consumo,
            "nova_descricao": nova_descricao}


def status_de(cid: str) -> dict:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return dict(fm.get("status") or {})


def fome_de(cid: str) -> str:
    return motor.get_context(cid)["self"]["necessidade"]["fome"]


def sede_de(cid: str) -> str:
    return motor.get_context(cid)["self"]["necessidade"]["sede"]


def set_status_field(cid: str, campo: str, valor) -> None:
    """Simula 'avançar o relógio': escreve *_ts/*_note direto no frontmatter,
    fora do fluxo de eat/drink, exatamente como um teste de tempo decorrido
    precisa fazer sem esperar horas de verdade."""
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status[campo] = valor
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


HORA = 3600.0

# =========================================================================== #
# US1 — a fome volta depois de tempo real suficiente. Nota 5 (refeição
# comum): limiar "com fome" = 3+5*1.5 = 10.5h; limiar "faminto" = 10+5*4 = 30h.
# =========================================================================== #

_mk_char("faminto-p51", "Faminto")
FAM = "faminto-p51"
fam_folder = motor.find_character_folder(FAM)
_mk_item(fam_folder, "prato-p51", "Prato Comum", "Um prato comum de comida quente.")
motor.apply_resolution(FAM, {"eat_ops": [eat_op("prato-p51", saciedade=5)]})

check("US1: logo após comer -> 'sem fome'", fome_de(FAM) == "sem fome", fome_de(FAM))
check("US1: eat grava status.hunger_ts/hunger_note",
      isinstance(status_de(FAM).get("hunger_ts"), (int, float))
      and status_de(FAM).get("hunger_note") == 5, str(status_de(FAM)))

set_status_field(FAM, "hunger_ts", time.time() - 11 * HORA)
check("US1: 11h decorridas (> 10.5h) -> 'com fome'", fome_de(FAM) == "com fome", fome_de(FAM))

set_status_field(FAM, "hunger_ts", time.time() - 35 * HORA)
check("US1: 35h decorridas (> 30h) -> 'faminto'", fome_de(FAM) == "faminto", fome_de(FAM))

# =========================================================================== #
# US2 — a sede volta mais rápido que a fome. Nota 5: limiar "com sede" =
# 2+5*1 = 7h; limiar "sedento" = 6+5*2 = 16h — ambos mais curtos que fome.
# =========================================================================== #

_mk_char("sedento-p51", "Sedento")
SED51 = "sedento-p51"
sed51_folder = motor.find_character_folder(SED51)
_mk_item(sed51_folder, "copo-p51", "Copo Comum", "Um copo comum de água.")
motor.apply_resolution(SED51, {"drink_ops": [drink_op("copo-p51", hidratacao=5)]})

check("US2: logo após beber -> 'sem sede'", sede_de(SED51) == "sem sede", sede_de(SED51))
check("US2: drink grava status.thirst_ts/thirst_note",
      isinstance(status_de(SED51).get("thirst_ts"), (int, float))
      and status_de(SED51).get("thirst_note") == 5, str(status_de(SED51)))

set_status_field(SED51, "thirst_ts", time.time() - 7.5 * HORA)
check("US2: 7h30 decorridas (> 7h) -> 'com sede'", sede_de(SED51) == "com sede", sede_de(SED51))

set_status_field(SED51, "thirst_ts", time.time() - 17 * HORA)
check("US2: 17h decorridas (> 16h) -> 'sedento'", sede_de(SED51) == "sedento", sede_de(SED51))

# comparativo: MESMA nota (5), MESMO ts, 20h decorridas -> sede já em estágio
# severo ("sedento", limiar 16h) enquanto fome ainda não ("com fome", só
# depois de 30h) — sede sempre aperta antes de fome (SC-002).
_mk_char("comparado-p51", "Comparado")
COMP = "comparado-p51"
comp_folder = motor.find_character_folder(COMP)
_mk_item(comp_folder, "prato-c-p51", "Prato", "Prato comum.")
_mk_item(comp_folder, "copo-c-p51", "Copo", "Copo comum.")
motor.apply_resolution(COMP, {"eat_ops": [eat_op("prato-c-p51", saciedade=5)]})
motor.apply_resolution(COMP, {"drink_ops": [drink_op("copo-c-p51", hidratacao=5)]})
ts_comum = time.time() - 20 * HORA
set_status_field(COMP, "hunger_ts", ts_comum)
set_status_field(COMP, "thirst_ts", ts_comum)
check("US2 (comparativo): mesma nota, mesmo tempo real -> sede já severa, fome ainda não",
      sede_de(COMP) == "sedento" and fome_de(COMP) == "com fome",
      f"fome={fome_de(COMP)} sede={sede_de(COMP)}")

# =========================================================================== #
# US3 — uma refeição farta segura mais tempo que uma mordida. Notas 2 e 10,
# MESMO tempo real decorrido (20h): nota 2 (limiar faminto=18h) já em crise;
# nota 10 (limiar faminto=50h, limiar com-fome=18h) só começando a sentir.
# =========================================================================== #

_mk_char("mordida-p51", "Mordida", )
MORD = "mordida-p51"
mord_folder = motor.find_character_folder(MORD)
_mk_item(mord_folder, "mordisco-p51", "Mordisco", "Um mordisco de pão.")
motor.apply_resolution(MORD, {"eat_ops": [eat_op("mordisco-p51", saciedade=2)]})
set_status_field(MORD, "hunger_ts", time.time() - 20 * HORA)

_mk_char("fartura-p51", "Fartura")
FART = "fartura-p51"
fart_folder = motor.find_character_folder(FART)
_mk_item(fart_folder, "banquete-p51", "Banquete", "Um banquete farto.")
motor.apply_resolution(FART, {"eat_ops": [eat_op("banquete-p51", saciedade=10)]})
set_status_field(FART, "hunger_ts", time.time() - 20 * HORA)

check("US3: mesmo tempo real, nota baixa (2) já em crise -> 'faminto'",
      fome_de(MORD) == "faminto", fome_de(MORD))
check("US3: mesmo tempo real, nota alta (10) ainda não em crise -> 'com fome'",
      fome_de(FART) == "com fome", fome_de(FART))

# =========================================================================== #
# US4 — ficção autorada à mão continua funcionando sem mudança: personagem
# SEM *_ts (nunca comeu/bebeu via tool) não sofre decadência nenhuma.
# =========================================================================== #

_mk_char("npc-p51", "Personagem de Mundo")
NPC = "npc-p51"
npc_folder = motor.find_character_folder(NPC)
set_status_field(NPC, "hunger", "faminta")
set_status_field(NPC, "thirst", "sedento")
check("US4: texto livre autorado sem *_ts -> lê o rótulo canônico de sempre",
      fome_de(NPC) == "faminto" and sede_de(NPC) == "sedento",
      f"fome={fome_de(NPC)} sede={sede_de(NPC)}")
check("US4: sem *_ts, status.hunger_ts/thirst_ts continuam ausentes (nada os cria de graça)",
      status_de(NPC).get("hunger_ts") is None and status_de(NPC).get("thirst_ts") is None,
      str(status_de(NPC)))

_mk_char("virgem-p51", "Nunca Comeu Nem Bebeu")
VIRG = "virgem-p51"
check("US4: personagem sem status.hunger/thirst nenhum -> 'sem fome'/'sem sede'",
      fome_de(VIRG) == "sem fome" and sede_de(VIRG) == "sem sede",
      f"fome={fome_de(VIRG)} sede={sede_de(VIRG)}")

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 51 (Fome e sede com o tempo, spec 049) OK.")
