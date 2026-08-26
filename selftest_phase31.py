"""Auto-teste da Fase 31 — Domínio da Memória (spec 029).

Sem nenhum modelo/LLM — exercita o Motor direto (`motor.apply_resolution`,
`motor.memoria.record_event`), molde das fases 27-30. Cobre:

  - US1: o retrofit evento→domain — cada evento já mapeado grava o domínio
    certo (via `record_event`, e via `apply_resolution` ponta a ponta para
    ao menos uma família de cada canal: ataque, furto, transferência);
    eventos utilitários (`equip`/`lock`/`mutate`/`wield`) gravam
    `domain: nenhuma`.
  - `validator.py` rejeita `domain` fora do enum.
  - US2: `create_memory` exige `domain` — ausente ou fora do enum é
    rejeitado ANTES de qualquer escrita; `"nenhuma"` é aceito; um domínio
    real grava corretamente.
  - US3: `proficiencies_for` — peso por intensidade, desconto de vencida a
    ¼, domínio sem memória = nível 0, sempre as 5 chaves presentes,
    determinismo entre duas chamadas.

Uso:  python3 server/selftest_phase31.py
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
import validator  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"
TOR, ELGA = "torvin-ferreiro", "elga-taverneira"
MOEDA1, MOEDA2 = "moeda-de-prata-1", "moeda-de-prata-2"


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
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: baixo\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")


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


def last_domain(cid: str) -> str | None:
    mems = memories(cid)
    return mems[-1][0].get("domain") if mems else None


# --------------------------------------------------------------------------- #
# 1) US1 — retrofit: todo evento já mapeado em _DOMAIN_BY_EVENT grava o
# domínio certo. Testado via record_event direto (cobre as 29 entradas sem
# precisar simular cada mecânica de jogo).
for evento, domain_esperado in motor._DOMAIN_BY_EVENT.items():
    mem_id = motor.memoria.record_event(
        TOR, f"teste retrofit: {evento}", evento, [TOR, ELGA])
    check(f"retrofit: evento='{evento}' grava domain='{domain_esperado}'",
          last_domain(TOR) == domain_esperado,
          f"obtido: {last_domain(TOR)}")

# eventos utilitários — deliberadamente fora da tabela, caem em "nenhuma"
for evento_util in ("equip", "lock", "mutate", "wield"):
    motor.memoria.record_event(TOR, f"teste utilitário: {evento_util}",
                               evento_util, [TOR])
    check(f"retrofit: evento utilitário '{evento_util}' grava domain='nenhuma'",
          last_domain(TOR) == "nenhuma", f"obtido: {last_domain(TOR)}")

# evento SEM entrada na tabela (hipotético, nunca revisado) — mesma regra
motor.memoria.record_event(TOR, "evento nunca visto antes", "evento-fantasma", [TOR])
check("retrofit: evento não mapeado grava domain='nenhuma' (nunca erro)",
      last_domain(TOR) == "nenhuma")

# --------------------------------------------------------------------------- #
# 2) US1 — ponta a ponta via apply_resolution (não só chamada direta):
# ataque, furto e transferência, as três famílias mais usadas em jogo.
force_hit = motor._roll_d20
motor._roll_d20 = lambda: 20  # garante acerto, independente de atributos/DC
motor.apply_resolution(TOR, {"attack_ops": [{"alvo": ELGA, "vantagem": 5}]})
motor._roll_d20 = force_hit
check("ponta a ponta: attack_ops grava domain='combate' no atacante",
      last_domain(TOR) == "combate")
check("ponta a ponta: attack_ops grava domain='combate' no alvo",
      last_domain(ELGA) == "combate")

dar(TOR, MOEDA1)
motor.apply_resolution(TOR, {"item_transfers": [{"item": MOEDA1, "to": ELGA}]})
check("ponta a ponta: item_transfers grava domain='comercio' no doador",
      last_domain(TOR) == "comercio")
check("ponta a ponta: item_transfers grava domain='comercio' no receptor",
      last_domain(ELGA) == "comercio")

dar(ELGA, MOEDA2)
force = motor._roll_d20
# mesma calibração do phase30: d20=8 satisfaz furto flagrado E percepção
motor._roll_d20 = lambda: 8
motor.apply_resolution(TOR, {"steal_ops": [{"alvo": ELGA, "item": MOEDA2, "exposicao": 5}]})
motor._roll_d20 = force
check("ponta a ponta: steal_ops grava domain='crime' no ladrão",
      last_domain(TOR) == "crime")

# --------------------------------------------------------------------------- #
# 3) validator.py — domain fora do enum é rejeitado
_erros_validos = validator.validate({
    "type": "memory", "id": "mem-x", "timestamp_start": 0, "timestamp_end": 1,
    "intensity": "small", "state": "active", "domain": "combate",
})
check("validator: domain válido não gera erro",
      not any("domain" in e for e in _erros_validos), str(_erros_validos))
_erros_invalidos = validator.validate({
    "type": "memory", "id": "mem-x", "timestamp_start": 0, "timestamp_end": 1,
    "intensity": "small", "state": "active", "domain": "alquimia",
})
check("validator: domain fora do enum é rejeitado",
      any("domain" in e for e in _erros_invalidos), str(_erros_invalidos))
_erros_ausente = validator.validate({
    "type": "memory", "id": "mem-x", "timestamp_start": 0, "timestamp_end": 1,
    "intensity": "small", "state": "active",
})
check("validator: domain ausente continua válido (memórias antigas)",
      not any("domain" in e for e in _erros_ausente), str(_erros_ausente))

# --------------------------------------------------------------------------- #
# 4) US2 — create_memory exige domain, na fronteira da tool (antes de
# qualquer escrita). Via apply_resolution direto na chave "memories" (o
# mesmo caminho que _create_memories/T009 processa) — cobre o executor sem
# precisar simular o loop de tool-calling inteiro.
n_elga = len(memories(ELGA))
motor.apply_resolution(TOR, {"memories": [
    {"target": ELGA, "content": "sem domain nenhum", "intensity": "small",
     "ttl_seconds": 3600}]})  # domain ausente do dict
check("US2: memória sem 'domain' ainda grava (executor tem fallback), "
      "mas com domain='nenhuma' — a REJEIÇÃO de verdade é na fronteira da "
      "tool (T008), testada abaixo via manifest/handler",
      last_domain(ELGA) == "nenhuma")

# 4a) a rejeição estrutural de verdade acontece no HANDLER da tool (dentro de
# `ctx.execute`, o mesmo usado por `resolver_proposta`), antes de a op chegar
# à fila — testado chamando o dispatch de tool diretamente via um roteiro.
ctx_tor = motor.get_context(TOR)
intent_base = {"action": "registra uma lembrança", "target": ELGA,
               "utterance": None, "movement": None, "note": ""}

res_sem_domain = []
selftest_helpers.resolve_scripted(intent_base, ctx_tor, [
    ("create_memory", {"target": ELGA, "content": "teste", "intensity": "small",
                        "ttl_seconds": 3600}),
], captured=res_sem_domain)
check("US2: create_memory sem 'domain' é rejeitado na fronteira da tool",
      res_sem_domain and res_sem_domain[0].get("ok") is False
      and res_sem_domain[0].get("campo") == "domain", str(res_sem_domain))

res_domain_invalido = []
selftest_helpers.resolve_scripted(intent_base, ctx_tor, [
    ("create_memory", {"target": ELGA, "content": "teste", "intensity": "small",
                        "ttl_seconds": 3600, "domain": "alquimia"}),
], captured=res_domain_invalido)
check("US2: create_memory com 'domain' fora do enum é rejeitado",
      res_domain_invalido and res_domain_invalido[0].get("ok") is False
      and res_domain_invalido[0].get("campo") == "domain", str(res_domain_invalido))

n_elga_antes = len(memories(ELGA))
res_nenhuma = []
selftest_helpers.resolve_scripted(intent_base, ctx_tor, [
    ("create_memory", {"target": ELGA, "content": "um momento qualquer, sem prática nenhuma",
                        "intensity": "small", "ttl_seconds": 3600, "domain": "nenhuma"}),
], captured=res_nenhuma)
check("US2: create_memory com domain='nenhuma' é ACEITO (resposta válida, não erro)",
      res_nenhuma and res_nenhuma[0].get("ok") is True, str(res_nenhuma))
check("US2: a memória com domain='nenhuma' nasce de verdade",
      len(memories(ELGA)) == n_elga_antes + 1 and last_domain(ELGA) == "nenhuma")

res_domain_real = []
selftest_helpers.resolve_scripted(intent_base, ctx_tor, [
    ("create_memory", {"target": ELGA, "content": "vi Torvin martelar até tarde, aprendendo o ofício",
                        "intensity": "medium", "ttl_seconds": 3600, "domain": "crime"}),
], captured=res_domain_real)
check("US2: create_memory com domain válido é aceito e grava o domínio certo",
      res_domain_real and res_domain_real[0].get("ok") is True
      and last_domain(ELGA) == "crime", str(res_domain_real))

# --------------------------------------------------------------------------- #
# 5) US3 — proficiencies_for: peso por intensidade, desconto de vencida a
# ¼, domínio vazio = nível 0, determinismo. Personagem ISOLADO para não
# herdar ruído das seções anteriores.
_mk_char("prof-p31", "Testador de Proficiência")
PROF = "prof-p31"

check("proficiencia: personagem sem nenhuma memória tem todos os domínios em nível 0",
      motor.proficiencies_for(PROF) == {
          "combate": 0, "crime": 0, "comercio": 0, "social": 0, "deslocamento": 0,
          "cura": 0,  # spec 032: 1º domínio de fase 2
          "cozinha": 0,  # spec 048: 2º domínio de fase 2
          "acougue": 0,  # spec 050: 3º domínio de fase 2
          "fogo": 0,  # spec 053: 6º domínio de fase 2
          "ferraria": 0,  # spec 052: 4º domínio de fase 2 (forjar arma)
          "armaria": 0,   # spec 052: 5º — DOIS de uma vez, e por isso separados:
                          # praticar armadura não faz ninguém melhor com espada
          "herbalismo": 0,  # spec 054: 7º domínio de fase 2 (colher)
      }, str(motor.proficiencies_for(PROF)))

# uma memória VIVA 'giant' em crime (peso 8.0) sobe o fator pela curva
# assintótica (spec 048, R12): TETO·peso/(peso+K) = 10·8/(8+16) = 3.333...
motor.memoria._write_memory(
    motor.find_character_folder(PROF), "um furto e tanto",
    intensity="giant", domain="crime", involved=[PROF])
check("proficiencia: memória viva 'giant' em crime (peso 8.0) dá fator ~3.33 (curva sem teto)",
      abs(motor.proficiencies_for(PROF)["crime"] - (10.0 * 8.0 / (8.0 + 16.0))) < 1e-9,
      str(motor.proficiencies_for(PROF)))
check("proficiencia: os demais domínios continuam em 0 (não vaza entre domínios)",
      all(v == 0 for k, v in motor.proficiencies_for(PROF).items() if k != "crime"))

_mk_char("prof-vencida-p31", "Testador de Memória Vencida")
VENC = "prof-vencida-p31"
mid_vencida = motor.memoria._write_memory(
    motor.find_character_folder(VENC), "um furto de muito tempo atrás",
    intensity="giant", domain="crime", involved=[VENC])
vfolder = motor.find_character_folder(VENC) / "memories" / f"{mid_vencida}.md"
vfm, vbody = motor.read_doc(vfolder)
vfm["timestamp_end"] = int(time.time()) - 10
motor.write_doc(vfolder, vfm, vbody)
check("proficiencia: a MESMA memória 'giant', VENCIDA (peso 8.0×¼=2.0), cai pra ~1.11 — "
     "menos, nunca zero (a curva não trava em degrau)",
      abs(motor.proficiencies_for(VENC)["crime"] - (10.0 * 2.0 / (2.0 + 16.0))) < 1e-9,
      str(motor.proficiencies_for(VENC)))

check("proficiencia: determinismo — duas chamadas seguidas sem mutação são idênticas",
      motor.proficiencies_for(PROF) == motor.proficiencies_for(PROF))

check("proficiencia: as chaves de domínio estão sempre presentes "
     "(5 de fase 1 + cura/032 + cozinha/048 + acougue/050 + ferraria e armaria/052 "
     "+ fogo/053 + herbalismo/054)",
      set(motor.proficiencies_for(PROF).keys()) ==
      {"combate", "crime", "comercio", "social", "deslocamento", "cura", "cozinha",
       "acougue", "ferraria", "armaria", "fogo", "herbalismo"})

# achado da validação manual (T017, quickstart contra servidor real): um
# personagem INEXISTENTE devolvia 200 com zeros, silenciosamente, porque
# _iter_memories engole a exceção de find_character_folder — errado aqui,
# porque character_id é sempre o PRÓPRIO sujeito da consulta, não um
# terceiro opcional (diferente de familiarity_with/sentiment_toward).
try:
    motor.proficiencies_for("personagem-que-nao-existe-p31")
    check("proficiencia: personagem inexistente propaga MotorError", False,
          "não levantou exceção nenhuma")
except motor.MotorError:
    check("proficiencia: personagem inexistente propaga MotorError", True)

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 31 (Domínio da Memória, spec 029) OK.")
