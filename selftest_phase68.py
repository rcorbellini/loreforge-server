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
body:
  cabeca: 1
  garras:
    capacidade: 0
    weapon:
      damage: 12
      attribute: STR
  fauces:
    capacidade: 0
    weapon:
      damage: 4
      attribute: STR
  dorso:
    capacidade: 1
    armor:
      protection: 8
  pernas: 1
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


def fixar_parte(slot):
    """Fixa o SORTEIO da parte (o análogo de `force_roll` para o dado)."""
    motor.fisica.primitivas._escolher_parte = \
        lambda armadas: next(a for a in armadas if a[0] == slot)


def parte_de(out):
    ap = out.get("attack_ops_applied") or []
    return ap[0].get("parte") if ap else None


try:
    print("\n--- US1: a criatura golpeia com uma PARTE do corpo ----------------")

    vulto = char_fm(VULTO)
    check("natural_weapons_of lista as duas partes armadas, na ordem de declaração",
          motor.natural_weapons_of(vulto) == [("garras", 12, "STR"),
                                              ("fauces", 4, "STR")],
          f"{motor.natural_weapons_of(vulto)}")
    check("quem não tem parte armada devolve lista vazia",
          motor.natural_weapons_of(char_fm(ELGA)) == []
          and motor.pick_natural_weapon(char_fm(ELGA)) is None)

    # a primitiva de item NÃO mudou: lê o bloco de qualquer mapa (item OU parte)
    check("weapon_of sobre a PARTE do corpo = (12, STR)",
          motor.weapon_of(motor.fisica.body_of(vulto)["garras"]) == (12, "STR"))
    check("weapon_of(None)/({}) seguem improvisados (contrato preservado)",
          motor.weapon_of(None) == (1, "STR") and motor.weapon_of({}) == (1, "STR"))

    # o sorteio é VARIADO: as duas partes saem ao longo de muitas tentativas
    vistas = {motor.pick_natural_weapon(vulto)[0] for _ in range(200)}
    check("o sorteio da parte é VARIADO (golpear com o corpo é instintivo)",
          vistas == {"garras", "fauces"}, f"{vistas}")

    # fim a fim: garra 12 + mod(STR 22 = +6) − proteção 0 = 18
    fixar_parte("garras")
    force_roll(15)                       # 15 + 6 = 21 vs defesa 11 de Elga
    set_status(ELGA, hp=90, hp_max=90)
    out_garra = attack(VULTO, ELGA)      # SEM arma
    check("golpe sem `arma` usa a GARRA sorteada: dano 12+6−0 = 18",
          dano_de(out_garra) == 18, f"dano={dano_de(out_garra)}")
    check("a op RELATA a parte que golpeou (senão A Mente não narra o COMO)",
          parte_de(out_garra) == "garras", f"parte={parte_de(out_garra)}")

    fixar_parte("fauces")
    force_roll(15)
    set_status(ELGA, hp=90)
    out_fauces = attack(VULTO, ELGA)
    check("a outra parte dá OUTRO dano: fauces 4+6−0 = 10",
          dano_de(out_fauces) == 10 and parte_de(out_fauces) == "fauces",
          f"dano={dano_de(out_fauces)} parte={parte_de(out_fauces)}")

    # a memória precisa dizer COM O QUÊ — é ela que A Mente relê para narrar depois
    resumos = []
    for md in (char_folder(VULTO) / "memories").glob("mem-*.md"):
        fm_m, _ = motor.read_doc(md)
        resumos.append(str(fm_m.get("summary", "")))
    check("a memória do golpe nomeia a PARTE, não some com o COMO",
          any("fauces" in r for r in resumos),
          f"{[r for r in resumos if 'olpe' in r]}")

    # NÃO-REGRESSÃO: quem não tem parte armada segue improvisado (1 + mod STR 16 = +3)
    force_roll(15)
    set_status(ELGA, hp=90)
    out_soco = attack(TORVIN, ELGA)
    check("NÃO-REGRESSÃO: sem parte armada, golpe desarmado segue valendo 1+3 = 4",
          dano_de(out_soco) == 4 and parte_de(out_soco) is None,
          f"dano={dano_de(out_soco)} parte={parte_de(out_soco)}")

    print("\n--- US2: a PARTE que segura o aço --------------------------------")

    check("protection_of: a parte `dorso` com `armor` sozinha = 8",
          motor.protection_of(char_folder(VULTO)) == 8,
          f"{motor.protection_of(char_folder(VULTO))}")

    attach(VULTO, GIBAO, "dorso")
    check("protection_of: parte + peça VESTIDA SOMA = 8 + 2 = 10",
          motor.protection_of(char_folder(VULTO)) == 10,
          f"{motor.protection_of(char_folder(VULTO))}")

    check("NÃO-REGRESSÃO: sem parte que absorve e nada vestido = 0",
          motor.protection_of(char_folder(ELGA)) == 0)

    # absorção: atiçador (improvisado 1) + mod(+3) = 4 contra couraça 10 ⇒ 0
    force_roll(20)
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

    # o Vulto NÃO tem slot de pega — a criatura de verdade não segura nada
    check("criatura sem `mao` nem `pega` não tem slot de pega",
          motor.fisica.grasp_slot_of(vulto) is None)

    # um corpo COM mão e COM parte armada: a escolha explícita vence
    f_t = char_folder(TORVIN)
    fm_t, body_t = motor.read_doc(f_t / "character.md")
    fm_t["body"] = {**validator.DEFAULT_BODY,
                    "unhas": {"capacidade": 0,
                              "weapon": {"damage": 9, "attribute": "STR"}}}
    motor.write_doc(f_t / "character.md", fm_t, body_t)
    fixar_parte("unhas")

    attach(TORVIN, ESPADA, motor.HAND_SLOT)
    force_roll(15)
    set_status(ELGA, hp=90)
    out_espada = attack(TORVIN, ELGA, ESPADA)
    check("com `arma` declarada vale a ESPADA (6+3 = 9), não a parte (9+3 = 12)",
          dano_de(out_espada) == 9 and parte_de(out_espada) is None,
          f"dano={dano_de(out_espada)} parte={parte_de(out_espada)}")

    force_roll(15)
    set_status(ELGA, hp=90)
    out_sem = attack(TORVIN, ELGA)       # espada na mão, mas não passada
    check("sem `arma`, mesmo com espada na mão, vale a PARTE (9+3 = 12)",
          dano_de(out_sem) == 12 and parte_de(out_sem) == "unhas",
          f"dano={dano_de(out_sem)} parte={parte_de(out_sem)}")

    attach(TORVIN, ATICADOR, motor.HAND_SLOT)
    force_roll(15)
    set_status(ELGA, hp=90)
    out_pedra = attack(TORVIN, ELGA, ATICADOR)
    check("item SEM bloco `weapon` vale IMPROVISADO (1+3 = 4), nunca a parte",
          dano_de(out_pedra) == 4 and parte_de(out_pedra) is None,
          f"dano={dano_de(out_pedra)} parte={parte_de(out_pedra)}")

    print("\n--- a fronteira: o NÚMERO não desce à Mente ----------------------")

    ctx = motor.get_context(VULTO)
    corpo = ctx["self"]["physics"]["body"]
    import json as _json
    bruto = _json.dumps(ctx, ensure_ascii=False)
    check("o `body` que desce marca a parte como arma, sem o dano",
          corpo["garras"] == {"capacidade": 0, "weapon": True},
          f"{corpo.get('garras')}")
    check("o `body` que desce marca a parte que protege, sem a proteção",
          corpo["dorso"].get("armor") is True and "protection" not in bruto,
          f"{corpo.get('dorso')}")
    check("slot de valor inteiro cru passa intacto", corpo["cabeca"] == 1)
    check("nenhum número de combate no contexto inteiro",
          '"damage"' not in bruto and '"protection"' not in bruto)

    print("\n--- validador: uma via só, e é a do corpo ------------------------")

    base = {"type": "character", "id": "x", "name": "X", "controlled_by": "none",
            "attributes": {a: 10 for a in ("STR", "DEX", "CON", "INT", "WIS", "CHA")},
            "status": {"hp": 10, "hp_max": 10}}

    def com(**extra):
        fm = dict(base)
        fm.update(extra)
        return validator.validate(fm)

    topo = com(weapon={"damage": 12, "attribute": "STR"})
    check("`weapon` NO TOPO do personagem é RECUSADO (a via morta não volta)",
          bool(topo) and "body.garras.weapon" in topo[0], f"{topo}")
    check("`armor` NO TOPO do personagem é RECUSADO",
          any("não vale no topo" in e for e in com(armor={"protection": 8})))

    parcial = com(body={"garras": {"capacidade": 0, "weapon": {"damage": 12}}})
    check("parte com `weapon` parcial é recusada, apontando a PARTE exata",
          bool(parcial) and "body.garras.weapon" in parcial[0], f"{parcial}")
    check("parte com `weapon.damage` < 1 é recusada",
          any("body.garras.weapon.damage" in e for e in com(
              body={"garras": {"capacidade": 0,
                               "weapon": {"damage": 0, "attribute": "STR"}}})))
    check("parte com `weapon.attribute` inválido é recusada",
          any("body.garras.weapon.attribute" in e for e in com(
              body={"garras": {"capacidade": 0,
                               "weapon": {"damage": 5, "attribute": "CON"}}})))
    check("parte com `armor` e SEM `wearable` é ACEITA (a pele não se veste)",
          com(body={"dorso": {"capacidade": 1, "armor": {"protection": 8}}}) == [])
    # `capacidade` conta PEÇAS VESTÍVEIS, não anatomia: uma parte que só golpeia não
    # veste nada, e exigir o campo dela era ruído puro.
    check("parte SEM `capacidade` é ACEITA (o campo é opcional, ausente vale 0)",
          com(body={"garras": {"weapon": {"damage": 9, "attribute": "STR"}}}) == [],
          f"{com(body={'garras': {'weapon': {'damage': 9, 'attribute': 'STR'}}})}")
    check("`capacidade` ausente vale 0 na leitura, e a parte não segura nada",
          motor.fisica.slot_capacity(
              {"body": {"garras": {"weapon": {"damage": 9, "attribute": "STR"}}}},
              "garras") == 0)
    check("`capacidade` TORTA continua recusada quando presente",
          any("capacidade" in e for e in com(
              body={"garras": {"capacidade": -1,
                               "weapon": {"damage": 9, "attribute": "STR"}}})))
    # membro que se conta vai SEPARADO — não há campo de quantidade, e não precisa
    dois = {"garra_esquerda": {"weapon": {"damage": 9, "attribute": "STR"}},
            "garra_direita": {"weapon": {"damage": 9, "attribute": "STR"}}}
    check("duas garras SEPARADAS são duas partes armadas (o sorteio ganha saídas)",
          com(body=dois) == []
          and [s for s, _d, _a in motor.natural_weapons_of({"body": dois})]
              == ["garra_esquerda", "garra_direita"])
    check("parte com `armor.protection` negativa é recusada",
          any("body.dorso.armor.protection" in e for e in com(
              body={"dorso": {"capacidade": 1, "armor": {"protection": -1}}})))
    check("corpo bem declarado passa",
          com(body={"garras": {"capacidade": 0,
                               "weapon": {"damage": 12, "attribute": "STR"}},
                    "dorso": {"capacidade": 1, "armor": {"protection": 8}}}) == [])

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
        {"target": VULTO, "path": "body.garras.weapon.damage", "value": 99}]))
    # `applied` NUNCA vem vazio: `_ensure_actor_touched` (FR-014, spec 020) grava
    # `status.action` quando nada mais tocou o ator. A asserção precisa ser sobre a
    # AUSÊNCIA da mutação pedida, não sobre a lista estar vazia.
    aplicou = any(a.get("path", "").startswith("body.")
                  for a in out_mut.get("applied") or [] if isinstance(a, dict))
    check("mutar o dano da parte em jogo é RECUSADO (só `status.*` é mutável)",
          not aplicou and bool(out_mut.get("rejected")),
          f"applied={out_mut.get('applied')}")
    check("a garra continua valendo 12 depois da tentativa",
          motor.natural_weapons_of(char_fm(VULTO))[0] == ("garras", 12, "STR"))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 68 (spec 068) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
