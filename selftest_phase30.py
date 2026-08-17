"""Auto-teste da Fase 30 — Acusar (spec 028).

Sem nenhum modelo/LLM — exercita o Motor direto (`motor.apply_resolution`),
molde das fases 27-29. Cobre:

  - `evento` persistido no retrofit (transfer, promise, witness) — o mesmo
    rótulo que já calibrava intensidade/valência agora vai pro arquivo
  - `acusar` com testemunha presente: as TRÊS memórias corretas, cada uma
    com o `evento` certo (accuse/accused/witness_accuse)
  - grounding: sem memória real sobre o alvo, a tool não aparece no
    manifest; `memoria_id` inválida/alheia/vencida é rejeitada, nada nasce
  - `acusar` nunca rola dado
  - o caminho VIVO do tool-calling: manifest expõe `acusar` com a descrição
    listando as evidências; outcome expõe `accuse_ops_applied`
  - US3: `attack` e `prometer` continuam funcionando normalmente depois de
    uma acusação, sem nenhum acoplamento vindo dela

Uso:  python3 server/selftest_phase30.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
import selftest_helpers  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"
TOR, ELGA = "torvin-ferreiro", "elga-taverneira"
BRAM = "bram-cliente"
MOEDA1, MOEDA2, MOEDA3 = "moeda-de-prata-1", "moeda-de-prata-2", "moeda-de-prata-3"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str, name: str):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 18\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: baixo\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")


_mk_char(BRAM, "Bram")


def ifolder(item_id) -> Path:
    return motor.find_entity(item_id)[0].parent


def dar(cid: str, item_id: str):
    folder = ifolder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    fm["state"] = {**(fm.get("state") or {}), "slot": motor.HAND_SLOT}
    motor.write_doc(folder / "item.md", fm, body)
    dest = motor.find_character_folder(cid) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def memories(cid: str) -> list[tuple[dict, str]]:
    d = motor.find_character_folder(cid) / "memories"
    if not d.exists():
        return []
    return [motor.read_doc(p) for p in sorted(d.glob("*.md"))]


def last_evento(cid: str) -> str | None:
    mems = memories(cid)
    return mems[-1][0].get("evento") if mems else None


def forbid_roll():
    def _boom():
        raise AssertionError("acusar não deveria rolar dado")
    motor._roll_d20 = _boom


def allow_roll():
    import random
    motor._roll_d20 = lambda: random.randint(1, 20)


# --------------------------------------------------------------------------- #
# 1) evento persistido no retrofit — transfer (give)
dar(TOR, MOEDA1)
motor.apply_resolution(TOR, {"item_transfers": [{"item": MOEDA1, "to": ELGA}]})
check("retrofit: transfer grava evento='transfer' no doador",
      last_evento(TOR) == "transfer")
check("retrofit: transfer grava evento='transfer' no receptor",
      last_evento(ELGA) == "transfer")

# 2) evento persistido no retrofit — promise (prometer, puramente verbal —
#    spec 036 tirou `item` de `prometer`)
motor.apply_resolution(TOR, {"promise_ops": [
    {"para": ELGA, "expectativa": "que ela devolva depois"}]})
check("retrofit: prometer grava evento='promise' em quem promete",
      any(fm.get("evento") == "promise" for fm, _ in memories(TOR)))
check("retrofit: prometer grava evento='promise' em quem recebe",
      any(fm.get("evento") == "promise" for fm, _ in memories(ELGA)))

# 3) evento persistido no retrofit — witness (furto FLAGRADO, com Bram por perto)
dar(ELGA, MOEDA3)
force_flag = motor._roll_d20
# d20=8 satisfaz os dois testes do mesmo turno: furto de Torvin (DEX -1) falha
# por pouco (8-1=7 < DC 10 => flagrado_levou) E a percepção de Bram (WIS 18,
# mod +4) passa (8+4=12 >= DC 2*exposicao=10) — os dois usam _roll_d20.
motor._roll_d20 = lambda: 8
motor.apply_resolution(TOR, {"steal_ops": [
    {"alvo": ELGA, "item": MOEDA3, "exposicao": 5}]})
motor._roll_d20 = force_flag
check("retrofit: leque de testemunha grava evento='witness_theft' em Bram",
      any(fm.get("evento") == "witness_theft" for fm, _ in memories(BRAM)))

# --------------------------------------------------------------------------- #
# 4) acusar COM testemunha — as três memórias, cada uma com o evento certo
n_tor0, n_elga0, n_bram0 = len(memories(TOR)), len(memories(ELGA)), len(memories(BRAM))
# grounding real e controlado: planta uma memória de Torvin sobre Elga
mid_evidencia = motor.memoria._write_memory(
    motor.find_character_folder(TOR),
    "Vi Elga esconder algo que não era dela.",
    involved=[ELGA])
forbid_roll()
out_ac = motor.apply_resolution(TOR, {"accuse_ops": [
    {"alvo": ELGA, "memoria_id": mid_evidencia}]})
allow_roll()
applied_ac = out_ac.get("accuse_ops_applied") or []
check("acusar: uma op aplicada", len(applied_ac) == 1)
# n_tor0 foi medido ANTES de plantar mid_evidencia — essa memória em si já
# soma 1; a acusação soma outro 1.
check("acusar: memória nova no acusador (Torvin)", len(memories(TOR)) == n_tor0 + 2)
check("acusar: memória nova na acusada (Elga)", len(memories(ELGA)) == n_elga0 + 1)
check("acusar: memória nova na testemunha (Bram)", len(memories(BRAM)) == n_bram0 + 1)
check("acusar: evento='accuse' no acusador", last_evento(TOR) == "accuse")
check("acusar: evento='accused' na acusada", last_evento(ELGA) == "accused")
check("acusar: evento='witness_accuse' na testemunha", last_evento(BRAM) == "witness_accuse")
_, corpo_elga = memories(ELGA)[-1]
check("acusar: conteúdo da acusada deriva da memória referenciada",
      "esconder" in corpo_elga.lower())

# 5) grounding — memoria_id inválida/alheia/vencida: nada nasce
n_tor1, n_elga1 = len(memories(TOR)), len(memories(ELGA))
out_bad = motor.apply_resolution(TOR, {"accuse_ops": [
    {"alvo": ELGA, "memoria_id": "mem-nao-existe"}]})
check("grounding: memoria_id inexistente é rejeitada", bool(out_bad.get("rejected")))
check("grounding: nada nasce em quem acusa", len(memories(TOR)) == n_tor1)
check("grounding: nada nasce na acusada", len(memories(ELGA)) == n_elga1)

# memória de OUTRA pessoa (Elga tem uma memória própria; Torvin não pode usá-la)
mid_da_elga = motor.memoria._write_memory(
    motor.find_character_folder(ELGA), "Vi Torvin martelar até tarde.",
    involved=[TOR])
out_alheia = motor.apply_resolution(TOR, {"accuse_ops": [
    {"alvo": ELGA, "memoria_id": mid_da_elga}]})
check("grounding: memoria_id de outra pasta é rejeitada", bool(out_alheia.get("rejected")))

# memória vencida (timestamp_end no passado)
mid_vencida = motor.memoria._write_memory(
    motor.find_character_folder(TOR), "Uma lembrança já esquecida.", involved=[ELGA])
vfolder = motor.find_character_folder(TOR) / "memories" / f"{mid_vencida}.md"
vfm, vbody = motor.read_doc(vfolder)
vfm["timestamp_end"] = int(time.time()) - 10
motor.write_doc(vfolder, vfm, vbody)
out_vencida = motor.apply_resolution(TOR, {"accuse_ops": [
    {"alvo": ELGA, "memoria_id": mid_vencida}]})
check("grounding: memoria_id vencida é rejeitada", bool(out_vencida.get("rejected")))

# 6) manifest — sem lastro nenhum, a tool não oferece o alvo / não aparece
_mk_char("estranho-p30", "Estranho")
ctx_estranho_alvo = motor.get_context(TOR)
tools_ctx = arbiter.build_tools(ctx_estranho_alvo)
tool_acusar = next((t for t in tools_ctx if t["name"] == "accuse"), None)
check("manifest: 'acusar' aparece (há lastro sobre Elga/Bram)", tool_acusar is not None)
if tool_acusar:
    check("manifest: 'estranho-p30' NÃO está no enum de alvo (sem memória real)",
          "estranho-p30" not in tool_acusar["parameters"]["properties"]["alvo"]["enum"])
    check("manifest: a descrição lista as evidências disponíveis",
          mid_evidencia in tool_acusar["description"]
          or any(mid_evidencia in v for v in
                 tool_acusar["parameters"]["properties"]["memoria_id"]["enum"]))

# --------------------------------------------------------------------------- #
# 7) o CAMINHO VIVO do tool-calling
mid_evidencia2 = motor.memoria._write_memory(
    motor.find_character_folder(TOR), "Vi Elga discutir alto com um cliente.",
    involved=[ELGA])
ctx_tor = motor.get_context(TOR)
intent_viva = {"action": "confronta Elga com o que sabe", "target": ELGA,
              "utterance": None, "movement": None, "note": ""}
out_viva = selftest_helpers.resolve_scripted(intent_viva, ctx_tor, [
    ("accuse", {"alvo": ELGA, "memoria_id": mid_evidencia2}),
    ("narrate", {"narrative_hint": "confronta Elga"}),
])
check("caminho vivo: outcome expõe 'accuse_ops_applied'",
      bool(out_viva.get("accuse_ops_applied")))

# --------------------------------------------------------------------------- #
# 8) US3 — reação continua livre: attack e prometer funcionam normalmente
# depois de uma acusação, sem nenhum acoplamento vindo dela
out_attack = motor.apply_resolution(TOR, {"attack_ops": [
    {"alvo": ELGA, "vantagem": 5}]})
check("US3: attack funciona normalmente depois de uma acusação (sem erro)",
      "attack_ops_applied" in out_attack)

out_prom = motor.apply_resolution(ELGA, {"promise_ops": [
    {"para": TOR, "expectativa": "devolvo o que é seu, perdão"}]})
check("US3: prometer (confissão) funciona normalmente depois de uma acusação",
      bool(out_prom.get("promise_ops_applied")))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 30 (Acusar, spec 028) OK.")
