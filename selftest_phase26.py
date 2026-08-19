"""Auto-teste da Fase 26 — steal: roubar (spec 023, US2).

Rolagem forçada (motor._roll_d20). Cobre:
  - LIMPO: o item passa ao ladrão, o DONO NÃO ganha memória (não soube)
  - FLAGRADO-mas-levou: item passa + memória NEGATIVA `large` no dono (afeto−)
  - FLAGRADO-e-vazio: item NÃO passa + memória negativa no dono
  - o flagrante dispara o PORTÃO DE TRAUMA: persuade_give do ladrão sobre o dono é
    recusado (tão grave quanto uma agressão)
  - item que não é do alvo → recusa
  - segredo: exposição/DC/dado não descem ao client (a nota não vira valor visível)
  - spec 051: a proficiência em "crime" soma DIRETO na rolagem — dois ladrões idênticos,
    MESMA tirada, desfechos diferentes; extremos deterministas intocados

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


def _planta_memoria_crime(cid, intensity="giant"):
    """Planta uma memória de prática de furto (spec 029/051) sem passar por um furto
    de verdade — molde de `_planta_memoria_acougue` (selftest_phase52)."""
    folder = motor.find_character_folder(cid)
    motor.memoria._write_memory(folder, "uma temporada inteira batendo carteiras",
                                intensity=intensity, domain="crime", involved=[cid])


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

# =========================================================================== #
# 8) spec 051 — a proficiência em "crime" soma DIRETO na rolagem do furto
# =========================================================================== #

NOVATO = "novato-crime-teste"
EXPERIENTE = "gatuno-experiente-teste"
_mk_char(NOVATO, dex=10)      # DEX 10 -> mod 0
_mk_char(EXPERIENTE, dex=10)  # idêntico; a ÚNICA diferença é a prática
_planta_memoria_crime(EXPERIENTE, "giant")  # peso 8 -> fator ~3.33

# SC-002: ator virgem em `crime` -> bônus zero (nunca erro, nunca regressão)
nivel_novato = motor.memoria.proficiencies_for(NOVATO).get("crime", -1)
check("spec 051: ator SEM nenhuma memória domain='crime' -> nivel_crime = 0.0 "
      "(bônus zero, nunca erro)", nivel_novato == 0.0, str(nivel_novato))
nivel_exp = motor.memoria.proficiencies_for(EXPERIENTE).get("crime", 0.0)
check("spec 051: o furtador de prática acumula nivel_crime > 0 pelo MESMO mecanismo "
      "dinâmico de cozinha/acougue (nunca um campo skills.*)", nivel_exp > 3.0,
      str(nivel_exp))

# SC-001: MESMO d20 (9), MESMA exposição 5 (DC 10). Novato: total 9 -> falhou por 1
# (<=5) -> flagrado_levou (o dono guarda o rancor). Experiente: 9 + 3.33 = 12.33 >= 10
# -> LIMPO (o dono nem soube). A MESMA tirada, desfechos diferentes, só pela prática.
_mk_item(TAVERNA / ELGA, "bug-novato")
_mk_item(TAVERNA / ELGA, "bug-exp")
force(9)
motor.apply_resolution(NOVATO, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-novato", "exposicao": 5}]})
motor.apply_resolution(EXPERIENTE, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-exp", "exposicao": 5}]})
check("spec 051: os dois levaram o item (o bônus muda o FLAGRANTE, não o butim aqui)",
      _tem(NOVATO, "bug-novato") and _tem(EXPERIENTE, "bug-exp"))
check("spec 051: o NOVATO foi flagrado com a mesma tirada (total 9 < DC 10)",
      _tem_memoria_furto(ELGA, NOVATO))
check("spec 051: o EXPERIENTE saiu LIMPO com a MESMA tirada — a prática cruzou a DC "
      "(9 + ~3.33 >= 10) e o dono não guardou nada",
      not _tem_memoria_furto(ELGA, EXPERIENTE),
      f"elga->experiente={motor.sentiment_toward(ELGA, EXPERIENTE)}")

# FR-003: os extremos deterministas NUNCA rolam — a proficiência não os alcança
_mk_item(TAVERNA / ELGA, "bug-exp-zero")
force(20)
out_imp = motor.apply_resolution(EXPERIENTE, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-exp-zero", "exposicao": 0}]})
check("spec 051: exposição 0 continua IMPOSSÍVEL mesmo para o mais proficiente, sem dado",
      _tem(ELGA, "bug-exp-zero") and not _tem(EXPERIENTE, "bug-exp-zero")
      and all(r.get("rolagem") is None for r in out_imp.get("rolls", [])
              if r.get("tipo") == "furto"),
      str(out_imp.get("rolls")))
_mk_item(TAVERNA / ELGA, "bug-exp-dez")
force(1)
out_dez = motor.apply_resolution(EXPERIENTE, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-exp-dez", "exposicao": 10}]})
check("spec 051: exposição 10 continua LIMPO sem dado (proficiência nunca entra)",
      _tem(EXPERIENTE, "bug-exp-dez")
      and all(r.get("rolagem") is None for r in out_dez.get("rolls", [])
              if r.get("tipo") == "furto"),
      str(out_dez.get("rolls")))

# FR-004/SC-004: nivel_crime é segredo do mundo — nunca desce ao client
_mk_item(TAVERNA / ELGA, "bug-segredo")
force(9)
out_seg = motor.apply_resolution(EXPERIENTE, {"steal_ops": [
    {"alvo": ELGA, "item": "bug-segredo", "exposicao": 5}]})
blob_seg = " ".join(server_app.inworld_effects(out_seg))
check("spec 051: nem a proficiência nem o total aparecem no que desce ao client",
      "crime" not in blob_seg.lower() and "profici" not in blob_seg.lower(),
      blob_seg)

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 26 (steal) OK.")
