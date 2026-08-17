"""Auto-teste da Fase 21 — Reconhecer pela Vivência (spec 018).

Cobre:
  - a LEITURA e o GRAU: nítido (com episódios) / vago (só familiaridade) / ausente
  - o RECORTE de percepção: fora do alcance é recusado
  - o SIGILO DO NÚMERO: nenhum float sai em recognition_of/scene_recognitions/observe
  - a COR AMBIENTE: só quem tem vivência entra; sem história → []
  - a FRONTEIRA: a tool recognize devolve ao MODELO só o aviso; o pacote desce por
    `reconhecimentos`, e o contexto do Árbitro NÃO recebe reconhecimento

Usa o WORLD REAL (11 personagens) copiado para tmpdir. Memórias limpas por bloco.

Uso:  python3 server/selftest_phase21.py
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

# spec 023: estas fases precisam de NPCs que só existem no SAVE. Para NUNCA testar
# contra world/ (regra do projeto), semeamos versões LIMPAS no tmp — isoladas, sem
# tocar o fixture compartilhado (que outras fases assertam).
def _seed_char(_loc, _cid, _name, _cha=12):
    _d = _tmp / "world" / _loc / _cid
    _d.mkdir(parents=True, exist_ok=True)
    (_d / "character.md").write_text(
        "---\ntype: character\nid: %s\nname: %s\ncontrolled_by: player_local\n"
        "weight_kg: 72\nattributes:\n  STR: 11\n  DEX: 11\n  CON: 11\n  INT: 12\n"
        "  WIS: 12\n  CHA: %d\nskills:\n  geral: 2\nstatus:\n  hp: 60\n  hp_max: 60\n"
        "  hunger: saciado\n  fatigue: leve\n  action: parado\n  mood: neutro\n"
        "  conditions: []\norigin: editorial\n---\n\n%s (fixture de apoio, spec 023).\n"
        % (_cid, _name, _cha, _name), encoding="utf-8")
_seed_char("taverna-do-gancho", "obadiah-mascate", "Obadiah, o Mascate", 13)
_seed_char("forja-de-ferro", "bram-pescador", "Bram, o Pescador", 12)
_seed_char("forja-de-ferro", "draven-vigia", "Draven, o Vigia", 10)
_seed_char("forja-de-ferro", "renn-trovador", "Renn, o Trovador", 12)
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import motor  # noqa: E402
import selftest_helpers  # noqa: E402

FAILS = []

TOR = "torvin-ferreiro"
EL = "elga-taverneira"
OB = "obadiah-mascate"       # co-localizado na taverna
DRAVEN = "draven-vigia"      # na forja (fora do alcance da taverna)


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def pasta(cid):
    return motor.find_character_folder(cid)


def limpar(*cids):
    for cid in cids:
        d = pasta(cid) / "memories"
        if d.is_dir():
            for p in d.glob("*.md"):
                p.unlink()


def tem_numero(o):
    """Há algum float/int (não-bool) em qualquer profundidade? (sigilo do número)"""
    if isinstance(o, bool):
        return False
    if isinstance(o, (int, float)):
        return True
    if isinstance(o, dict):
        return any(tem_numero(v) for v in o.values())
    if isinstance(o, (list, tuple)):
        return any(tem_numero(v) for v in o)
    return False


print("\n--- A leitura e o grau ----------------------------------------------")

limpar(TOR, OB)
# NÍTIDO: Torvin guarda memória viva envolvendo Elga (presente na taverna)
motor._write_memory(pasta(TOR), "Elga me serviu ensopado quando eu não tinha um cobre.",
                    intensity="large", involved=[EL], valence={EL: motor.POSITIVA})
pac = motor.recognition_of(TOR, EL)
check("grau NÍTIDO quando há memória viva", pac["grau"] == "nitido", pac["grau"])
check("nítido traz os EPISÓDIOS", len(pac["memorias_vivas"]) >= 1)
check("nítido traz a PROSA do .md", "Taverna" in (pac["prosa"] or ""))
check("nítido traz FAMILIARIDADE em rótulo", isinstance(pac["familiaridade"], str))

# AUSENTE: Obadiah sem história com Torvin
pac2 = motor.recognition_of(OB, TOR)
check("grau AUSENTE sem história", pac2["grau"] == "ausente", pac2["grau"])
check("ausente não traz episódios", pac2["memorias_vivas"] == [])

# VAGO: familiaridade acima do piso, mas TODA vencida (remembered_about vazio)
limpar(OB)
mid = motor._write_memory(pasta(OB), "Torvin trocou comigo uma vez.", intensity="large",
                          involved=[TOR])
# vence à mão
for p in (pasta(OB) / "memories").glob("*.md"):
    fm, body = motor.read_doc(p)
    if TOR in motor.memory_involved(fm):
        fm["state"] = "expired"
        motor.write_doc(p, fm, body)
pac3 = motor.recognition_of(OB, TOR)
check("grau VAGO: familiaridade sem episódio vivo",
      pac3["grau"] == "vago" and pac3["memorias_vivas"] == [],
      f"grau={pac3['grau']} mem={len(pac3['memorias_vivas'])}")


print("\n--- O recorte de percepção (anti-metagaming) ------------------------")

try:
    motor.recognition_of(TOR, DRAVEN)  # Draven está na forja
    check("fora do alcance é recusado", False, "não recusou")
except motor.MotorError:
    check("fora do alcance é recusado", True)

# BUG: quem está CAÍDO não observa (percepção cessa ao cair)
_f = pasta(TOR) / "character.md"
_fm, _body = motor.read_doc(_f)
_fm.setdefault("status", {})["conditions"] = [motor.INCAPACITATED]
motor.write_doc(_f, _fm, _body)
try:
    motor.observe_entity(TOR, EL)
    check("observador CAÍDO é recusado (bug de percepção)", False, "observou caído")
except motor.MotorError:
    check("observador CAÍDO é recusado (bug de percepção)", True)
check("e caído não tinge a cena (scene_recognitions vazio)",
      motor.scene_recognitions(TOR) == [])
_fm["status"]["conditions"] = []
motor.write_doc(_f, _fm, _body)


print("\n--- O SIGILO DO NÚMERO (SC-005) -------------------------------------")

check("recognition_of NÃO contém número algum", not tem_numero(pac), str(pac))
check("scene_recognitions NÃO contém número algum",
      not tem_numero(motor.scene_recognitions(TOR)))
obs = motor.observe_entity(TOR, EL)
# observe ganha os campos de reconhecimento; nenhum número
check("observe_entity carried_item_ids o reconhecimento e nenhum número",
      "grau" in obs and "familiaridade" in obs and not tem_numero(obs),
      str(obs))


print("\n--- A cor ambiente (SC-007) ----------------------------------------")

cena = motor.scene_recognitions(TOR)
check("scene_recognitions traz a entidade de vivência (Elga)",
      any(p["name"] and "Elga" in p["name"] for p in cena), str([p["name"] for p in cena]))
# sem história com ninguém: limpa Torvin e mede
limpar(TOR)
check("cena sem história alguma → sem material (sem ruído)",
      motor.scene_recognitions(TOR) == [], str(motor.scene_recognitions(TOR)))


print("\n--- A FRONTEIRA: o Árbitro dispara mas NÃO interpreta (SC-006) -------")

limpar(TOR)
motor._write_memory(pasta(TOR), "Elga me serviu ensopado quando eu não tinha um cobre.",
                    intensity="large", involved=[EL], valence={EL: motor.POSITIVA})
_visto_lista = []
_r = selftest_helpers.resolve_scripted(
    {"action": "observa Elga"}, motor.get_context(TOR),
    [("recognize", {"alvo": EL})], captured=_visto_lista)
_visto = {"r": _visto_lista[0]}
check("recognize devolve ao MODELO só o aviso (sem a matéria)",
      _visto["r"].get("ok") and "prosa" not in _visto["r"]
      and "memorias_vivas" not in _visto["r"], str(_visto["r"]))
check("o PACOTE desce por `reconhecimentos` (não ao raciocínio do Árbitro)",
      _r.get("reconhecimentos") and _r["reconhecimentos"][0].get("memorias_vivas"),
      str(_r.get("reconhecimentos")))
# o contexto do Árbitro NÃO carried_item_ids reconhecimento
ctx_arb = arbiter._context_for_prompt(motor.get_context(TOR))
check("o contexto do Árbitro NÃO ganha reconhecimento (a fronteira)",
      "reconhec" not in str(ctx_arb).lower()
      and "memorias_vivas" not in str(ctx_arb),
      "vazou reconhecimento ao contexto do Árbitro")


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 21 (spec 018) passaram.")
