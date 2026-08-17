"""Auto-teste da Fase 26 — steal: roubar (spec 023, US2).

Rolagem forçada (motor._roll_d20). Cobre:
  - LIMPO: o item passa ao ladrão, o DONO NÃO ganha memória (não soube)
  - FLAGRADO-mas-levou: item passa + memória NEGATIVA `large` no dono (afeto−)
  - FLAGRADO-e-vazio: item NÃO passa + memória negativa no dono
  - o flagrante dispara o PORTÃO DE TRAUMA: persuade_give do ladrão sobre o dono é
    recusado (tão grave quanto uma agressão)
  - item que não é do alvo → recusa
  - segredo: exposição/DC/dado não descem ao client (a nota não vira valor visível)

Uso:  python3 server/selftest_phase26.py
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
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402

FAILS = []
TAVERNA = _tmp / "world" / "taverna-do-gancho"
ELGA = "elga-taverneira"
LADRAO = "ladrao-teste"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_item(dono_folder, item_id):
    d = dono_folder / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {item_id}\nname: Bugiganga\nvalue: 1\nsize: P\n"
        f"weight_kg: 0.2\norigin: editorial\n---\nUma bugiganga qualquer.\n", encoding="utf-8")


def _mk_char(cid, dex=14):
    d = TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: Ladrão de Teste\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: {dex}\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 12\n"
        f"skills:\n  furto: 3\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: leve\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm gatuno de teste.\n", encoding="utf-8")


def force(v):
    motor._roll_d20 = lambda: v


def _tem(cid, item):
    f = motor.find_character_folder(cid)
    return f is not None and motor._find_item_under(f, item) is not None


def _tem_memoria_furto(dono, ladrao):
    """O dono guarda memória de furto (stolen, large, negativa) do ladrão?"""
    return motor.has_trauma_from(dono, ladrao)


_mk_char(LADRAO, dex=10)  # DEX 10 → mod 0

# 1) LIMPO — exposição 5 (DC 10), d20=20 → total 20 ≥ 10
_mk_item(TAVERNA / ELGA, "bug-a")
force(20)
motor.apply_resolution(LADRAO, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-a", "exposicao": 5}]})
check("LIMPO: o item passou ao ladrão", _tem(LADRAO, "bug-a") and not _tem(ELGA, "bug-a"))
check("LIMPO: o DONO NÃO ganhou memória (não soube) — portão NÃO dispara",
      not _tem_memoria_furto(ELGA, LADRAO))

# 2) FLAGRADO-mas-levou — DC 10, d20=10 → total 10... ajusta: quero falhar por ≤5.
#    total 9 (d20=9, mod 0): dc−total = 1 ≤ 5 → flagrado_levou
_mk_item(TAVERNA / ELGA, "bug-b")
force(9)
motor.apply_resolution(LADRAO, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-b", "exposicao": 5}]})
check("FLAGRADO-levou: o item passou ao ladrão", _tem(LADRAO, "bug-b"))
check("FLAGRADO-levou: o dono ganhou memória NEGATIVA (afeto−)",
      motor.sentiment_toward(ELGA, LADRAO) < 0,
      f"elga->ladrao={motor.sentiment_toward(ELGA, LADRAO)}")
check("FLAGRADO-levou: dispara o portão de trauma (large)",
      _tem_memoria_furto(ELGA, LADRAO))

# 3) portão de TRAUMA: depois do flagrante, persuade_give do ladrão sobre Elga é recusado
_mk_item(TAVERNA / ELGA, "bug-t")
force(20)  # dado ótimo, mas o trauma força a disposição a 0
motor.apply_resolution(LADRAO, {"persuade_give_ops": [
    {"alvo": ELGA, "item": "bug-t", "para": LADRAO, "disposicao": 8}]})
check("portão de trauma: Elga NÃO cede a quem a flagrou roubando",
      not _tem(LADRAO, "bug-t") and _tem(ELGA, "bug-t"))

# 4) FLAGRADO-e-vazio — outro ladrão (sem trauma prévio no dono a atrapalhar a leitura)
L2 = "gatuno-teste"
_mk_char(L2, dex=10)
_mk_item(TAVERNA / ELGA, "bug-c")
force(1)  # total 0, dc−total = 10 > 5 → flagrado_vazio
motor.apply_resolution(L2, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-c", "exposicao": 5}]})
check("FLAGRADO-vazio: o item NÃO passou (ficou com o dono)",
      _tem(ELGA, "bug-c") and not _tem(L2, "bug-c"))
check("FLAGRADO-vazio: mesmo sem levar, o dono guarda o flagrante (trauma)",
      _tem_memoria_furto(ELGA, L2))

# 5) item que não é do alvo → recusa, sem efeito
_mk_item(TAVERNA / LADRAO, "bug-do-ladrao")  # item do próprio ladrão
force(20)
out = motor.apply_resolution(L2, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-do-ladrao", "exposicao": 5}]})
rej = out.get("rejected") or []
check("item que não é do alvo: recusa estruturada, sem efeito",
      _tem(LADRAO, "bug-do-ladrao") and any("de" in r for r in rej))

# 6) segredo: a exposição/DC não descem no que iria ao client (inworld_effects)
import app as server_app  # noqa: E402
_mk_char("furtivo-teste", dex=10)
_mk_item(TAVERNA / ELGA, "bug-s")
force(20)
o2 = motor.apply_resolution("furtivo-teste", {"steal_ops": [
    {"alvo": ELGA, "item": "bug-s", "exposicao": 7}]})
aconteceu = server_app.inworld_effects(o2)
blob = " ".join(aconteceu)
check("segredo: nem a exposição nem a DC aparecem no que desce ao client",
      "7" not in blob and "exposic" not in blob.lower() and "dc" not in blob.lower(),
      blob)

# 7) VIRADA (skill loreforge-arbitrated-action, itens 6 e 8): exposição BAIXA
#    (parecia impossível) + dado alto → furto LIMPO contra as probabilidades.
def _tem_mem_contendo(cid, trecho):
    md = motor.find_character_folder(cid) / "memories"
    for p in md.glob("*.md"):
        _fm, body = motor.read_doc(p)
        if trecho.lower() in body.lower():
            return True
    return False


_mk_char("azarado-teste", dex=10)
_mk_item(TAVERNA / ELGA, "bug-v")
force(14)  # exposição 3 (DC 14), total 14 = passou (não natural-20) → LIMPO; exp≤4 → VIRADA
outv = motor.apply_resolution("azarado-teste", {"steal_ops": [
    {"alvo": ELGA, "item": "bug-v", "exposicao": 3}]})
viradas = server_app.fate_twists(outv.get("rolls", []))
check("item 6: a virada do furto sobe no canal `viradas` (não silenciosa)",
      any(v.get("o_que") for v in viradas), str(viradas))
check("item 6: a virada é do bloco FURTO (resultado 'limpo'), não da força física",
      any(v.get("resultado") == "limpo" for v in viradas), str(viradas))
check("item 8: a virada deixa memória MAIS VIVA no ladrão (theft_twist)",
      _tem_mem_contendo("azarado-teste", "ninguém viu"))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 26 (steal) OK.")
