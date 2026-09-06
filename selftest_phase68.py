"""Auto-teste da Fase 68 — O corpo que luta (spec 068).

Arma e couraça NATURAIS: os mesmos blocos `weapon`/`armor` do item, aceitos no topo
do `character.md`. Antes desta spec um dragão golpeava por 1 de dano (improvisado,
porque não segura arma) e absorvia 0 (porque não veste nada) — batia como um homem
irritado e morria como um homem desarmado.

Cobre:
  - US1: `weapon_of` sobre frontmatter de PERSONAGEM; golpe sem `arma` usa a garra
  - US2: `protection_of` soma a pele ao que está vestido; absorção vira
    `golpe_absorvido`, nunca `ataque_errou`
  - US3: precedência — a mão vence o corpo; item sem bloco `weapon` (uma pedra)
    vale improvisado, NUNCA a garra (a Mente escolheu a pedra)
  - validador: declaração parcial recusada com prefixo `character:`; `armor` de
    personagem NÃO exige `wearable` (a pele não se veste), o de item continua
    exigindo
  - imutabilidade: `weapon.*` não é `status.*`, logo não se muta em jogo
  - NÃO-REGRESSÃO: quem não tem os blocos se comporta exatamente como antes

Cenário: Vulto das Escamas (STR 22 ⇒ mod +6; garra 12/STR; couraça 8; DEX 12 ⇒
defesa 11) na taverna, com Torvin (STR 16 ⇒ mod +3; DEX 8 ⇒ defesa 9) e Elga
(DEX 12 ⇒ defesa 11, sem blocos — o CONTROLE de não-regressão).

Uso:  python3 server/selftest_phase68.py
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

# A CRIATURA nasce AQUI, na cópia temporária — e deliberadamente NÃO em
# `tests/world/`. O fixture é compartilhado por 45+ fases, e acrescentar um
# personagem a ele muda contagens de cena que outras fases afirmam: medido, o
# `selftest.py` quebrou em "list_characters retorna 2" no instante em que o Vulto
# entrou na taverna. Editar a expectativa DELE para caber esta spec seria fazer uma
# feature nova reescrever a guarda de outra. Fixture compartilhado é imutável;
# cenário próprio de uma fase mora na fase.
_VULTO_MD = """\
---
type: character
id: vulto-das-escamas
name: Vulto das Escamas
controlled_by: none
weight_kg: 2200
attributes:
  STR: 22
  DEX: 12
  CON: 20
  INT: 8
  WIS: 13
  CHA: 6
status:
  hp: 180
  hp_max: 180
  hunger: saciado
  fatigue: descansado
  action: enrodilhado sobre a pedra fria
  mood: indiferente
  conditions: []
weapon:
  damage: 12
  attribute: STR
armor:
  protection: 8
origin: editorial
---

O Vulto tem garras que são foices de osso velho, e o couro que as sustenta é feito
de escamas sobrepostas, cada uma da largura de um escudo. Nada nele precisa de arma:
o corpo já é a arma, e a pele já é a armadura.
"""
_vulto_dir = _tmp / "world" / "taverna-do-gancho" / "vulto-das-escamas"
_vulto_dir.mkdir(parents=True)
(_vulto_dir / "character.md").write_text(_VULTO_MD, encoding="utf-8")

sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import validator  # noqa: E402

FAILS = []

VULTO, TORVIN, ELGA = "vulto-das-escamas", "torvin-ferreiro", "elga-taverneira"
ESPADA, GIBAO, ATICADOR = "espada-curta", "gibao-de-couro", "aticador-de-ferro"


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def force_roll(value):
    motor._roll_d20 = lambda: value


def res(**parts):
    base = {"narrative_hint": "avança para o golpe", "movement": None,
            "mutations": [], "item_transfers": [], "equip_ops": [],
            "lock_ops": [], "persuade_ops": [], "attack_ops": [], "memories": []}
    base.update(parts)
    return base


def attack(actor, alvo, arma=None, vantagem=5):
    return motor.apply_resolution(actor, res(
        attack_ops=[{"alvo": alvo, "arma": arma, "vantagem": vantagem}]))


def char_folder(cid) -> Path:
    return motor.find_character_folder(cid)


def char_fm(cid) -> dict:
    fm, _ = motor.read_doc(char_folder(cid) / "character.md")
    return fm


def read_status(cid) -> dict:
    return char_fm(cid).get("status") or {}


def set_status(cid, **fields) -> None:
    folder = char_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status.update(fields)
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def attach(cid, item_id, slot) -> None:
    """Acopla um item da cena ao corpo do personagem (montagem de cenário)."""
    found = motor.find_entity(item_id)
    folder = found[0].parent
    fm, body = motor.read_doc(folder / "item.md")
    state = dict(fm.get("state") or {})
    state["slot"] = slot
    fm["state"] = state
    motor.write_doc(folder / "item.md", fm, body)
    dest = char_folder(cid) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def dano_de(out) -> int | None:
    aplicado = out.get("attack_ops_applied") or []
    return aplicado[0]["dano"] if aplicado else None


def regras_rejeitadas(out) -> set:
    return {r.get("regra") for r in out.get("rejected") or [] if isinstance(r, dict)}


try:
    print("\n--- US1: a criatura golpeia com o corpo ---------------------------")

    # unidade: a primitiva não sabe de onde veio o frontmatter (item ou corpo)
    check("weapon_of sobre PERSONAGEM com bloco = (12, STR)",
          motor.weapon_of(char_fm(VULTO)) == (12, "STR"),
          f"{motor.weapon_of(char_fm(VULTO))}")
    check("weapon_of sobre PERSONAGEM sem bloco = improvisado (1, STR)",
          motor.weapon_of(char_fm(ELGA)) == (1, "STR"),
          f"{motor.weapon_of(char_fm(ELGA))}")

    # contrato preservado da primitiva (não pode regredir — contracts/)
    check("weapon_of(None) e weapon_of({}) seguem improvisados",
          motor.weapon_of(None) == (1, "STR") and motor.weapon_of({}) == (1, "STR"))

    # fim a fim: garra vale 12 + mod(STR 22 = +6) − proteção 0 = 18
    force_roll(15)                       # 15 + 6 = 21 vs defesa 11 de Elga
    set_status(ELGA, hp=90, hp_max=90)
    out_garra = attack(VULTO, ELGA)      # SEM arma
    check("golpe sem 'arma' usa a GARRA: dano 12+6−0 = 18",
          dano_de(out_garra) == 18, f"dano={dano_de(out_garra)}")

    # NÃO-REGRESSÃO: quem não tem garra segue improvisado (1 + mod STR 16 = +3)
    force_roll(15)
    set_status(ELGA, hp=90)
    out_soco = attack(TORVIN, ELGA)      # SEM arma, e Torvin não tem bloco
    check("NÃO-REGRESSÃO: sem bloco `weapon`, golpe desarmado segue valendo 1+3 = 4",
          dano_de(out_soco) == 4, f"dano={dano_de(out_soco)}")

    print("\n--- US2: a pele que segura o aço ---------------------------------")

    check("protection_of: couraça natural sozinha = 8",
          motor.protection_of(char_folder(VULTO)) == 8,
          f"{motor.protection_of(char_folder(VULTO))}")

    attach(VULTO, GIBAO, "torso")
    check("protection_of: couraça natural + peça VESTIDA SOMA = 8 + 2 = 10",
          motor.protection_of(char_folder(VULTO)) == 10,
          f"{motor.protection_of(char_folder(VULTO))}")

    check("NÃO-REGRESSÃO: sem bloco `armor` e nada vestido = 0",
          motor.protection_of(char_folder(ELGA)) == 0)

    # absorção: atiçador (improvisado 1) + mod(+3) = 4 contra couraça 10 ⇒ 0
    force_roll(20)                       # acerta com folga: o dado não é o assunto
    attach(TORVIN, ATICADOR, motor.HAND_SLOT)
    hp_antes = read_status(VULTO).get("hp")
    out_abs = attack(TORVIN, VULTO, ATICADOR)
    check("golpe conectado e absorvido é `golpe_absorvido`, NÃO `ataque_errou`",
          "golpe_absorvido" in regras_rejeitadas(out_abs)
          and "ataque_errou" not in regras_rejeitadas(out_abs),
          f"{regras_rejeitadas(out_abs)}")
    check("golpe absorvido não tira hp do alvo",
          read_status(VULTO).get("hp") == hp_antes)

    print("\n--- US3: a mão vence o corpo -------------------------------------")

    attach(VULTO, ESPADA, motor.HAND_SLOT)
    force_roll(15)
    set_status(ELGA, hp=90)
    out_espada = attack(VULTO, ELGA, ESPADA)
    check("com `arma` declarada vale a ESPADA (6+6 = 12), não a garra (18)",
          dano_de(out_espada) == 12, f"dano={dano_de(out_espada)}")

    force_roll(15)
    set_status(ELGA, hp=90)
    out_sem = attack(VULTO, ELGA)        # a espada segue na mão, mas não foi passada
    check("sem `arma`, mesmo com espada na mão, vale a GARRA (18)",
          dano_de(out_sem) == 18, f"dano={dano_de(out_sem)}")

    attach(VULTO, ATICADOR, motor.HAND_SLOT)
    force_roll(15)
    set_status(ELGA, hp=90)
    out_pedra = attack(VULTO, ELGA, ATICADOR)
    check("item SEM bloco `weapon` vale IMPROVISADO (1+6 = 7), nunca a garra",
          dano_de(out_pedra) == 7, f"dano={dano_de(out_pedra)}")

    print("\n--- validador: a regra compartilhada -----------------------------")

    base = {"type": "character", "id": "x", "name": "X", "controlled_by": "none",
            "attributes": {a: 10 for a in ("STR", "DEX", "CON", "INT", "WIS", "CHA")},
            "status": {"hp": 10, "hp_max": 10}}

    def com(**extra):
        fm = dict(base)
        fm.update(extra)
        return validator.validate(fm)

    parcial = com(weapon={"damage": 12})
    check("character: `weapon` parcial é RECUSADO, com prefixo 'character:'",
          bool(parcial) and parcial[0].startswith("character: 'weapon'"),
          f"{parcial}")
    check("character: `weapon.damage` < 1 é recusado",
          any("weapon.damage" in e for e in com(weapon={"damage": 0,
                                                       "attribute": "STR"})))
    check("character: `weapon.attribute` fora de (STR, DEX) é recusado",
          any("weapon.attribute" in e for e in com(weapon={"damage": 5,
                                                          "attribute": "CON"})))
    check("character: `armor` SEM `wearable` é ACEITO (a pele não se veste)",
          com(armor={"protection": 8}) == [])
    check("character: `armor.protection` negativa é recusada",
          any("armor.protection" in e for e in com(armor={"protection": -1})))
    check("character: os dois blocos bem declarados passam",
          com(weapon={"damage": 12, "attribute": "STR"},
              armor={"protection": 8}) == [])

    item_sem_wearable = validator.validate(
        {"type": "item", "id": "i", "name": "I", "armor": {"protection": 2}})
    check("ITEM: `armor` sem `wearable` CONTINUA recusado (regra não atravessa)",
          any("exige 'wearable'" in e for e in item_sem_wearable),
          f"{item_sem_wearable}")
    check("ITEM: mensagem de `weapon` parcial segue com prefixo 'item:'",
          any(e.startswith("item: 'weapon'") for e in validator.validate(
              {"type": "item", "id": "i", "name": "I", "weapon": {"damage": 6}})))

    print("\n--- imutabilidade: a garra é editorial ---------------------------")

    out_mut = motor.apply_resolution(VULTO, res(mutations=[
        {"target": VULTO, "path": "weapon.damage", "value": 99}]))
    # `applied` NUNCA vem vazio: `_ensure_actor_touched` (FR-014, spec 020) grava
    # `status.action` quando nada mais tocou o ator. A asserção precisa ser sobre a
    # AUSÊNCIA da mutação pedida, não sobre a lista estar vazia.
    aplicou_garra = any(a.get("path") == "weapon.damage"
                        for a in out_mut.get("applied") or [] if isinstance(a, dict))
    check("mutar `weapon.damage` em jogo é RECUSADO (só `status.*` é mutável)",
          not aplicou_garra and bool(out_mut.get("rejected")),
          f"applied={out_mut.get('applied')} rejected={out_mut.get('rejected')}")
    check("a garra continua valendo 12 depois da tentativa",
          motor.weapon_of(char_fm(VULTO)) == (12, "STR"))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 68 (spec 068) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
