"""Auto-teste da Fase 25 — persuade_give: convencer a DAR um item (spec 023, US1).

Rolagem forçada (motor._roll_d20). Cobre:
  - sucesso: o item passa do DONO ao destinatário; o afeto de QUEM RECEBE pelo DONO
    fica POSITIVO (é o dono quem doou) — a si e a um TERCEIRO
  - determinismo: disposição 0 recusa sem dado; 10 cede sem dado; 1–9 rola uma vez
  - portão de trauma: quem sofreu violência de quem pede NÃO cede (disposição → 0)
  - falha: dado ruim → o item não se move

Uso:  python3 server/selftest_phase25.py
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
TOR, ELGA, BRAM = "torvin-ferreiro", "elga-taverneira", "bram-teste"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_item(dono_folder: Path, item_id: str):
    d = dono_folder / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {item_id}\nname: Naco de Teste\nvalue: 1\n"
        f"size: P\nweight_kg: 0.3\norigin: editorial\n---\nUm naco de carne assada.\n",
        encoding="utf-8")


def _mk_char(cid: str, cha: int = 10):
    d = TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: Sujeito de Teste\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: {cha}\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: leve\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm sujeito de teste.\n", encoding="utf-8")


def force(v):
    motor._roll_d20 = lambda: v


def _tem(char_id, item_id):
    folder = motor.find_character_folder(char_id)
    return folder is not None and motor._find_item_under(folder, item_id) is not None


# ---------------------------------------------------------------------------- #
# 1) sucesso a SI — afeto do ator pelo DONO fica positivo
_mk_item(TAVERNA / ELGA, "naco-a")
force(20)
out = motor.apply_resolution(TOR, {"persuade_give_ops": [
    {"alvo": ELGA, "item": "naco-a", "para": TOR, "disposicao": 5}]})
check("sucesso a si: o item passou do dono (Elga) ao ator (Torvin)",
      _tem(TOR, "naco-a") and not _tem(ELGA, "naco-a"))
check("sucesso a si: o afeto de Torvin por Elga (a DOADORA) ficou POSITIVO",
      motor.sentiment_toward(TOR, ELGA) > 0,
      f"sentiment={motor.sentiment_toward(TOR, ELGA)}")

# 2) sucesso a TERCEIRO — o afeto positivo é de quem RECEBEU pelo DONO, não do ator
_mk_char(BRAM)
_mk_item(TAVERNA / ELGA, "naco-b")
force(20)
motor.apply_resolution(TOR, {"persuade_give_ops": [
    {"alvo": ELGA, "item": "naco-b", "para": BRAM, "disposicao": 5}]})
check("sucesso a terceiro: o item foi para o TERCEIRO (Bram)", _tem(BRAM, "naco-b"))
check("sucesso a terceiro: o afeto positivo é de BRAM por Elga (a doadora)",
      motor.sentiment_toward(BRAM, ELGA) > 0,
      f"bram->elga={motor.sentiment_toward(BRAM, ELGA)}")

# 3) determinismo: disposição 0 recusa sem dado
_mk_item(TAVERNA / ELGA, "naco-c")
def _boom():
    raise AssertionError("não deveria rolar dado com disposição 0")
motor._roll_d20 = _boom
out0 = motor.apply_resolution(TOR, {"persuade_give_ops": [
    {"alvo": ELGA, "item": "naco-c", "para": TOR, "disposicao": 0}]})
check("disposição 0: recusa determinista, item não se move, sem dado",
      not _tem(TOR, "naco-c") and _tem(ELGA, "naco-c"))

# 4) disposição 10: cede sem dado
motor._roll_d20 = _boom
motor.apply_resolution(TOR, {"persuade_give_ops": [
    {"alvo": ELGA, "item": "naco-c", "para": TOR, "disposicao": 10}]})
check("disposição 10: cede sem dado (item passou ao ator)", _tem(TOR, "naco-c"))

# 5) portão de TRAUMA: quem sofreu violência do ator não cede (disposição forçada a 0)
_mk_item(TAVERNA / ELGA, "naco-d")
# grava uma agressão viva de Torvin contra Elga (large, negativa)
motor.record_event(ELGA, "Torvin me golpeou com fúria; caí.", "assaulted",
                   [ELGA, TOR], valence={TOR: motor.NEGATIVA})
# eleva a intensidade para large (o portão exige large/giant)
mem_dir = motor.find_character_folder(ELGA) / "memories"
for p in mem_dir.glob("*.md"):
    fm, body = motor.read_doc(p)
    if fm.get("type") == "memory" and "golpeou" in body:
        fm["intensity"] = "large"
        motor.write_doc(p, fm, body)
check("preparo: o portão vê o trauma (has_trauma_from(Elga, Torvin))",
      motor.has_trauma_from(ELGA, TOR))
force(20)  # dado ótimo, mas a disposição é forçada a 0 pelo portão
motor.apply_resolution(TOR, {"persuade_give_ops": [
    {"alvo": ELGA, "item": "naco-d", "para": TOR, "disposicao": 8}]})
check("portão de trauma: mesmo com dado ótimo, Elga NÃO cede a quem a golpeou",
      not _tem(TOR, "naco-d") and _tem(ELGA, "naco-d"))

# 6) falha por dado ruim (sem trauma): item fica
_mk_item(TAVERNA / ELGA, "naco-e")
_mk_char("cordato-teste", cha=10)
force(1)  # d20=1 + mod baixo vs DC de disposição 5 → falha
motor.apply_resolution("cordato-teste", {"persuade_give_ops": [
    {"alvo": ELGA, "item": "naco-e", "para": "cordato-teste", "disposicao": 5}]})
check("falha por dado ruim: o item não se move", _tem(ELGA, "naco-e")
      and not _tem("cordato-teste", "naco-e"))

# 7) VIRADA (skill loreforge-arbitrated-action, itens 6 e 8): disposição BAIXA
#    (tendência "não daria") + dado alto → cedeu contra o juízo. Deve (6) subir no
#    canal `viradas` como frase in-world e (8) deixar memória MAIS VIVA no doador.
import app as server_app  # noqa: E402


def _tem_mem_contendo(cid, trecho):
    md = motor.find_character_folder(cid) / "memories"
    for p in md.glob("*.md"):
        _fm, body = motor.read_doc(p)
        if trecho.lower() in body.lower():
            return True
    return False


_mk_char("suplicante-teste", cha=10)  # ator FRESCO: Elga não guarda trauma dele
_mk_item(TAVERNA / ELGA, "naco-v")
force(20)  # disposição 2 (tendência "não daria", DC 16) + dado 20 → cedeu = VIRADA
outv = motor.apply_resolution("suplicante-teste", {"persuade_give_ops": [
    {"alvo": ELGA, "item": "naco-v", "para": "suplicante-teste", "disposicao": 2}]})
viradas = server_app.fate_twists(outv.get("rolls", []))
check("item 6: a virada sobe no canal `viradas` como frase in-world (não silenciosa)",
      any(v.get("o_que") for v in viradas), str(viradas))
check("item 6: a frase é de CEDER, não de força física (tipo persuade_give)",
      any("abrir mão" in (v.get("o_que") or "") for v in viradas), str(viradas))
check("item 8: a virada deixa memória MAIS VIVA no doador (cedeu contra o juízo)",
      _tem_mem_contendo(ELGA, "não sei o que me deu"))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 25 (persuade_give) OK.")
