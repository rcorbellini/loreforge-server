"""Auto-teste da Fase 69 — O revide involuntário (spec 069).

Quem apanha devolve o golpe, no mesmo turno, sem que ninguém decida por ele. A
nota de PRONTIDÃO é gate e vantagem ao mesmo tempo (0 = não revidou), e viaja na
MESMA chamada ao modelo que já apurava a vantagem.

Cobre:
  - US1: nota > 0 e alvo de pé ⇒ contra-golpe no mesmo turno, com a PARTE relatada
  - US2: os portões (nota 0, caiu, morto, caído, descansando, ocupado, a trava)
  - US3: memória dos dois lados com o REVIDANTE como autor, e a valência que NÃO
    condena quem se defendeu — nem no rancor da vítima, nem no leque da plateia
  - RECURSÃO: dois que revidariam se atacam e o turno TERMINA (profundidade 1)
  - a régua-mãe: duas notas de UMA resposta JSON, com default por campo

Cenário: Vulto (STR 22 ⇒ mod +6; garra 12/STR e fauces 4/STR; DEX 12 ⇒ defesa 11),
Torvin (STR 16 ⇒ mod +3; DEX 8 ⇒ defesa 9) e Elga (a plateia sem história).

Uso:  python3 server/selftest_phase69.py
"""

from __future__ import annotations

import json
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

# As criaturas nascem AQUI, na cópia temporária — nunca em `tests/world/`, que é
# compartilhado por 45+ fases e cuja contagem de cena outras fases afirmam (lição
# medida na spec 068).
def _escreve(pasta: str, corpo: str) -> None:
    d = _tmp / "world" / "taverna-do-gancho" / pasta
    d.mkdir(parents=True)
    (d / "character.md").write_text(corpo, encoding="utf-8")


_escreve("vulto-das-escamas", """\
---
type: character
id: vulto-das-escamas
name: Vulto das Escamas
controlled_by: none
weight_kg: 2200
attributes: {STR: 22, DEX: 12, CON: 20, INT: 8, WIS: 13, CHA: 6}
status: {hp: 180, hp_max: 180, fatigue: descansado, conditions: []}
body:
  cabeca: 1
  garras: {weapon: {damage: 12, attribute: STR}}
  fauces: {weapon: {damage: 4, attribute: STR}}
  dorso: {capacidade: 1}
origin: editorial
---

O Vulto não divide a pedra com nada que respire. O que entra é intruso.
""")

_escreve("moura-serena", """\
---
type: character
id: moura-serena
name: Moura, a Serena
controlled_by: none
weight_kg: 62
attributes: {STR: 9, DEX: 12, CON: 11, INT: 14, WIS: 16, CHA: 13}
status: {hp: 60, hp_max: 60, fatigue: descansado, conditions: []}
origin: editorial
---

Moura atende quem chega ferido e nunca ergueu a mão contra ninguém.
""")

sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402

FAILS = []

VULTO, TORVIN, ELGA = "vulto-das-escamas", "torvin-ferreiro", "elga-taverneira"
MOURA = "moura-serena"


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def force_roll(value):
    motor._roll_d20 = lambda: value


def fixar_parte(slot):
    motor.fisica.primitivas._escolher_parte = \
        lambda armadas: next(a for a in armadas if a[0] == slot)


def res(**parts):
    base = {"narrative_hint": "avança para o golpe", "movement": None,
            "mutations": [], "item_transfers": [], "equip_ops": [],
            "lock_ops": [], "persuade_ops": [], "attack_ops": [], "memories": []}
    base.update(parts)
    return base


def golpe(ator, alvo, revide=0, arma=None, vantagem=5):
    return motor.apply_resolution(ator, res(attack_ops=[
        {"alvo": alvo, "arma": arma, "vantagem": vantagem, "revide_nota": revide}]))


def folder(cid) -> Path:
    return motor.find_character_folder(cid)


def fm_de(cid) -> dict:
    fm, _ = motor.read_doc(folder(cid) / "character.md")
    return fm


def status(cid) -> dict:
    return fm_de(cid).get("status") or {}


def set_status(cid, **campos):
    f = folder(cid)
    fm, body = motor.read_doc(f / "character.md")
    st = dict(fm.get("status") or {})
    st.update(campos)
    fm["status"] = st
    motor.write_doc(f / "character.md", fm, body)


def aplicados(out) -> list:
    return out.get("attack_ops_applied") or []


def contra(out) -> dict | None:
    """A op do CONTRA-GOLPE, se houve."""
    return next((a for a in aplicados(out) if a.get("revide")), None)


def memorias(cid) -> list:
    saida = []
    d = folder(cid) / "memories"
    for md in (sorted(d.glob("mem-*.md")) if d.exists() else []):
        fm, _ = motor.read_doc(md)
        saida.append(fm)
    return saida


try:
    print("\n--- a régua-mãe: duas notas, UMA resposta ------------------------")

    from motor.combate import declaracao as D
    check("REGUA_GOLPE compõe os dois eixos e pede JSON com as duas chaves",
          "vantagem" in D.REGUA_GOLPE and "PRONTIDÃO" in D.REGUA_GOLPE
          and '"vantagem"' in D.REGUA_GOLPE and '"revide"' in D.REGUA_GOLPE)
    check("ToolSpec.juizo de `attack` declara os DOIS eixos (o descarte de nota "
          "vinda de fora é por laço, então cobre os dois)",
          [p for p, _r in D.ATTACK.juizo] == ["vantagem", "revide"],
          f"{[p for p, _r in D.ATTACK.juizo]}")
    j = motor.juizo.julgamento('{"vantagem": 7, "revide": 3}',
                               {"vantagem": 5, "revide": 0})
    check("as duas notas saem de UMA resposta", j == {"vantagem": 7, "revide": 3})
    # SUPERSEDIDO PELA SPEC 071, e o INTENTO fica mais forte, não mais fraco: a
    # preocupação aqui era "revide 0 nunca inventa violência" numa resposta
    # ilegível. Agora não há resposta nenhuma a interpretar — a capacidade RECUSA,
    # e o revide involuntário simplesmente não acontece. Zero violência inventada
    # continua garantido, por um caminho mais curto.
    try:
        motor.juizo.julgamento("blá", {"vantagem": 5, "revide": 0})
        check("resposta ilegível é FALHA — nenhum revide é sequer avaliado "
              "(spec 071)", False, "não levantou")
    except motor.juizo.NaoJulgado:
        check("resposta ilegível é FALHA — nenhum revide é sequer avaliado "
              "(spec 071)", True)

    print("\n--- US1: quem está pronto devolve o golpe ------------------------")

    fixar_parte("garras")
    force_roll(15)
    hp0 = status(TORVIN).get("hp")
    out = golpe(TORVIN, VULTO, revide=8)
    c = contra(out)
    check("nota alta ⇒ contra-golpe resolvido no MESMO turno",
          c is not None, f"{aplicados(out)}")
    check("o contra-golpe mira o AGRESSOR",
          c and c.get("alvo") == TORVIN, f"{c}")
    check("o dano do contra-golpe é o da garra: 12 + mod(STR 22 = +6) = 18",
          c and c.get("dano") == 18, f"dano={c and c.get('dano')}")
    check("o agressor perdeu hp de verdade",
          status(TORVIN).get("hp") == hp0 - 18,
          f"{hp0} -> {status(TORVIN).get('hp')}")
    check("o contra-golpe RELATA a parte que reagiu (FR-004a)",
          c and c.get("parte") == "garras", f"parte={c and c.get('parte')}")
    check("a rolagem do contra-golpe sobe em `rolls`, com o revidante como autor",
          any(r.get("personagem") == VULTO and r.get("alvo") == TORVIN
              for r in out.get("rolls") or []))

    # a parte VARIA: fixando a outra, o dano muda
    fixar_parte("fauces")
    force_roll(15)
    set_status(TORVIN, hp=120)
    c2 = contra(golpe(TORVIN, VULTO, revide=8))
    check("outra parte reage ⇒ outro dano (fauces 4+6 = 10)",
          c2 and c2.get("parte") == "fauces" and c2.get("dano") == 10,
          f"{c2}")

    print("\n--- US2: quem não está pronto apanha calado ----------------------")

    fixar_parte("garras")
    force_roll(15)
    set_status(TORVIN, hp=120)
    check("nota 0 ⇒ NENHUM contra-golpe",
          contra(golpe(TORVIN, VULTO, revide=0)) is None)
    check("e o agressor sai ileso", status(TORVIN).get("hp") == 120)

    # caiu NESTE golpe: não revida. Torvin desarmado vale improvisado 1 + mod(STR 16
    # = +3) = 4 de dano, então hp 4 é exatamente o que ZERA — e zerar é o que faz
    # `derrota` nascer. (hp 5 deixaria 1, e aí o Vulto revidaria com toda a razão.)
    set_status(VULTO, hp=4, conditions=[])
    set_status(TORVIN, hp=120)
    force_roll(20)
    out_caiu = golpe(TORVIN, VULTO, revide=10)
    caiu_op = next((a for a in aplicados(out_caiu) if not a.get("revide")), {})
    check("o cenário de fato derrubou o alvo (guarda do próprio teste)",
          caiu_op.get("hp_restante") == 0 and caiu_op.get("derrota"),
          f"{caiu_op}")
    check("quem CAIU neste golpe não revida",
          contra(out_caiu) is None and status(TORVIN).get("hp") == 120,
          f"{aplicados(out_caiu)}")

    # já caído / morto
    set_status(VULTO, hp=0, conditions=["incapacitado"])
    set_status(TORVIN, hp=120)
    force_roll(20)
    check("alvo JÁ CAÍDO não revida (e o golpe o mata sem dado)",
          contra(golpe(TORVIN, VULTO, revide=10)) is None)

    set_status(VULTO, hp=180, conditions=[])

    # descansando
    set_status(VULTO, descansando_desde=1)
    set_status(TORVIN, hp=120)
    force_roll(15)
    check("alvo DESCANSANDO não revida",
          contra(golpe(TORVIN, VULTO, revide=10)) is None)
    f_v = folder(VULTO)
    fm_v, body_v = motor.read_doc(f_v / "character.md")
    st = dict(fm_v.get("status") or {})
    st.pop("descansando_desde", None)
    fm_v["status"] = st
    motor.write_doc(f_v / "character.md", fm_v, body_v)

    # o golpe que ERRA e o ABSORVIDO ainda provocam
    set_status(TORVIN, hp=120)
    force_roll(1)                      # 1 + 3 = 4 < defesa 11 do Vulto
    out_erro = golpe(TORVIN, VULTO, revide=8)
    check("golpe que ERRA ainda provoca revide (a lâmina passou perto)",
          contra(out_erro) is not None,
          f"{[r.get('regra') for r in out_erro.get('rejected') or []]}")

    print("\n--- US3: o rastro — defender-se não é agredir --------------------")

    # cena limpa para medir a memória
    for cid in (TORVIN, VULTO):
        d = folder(cid) / "memories"
        if d.exists():
            shutil.rmtree(d)
    d_elga = folder(ELGA) / "memories"
    if d_elga.exists():
        shutil.rmtree(d_elga)

    fixar_parte("garras")
    force_roll(15)
    set_status(TORVIN, hp=120)
    set_status(VULTO, hp=180, conditions=[])
    golpe(TORVIN, VULTO, revide=8)

    mem_v = memorias(VULTO)
    mem_t = memorias(TORVIN)
    mem_e = memorias(ELGA)

    check("o REVIDANTE é o autor da memória do contra-golpe",
          any("Golpeei" in str(m.get("summary")) and "garras" in str(m.get("summary"))
              for m in mem_v),
          f"{[m.get('summary') for m in mem_v]}")
    check("o AGRESSOR lembra de ter apanhado (senão narraria vitória que não houve)",
          any("me golpeou" in str(m.get("summary")) for m in mem_t),
          f"{[m.get('summary') for m in mem_t]}")

    apanhou = next((m for m in mem_t if "me golpeou" in str(m.get("summary"))), {})
    val_ap = apanhou.get("valence") or {}
    check("o agressor NÃO guarda rancor de quem se defendeu (FR-009a)",
          VULTO not in val_ap, f"valence={val_ap}")
    check("mas o LUGAR fica ruim para ele (isso independe de quem teve razão)",
          any(v == "negativa" for k, v in val_ap.items() if k != VULTO),
          f"valence={val_ap}")

    agredido = next((m for m in memorias(VULTO)
                     if "me golpeou" in str(m.get("summary"))), {})
    check("a AGRESSÃO original segue condenada: o Vulto guarda rancor de Torvin",
          (agredido.get("valence") or {}).get(TORVIN) == "negativa",
          f"{agredido.get('valence')}")

    # o leque: Elga não tem história com Torvin ⇒ banda neutra ⇒ sem valência
    w_defesa = [m for m in mem_e
                if m.get("evento") == "witness_attack"
                and str(m.get("summary", "")).startswith("Vi Vulto")]
    w_agressao = [m for m in mem_e
                  if m.get("evento") == "witness_attack"
                  and "golpear Vulto" in str(m.get("summary", ""))]
    check("a plateia CONDENA a agressão original",
          w_agressao and (w_agressao[0].get("valence") or {}).get(TORVIN)
          == "negativa", f"{[m.get('valence') for m in w_agressao]}")
    check("a plateia NÃO condena quem se defendeu — estranho fica na banda neutra "
          "(FR-009b, e é o fim da lavagem de culpa)",
          w_defesa and not (w_defesa[0].get("valence") or {}),
          f"{[m.get('valence') for m in w_defesa]}")

    print("\n--- a RECURSÃO: dois que revidariam ------------------------------")

    # Moura não tem parte armada nem arma: revida por improvisado. O que importa
    # aqui não é o dano, é o turno TERMINAR.
    set_status(TORVIN, hp=120)
    set_status(MOURA, hp=60, conditions=[])
    force_roll(15)
    out_r = golpe(MOURA, TORVIN, revide=10)   # Moura ataca, Torvin revidaria
    contras = [a for a in aplicados(out_r) if a.get("revide")]
    check("o turno TERMINA, com profundidade 1 — um contra-golpe, e só um",
          len(contras) <= 1, f"{len(contras)} contra-golpes")
    check("o contra-golpe NÃO gera um terceiro golpe (a trava `revide`)",
          all(not a.get("revide") or a.get("alvo") == MOURA
              for a in aplicados(out_r)), f"{aplicados(out_r)}")
    check("o mundo continua íntegro (as duas fichas existem e são legíveis)",
          bool(fm_de(MOURA)) and bool(fm_de(TORVIN)))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 69 (spec 069) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
