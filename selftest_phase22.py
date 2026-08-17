"""Auto-teste da Fase 22 — Corpo do personagem (spec 019).

Cobre:
  - US1 compatibilidade: sem `body` declarado, herda o corpo humano padrão
    (byte-a-byte com validator.SLOTS de hoje); nenhuma ficha muda de comportamento.
  - fonte única: body_of/slot_capacity derivam do PERSONAGEM; auditoria de que
    nenhum ponto do motor lê validator.SLOTS como a capacidade de alguém (SC-005).
  - US2 corpos não-padrão: quatro-mãos (SC-002); PESSOA COM PERNA DE PAU (humano
    subtrativo — recusa a bota com corpo_sem_slot); CACHORRO (segura na BOCA via
    slot de pega `focinho`; não veste espada em `mao` que não tem; coleira
    encaixa); slot novo genérico (asas); criatura SEM pega (não segura nada).
  - SLOT DE PEGA (pega:true): onde os itens pegos vão. A mão do humano por
    fallback; a boca do cão por declaração. take/dar respeitam o corpo.
  - validação de corpo malformado (forma sim, nome livre não; forma rica).

Roda sobre uma CÓPIA temporária do fixture (server/tests/world). Uso:
  python3 server/selftest_phase22.py
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
import validator  # noqa: E402

FAILS = []
TAVERNA = motor.WORLD_DIR / "taverna-do-gancho"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def res(**parts):
    base = {"narrative_hint": "faz o que pretendia", "movement": None,
            "mutations": [], "item_transfers": [], "equip_ops": [], "memories": []}
    base.update(parts)
    return base


def author(relpath: str, text: str) -> None:
    p = motor.WORLD_DIR / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def char_md(cid, name, body_yaml=""):
    return (
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        "controlled_by: player_local\nweight_kg: 40\n"
        "attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        "skills: {}\n"
        "status:\n  hp: 20\n  hp_max: 20\n  hunger: saciado\n  fatigue: baixo\n"
        "  action: parado\n  mood: neutro\n  conditions: []\n"
        f"{body_yaml}origin: editorial\n---\n\n{name} está aqui.\n"
    )


def item_md(iid, name, slot, size="P", weight=0.5):
    return (
        f"---\ntype: item\nid: {iid}\nname: {name}\nsize: {size}\n"
        f"weight_kg: {weight}\nwearable:\n  slot: {slot}\norigin: editorial\n---\n\n"
        f"{name}.\n"
    )


print("--- Bloco A: leituras derivadas puras (body_of / slot_capacity / pega) --")

humano = {"attributes": {}}  # sem body → padrão humano
check("A1: sem body herda o humano padrão (== validator.DEFAULT_BODY)",
      motor.body_of(humano) == validator.DEFAULT_BODY)
check("A2: slot_capacity humano — mao=2, dedo=10, torso=1",
      motor.slot_capacity(humano, "mao") == 2
      and motor.slot_capacity(humano, "dedo") == 10
      and motor.slot_capacity(humano, "torso") == 1)
quatro = {"body": {"mao": 4, "torso": 1}}
check("A3: corpo declarado é COMPLETO (sem merge com humano) — dedo ausente = 0",
      motor.slot_capacity(quatro, "mao") == 4
      and motor.slot_capacity(quatro, "dedo") == 0
      and motor.slot_capacity(quatro, "pes") == 0)
check("A4: forma rica {capacidade, pega} — capacidade lida certo",
      motor.slot_capacity({"body": {"focinho": {"capacidade": 1, "pega": True}}},
                          "focinho") == 1)
check("A5: grasp_slot_of humano = mao (fallback, sem declarar nada)",
      motor.grasp_slot_of(humano) == "mao")
check("A6: grasp_slot_of usa o slot marcado pega:true (a boca do cão)",
      motor.grasp_slot_of({"body": {"focinho": {"capacidade": 1, "pega": True},
                                    "mao": 0}}) == "focinho")
check("A7: corpo sem mãos e sem pega não segura nada (grasp = None)",
      motor.grasp_slot_of({"body": {"torso": 1, "cauda": 1}}) is None)


print("\n--- Bloco B: checagens puras (corpo_sem_slot vs ocupado) ---------------")

check("B1: check_mao capacidade 0 → corpo_sem_slot",
      (motor.check_mao("x", [], 0) or {}).get("regra") == "corpo_sem_slot")
check("B2: check_mao cap 4 com 3 ocupantes → ok (SC-002)",
      motor.check_mao("x", ["a", "b", "c"], 4) is None)
check("B3: check_mao cap 2 com 2 ocupantes → maos_ocupadas",
      (motor.check_mao("x", ["a", "b"], 2) or {}).get("regra") == "maos_ocupadas")
check("B4: check_slot capacidade 0 → corpo_sem_slot (não slot_ocupado)",
      (motor.check_slot("i", "asas", [], 0) or {}).get("regra") == "corpo_sem_slot")
check("B5: check_slot cap 1 cheio → slot_ocupado",
      (motor.check_slot("i", "torso", ["j"], 1) or {}).get("regra") == "slot_ocupado")
check("B6: check_slot cap 1 vazio → ok",
      motor.check_slot("i", "torso", [], 1) is None)


print("\n--- Bloco C: validação do campo body (forma int e forma rica) ----------")


def verr(fm):
    return validator.validate({"type": "character", "id": "c", "name": "C",
                               "controlled_by": "arbiter",
                               "attributes": {a: 10 for a in
                                              ("STR", "DEX", "CON", "INT", "WIS", "CHA")},
                               "skills": {}, "status": {}, **fm})


check("C1: body com capacidade negativa reprovado",
      any("body" in e for e in verr({"body": {"mao": -1}})))
check("C2: body com float reprovado",
      any("body" in e for e in verr({"body": {"mao": 1.5}})))
check("C3: body com bool reprovado",
      any("body" in e for e in verr({"body": {"mao": True}})))
check("C4: body não-mapa reprovado",
      any("body" in e for e in verr({"body": [1, 2]})))
check("C5: body com nome de slot livre ('tentaculo') é ACEITO (vocab aberto)",
      not any("body" in e for e in verr({"body": {"tentaculo": 6}})))
check("C6: forma rica {capacidade, pega} válida é aceita",
      not any("body" in e for e in
              verr({"body": {"focinho": {"capacidade": 1, "pega": True}}})))
check("C7: forma rica com pega não-booleano reprovada",
      any("pega" in e for e in
          verr({"body": {"focinho": {"capacidade": 1, "pega": "sim"}}})))
check("C8: forma rica com capacidade inválida reprovada",
      any("capacidade" in e for e in verr({"body": {"focinho": {"capacidade": -2}}})))


print("\n--- Bloco D: fim a fim — PESSOA COM PERNA DE PAU (humano subtrativo) ----")

# corpo humano MENOS um pé: pes:0 (a perna de pau não calça); resto humano. Sem
# marcar pega: a mão continua sendo o slot de pega por fallback.
_perna_body = "body:\n" + "".join(
    f"  {s}: {0 if s == 'pes' else c}\n" for s, c in validator.DEFAULT_BODY.items())
author("taverna-do-gancho/perna-de-pau/character.md",
       char_md("perna-de-pau", "Vesna da Perna de Pau", _perna_body))
author("taverna-do-gancho/bota-teste/item.md",
       item_md("bota-teste", "Bota de Couro", "pes"))
author("taverna-do-gancho/elmo-teste/item.md",
       item_md("elmo-teste", "Elmo Amassado", "cabeca"))
author("taverna-do-gancho/anel-teste/item.md",
       item_md("anel-teste", "Anel Simples", "mao", size="PP", weight=0.05))

fis_vesna = motor.get_context("perna-de-pau")["self"]["fisico"]
check("D0: perna de pau ainda pega com a MÃO (fallback) — pega_slot=mao, 2 livres",
      fis_vesna["pega_slot"] == "mao" and fis_vesna["maos_livres"] == 2)
out_bota = motor.apply_resolution("perna-de-pau", res(
    equip_ops=[{"op": "equip", "item": "bota-teste"}]))
check("D1: calçar bota num corpo sem 'pes' → recusa corpo_sem_slot",
      any(r.get("regra") == "corpo_sem_slot" for r in out_bota.get("rejected") or []))
check("D2: a bota NÃO foi vestida (continua no chão da taverna)",
      (TAVERNA / "bota-teste").exists()
      and not (TAVERNA / "perna-de-pau" / "bota-teste").exists())
out_elmo = motor.apply_resolution("perna-de-pau", res(
    equip_ops=[{"op": "equip", "item": "elmo-teste"}]))
check("D3: o resto do corpo humano segue vestindo — elmo (cabeca) encaixa",
      any(a.get("item") == "elmo-teste"
          for a in out_elmo.get("equip_ops_applied") or []))
motor.apply_resolution("perna-de-pau", res(
    item_transfers=[{"item": "anel-teste", "to": "perna-de-pau"}]))
anel_fm, _ = motor.read_doc(TAVERNA / "perna-de-pau" / "anel-teste" / "item.md")
check("D4: item pego vai para a MÃO da Vesna (state.slot = mao)",
      motor.item_slot(anel_fm) == "mao")


print("\n--- Bloco E: fim a fim — CACHORRO (segura na BOCA, veste coleira) ------")

_dog_body = ("body:\n  cabeca: 1\n  pescoco: 1\n  torso: 1\n  cauda: 1\n  pata: 4\n"
             "  focinho:\n    capacidade: 1\n    pega: true\n")
author("taverna-do-gancho/cao-farejador/character.md",
       char_md("cao-farejador", "Farejador, o Cão", _dog_body))
author("taverna-do-gancho/espada-teste/item.md",
       item_md("espada-teste", "Espada Curta", "mao", size="M", weight=1.5))
author("taverna-do-gancho/coleira-teste/item.md",
       item_md("coleira-teste", "Coleira de Couro", "pescoco", weight=0.2))
author("taverna-do-gancho/graveto-teste/item.md",
       item_md("graveto-teste", "Graveto", "mao", size="P", weight=0.3))
author("taverna-do-gancho/osso-teste/item.md",
       item_md("osso-teste", "Osso Roído", "mao", size="P", weight=0.4))

fis_dog = motor.get_context("cao-farejador")["self"]["fisico"]
check("E1: o slot de pega do cão é a BOCA (pega_slot=focinho, 1 vaga)",
      fis_dog["pega_slot"] == "focinho" and fis_dog["maos_totais"] == 1)
check("E2: o corpo do cão desce no contexto do próprio dono (pata:4, cauda:1)",
      motor.slot_capacity({"body": fis_dog.get("corpo", {})}, "pata") == 4
      and fis_dog.get("corpo", {}).get("cauda") == 1)
out_esp = motor.apply_resolution("cao-farejador", res(
    equip_ops=[{"op": "equip", "item": "espada-teste"}]))
check("E3: VESTIR espada em 'mao' que o cão não tem → corpo_sem_slot",
      any(r.get("regra") == "corpo_sem_slot" for r in out_esp.get("rejected") or []))
out_col = motor.apply_resolution("cao-farejador", res(
    equip_ops=[{"op": "equip", "item": "coleira-teste"}]))
check("E4: coleira (pescoco) encaixa no cão",
      any(a.get("item") == "coleira-teste"
          for a in out_col.get("equip_ops_applied") or []))
# o cão PEGA o graveto — vai para a boca (slot de pega), não para "mao"
motor.apply_resolution("cao-farejador", res(
    item_transfers=[{"item": "graveto-teste", "to": "cao-farejador"}]))
grav_fm, _ = motor.read_doc(TAVERNA / "cao-farejador" / "graveto-teste" / "item.md")
check("E5: o cão segura na BOCA — graveto pego fica com state.slot = focinho",
      motor.item_slot(grav_fm) == "focinho")
# boca cheia (cap 1): um segundo item na boca é recusado
out_osso = motor.apply_resolution("cao-farejador", res(
    item_transfers=[{"item": "osso-teste", "to": "cao-farejador"}]))
check("E6: boca já ocupada → 2º item na boca recusado (maos_ocupadas)",
      any(r.get("regra") == "maos_ocupadas" for r in out_osso.get("rejected") or []))


print("\n--- Bloco F: criatura SEM pega (caso-zero, sem divisão por zero) --------")

author("taverna-do-gancho/enguia-teste/character.md",
       char_md("enguia-teste", "Enguia", "body:\n  cabeca: 1\n  torso: 1\n"))
author("taverna-do-gancho/isca-teste/item.md",
       item_md("isca-teste", "Isca", "mao", size="PP", weight=0.05))
fis_eng = motor.get_context("enguia-teste")["self"]["fisico"]
check("F1: enguia sem pega → maos_livres 0, maos_totais 0, pega_slot None",
      fis_eng["maos_livres"] == 0 and fis_eng["maos_totais"] == 0
      and fis_eng["pega_slot"] is None)
out_isca = motor.apply_resolution("enguia-teste", res(
    item_transfers=[{"item": "isca-teste", "to": "enguia-teste"}]))
check("F2: enguia não segura nada — take recusado com corpo_sem_slot",
      any(r.get("regra") == "corpo_sem_slot" for r in out_isca.get("rejected") or []))


print("\n--- Bloco G: slot novo genérico (asas) e compat US1 --------------------")

author("taverna-do-gancho/ser-alado/character.md",
       char_md("ser-alado", "Ser Alado", "body:\n  torso: 1\n  asas: 2\n  mao: 2\n"))
author("taverna-do-gancho/manto-teste/item.md",
       item_md("manto-teste", "Manto de Penas", "asas"))
out_asas = motor.apply_resolution("ser-alado", res(
    equip_ops=[{"op": "equip", "item": "manto-teste"}]))
check("G1: item wearable.slot 'asas' encaixa num corpo com asas",
      any(a.get("item") == "manto-teste"
          for a in out_asas.get("equip_ops_applied") or []))

# US1: um humano do fixture não muda
tor_fm, _ = motor.read_doc(TAVERNA / "torvin-ferreiro" / "character.md")
check("G2 (US1): Torvin sem body → slot_capacity mao == 2, body_of == humano",
      motor.slot_capacity(tor_fm, "mao") == 2
      and motor.body_of(tor_fm) == validator.DEFAULT_BODY)
fis_tor = motor.get_context("torvin-ferreiro")["self"]["fisico"]
check("G3 (US1): maos_livres do Torvin == 2 e pega_slot == mao",
      fis_tor["maos_livres"] == 2 and fis_tor["pega_slot"] == "mao")


print("\n--- Bloco I: corpo em forma INLINE aninhada NÃO some do seletor --------")

# Regressão: o parser stdlib não lia mapa flow ANINHADO — `focinho: {capacidade:
# 1, pega: true}` virava string, o validador reprovava e o personagem sumia do
# seletor (FR-010). O cão escrito pelo exemplo inline do README ficava invisível.
author("taverna-do-gancho/cao-inline/character.md",
       "---\ntype: character\nid: cao-inline\nname: Cao Inline\n"
       "controlled_by: player_local\nweight_kg: 25\n"
       "attributes: {STR: 10, DEX: 12, CON: 10, INT: 4, WIS: 12, CHA: 8}\n"
       "skills: {}\n"
       "status: {hp: 10, hp_max: 10, hunger: saciado, fatigue: baixo, "
       "action: parado, mood: calmo, conditions: []}\n"
       "body: {cabeca: 1, torso: 1, focinho: {capacidade: 1, pega: true}}\n"
       "origin: editorial\n---\n\nUm cao escrito inline.\n")
_inline_fm, _ = motor.read_doc(TAVERNA / "cao-inline" / "character.md")
check("I1: body inline aninhado vira mapa (não string) e valida",
      isinstance(_inline_fm.get("body", {}).get("focinho"), dict)
      and validator.validate(_inline_fm) == [])
check("I2: o cão inline aparece em list_characters (não sumiu do seletor)",
      any(c["id"] == "cao-inline" for c in motor.list_characters()))
check("I3: e seu slot de pega é a boca",
      motor.grasp_slot_of(_inline_fm) == "focinho")


print("\n--- Bloco H: auditoria de fonte única (SC-005) -------------------------")

# O Motor virou um pacote (spec 021): a fonte agora se espalha pelos módulos de
# motor/. Concatena todos os .py do pacote para a auditoria de fonte única.
_motor_dir = SERVER_DIR / "motor"
_src = "".join(p.read_text(encoding="utf-8") for p in sorted(_motor_dir.glob("*.py")))
check("H1: o Motor não indexa validator.SLOTS[...] (fonte única no personagem)",
      "validator.SLOTS[" not in _src)
check("H2: o Motor não testa 'in validator.SLOTS' (usa body_of do personagem)",
      "in validator.SLOTS" not in _src)


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 22 (spec 019) passaram.")
