"""Sondagem exploratória da spec 068 — o corpo que luta.

NÃO é teste de aceitação (isso é `selftest_phase68.py`). É o passo 4 da
`loreforge-implement-review`: atacar a feature de todos os ângulos até ela revelar
o que ninguém desenhou.

Roda contra uma CÓPIA do mundo REAL (o layout do fixture != o do real), em tmp —
`world/` é o save do jogador e jamais é mutado por isto.

Uso:  python3 tests/exploracao/sondagem_corpo_que_luta.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2]
REAL_WORLD = Path(os.environ.get("LOREFORGE_WORLD_REAL",
                                 SERVER_DIR.parent / "loreforge-world" / "tardenia"))

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-sonda-068-"))
shutil.copytree(REAL_WORLD, _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))

import motor  # noqa: E402
import validator  # noqa: E402

BICHO = "rastejante-das-galerias"
HESPER = "hesper-ferreiro-itinerante"

ACHADOS: list[tuple[str, str, str]] = []


def achado(tipo: str, titulo: str, detalhe: str) -> None:
    ACHADOS.append((tipo, titulo, detalhe))
    print(f"\n  [{tipo.upper()}] {titulo}\n      {detalhe}")


def obs(txt: str) -> None:
    print(f"      · {txt}")


def force_roll(v):
    motor._roll_d20 = lambda: v


def res(**parts):
    base = {"narrative_hint": "a cena se move", "movement": None, "mutations": [],
            "item_transfers": [], "equip_ops": [], "lock_ops": [], "persuade_ops": [],
            "attack_ops": [], "memories": []}
    base.update(parts)
    return base


def atacar(ator, alvo, arma=None, vantagem=5):
    return motor.apply_resolution(ator, res(
        attack_ops=[{"alvo": alvo, "arma": arma, "vantagem": vantagem}]))


def folder(cid):
    return motor.find_character_folder(cid)


def fm_de(cid):
    fm, _ = motor.read_doc(folder(cid) / "character.md")
    return fm


def status(cid):
    return fm_de(cid).get("status") or {}


def set_status(cid, **campos):
    f = folder(cid)
    fm, body = motor.read_doc(f / "character.md")
    st = dict(fm.get("status") or {})
    st.update(campos)
    fm["status"] = st
    motor.write_doc(f / "character.md", fm, body)


def dano(out):
    ap = out.get("attack_ops_applied") or []
    return ap[0]["dano"] if ap else None


def regras(out):
    return {r.get("regra") for r in out.get("rejected") or [] if isinstance(r, dict)}


try:
    print("=" * 74)
    print("SONDAGEM 068 — o corpo que luta (mundo REAL copiado para tmp)")
    print("=" * 74)

    bicho = fm_de(BICHO)
    print(f"\nCriatura: {bicho['name']} | STR {bicho['attributes']['STR']} "
          f"| garra {motor.weapon_of(bicho)} | couraça {motor.protection_of(folder(BICHO))} "
          f"| hp {status(BICHO).get('hp')} | {bicho.get('weight_kg')} kg")

    # ---- LENTE: o protagonista de ponta a ponta -------------------------- #
    print("\n\n--- LENTE 1: o protagonista submetido a tudo ---------------------")

    # 1. o corpo herdado
    corpo = motor.fisica.body_of(bicho)
    pega = motor.fisica.grasp_slot_of(bicho)
    tem_body_proprio = "body" in bicho
    obs(f"declara `body` próprio? {tem_body_proprio} | slot de pega: {pega}")
    obs(f"slots herdados: {sorted(corpo)}")
    if not tem_body_proprio and pega == "mao":
        achado("lacuna",
               "criatura com arma natural herda o CORPO HUMANO se não declarar `body`",
               "Um bicho rastejante de placas tem `mao`, `dedo` (10), `cabeca`, "
               "`torso`... Pode empunhar espada e vestir chapéu. A spec 068 deu a ele "
               "a garra, mas não o corpo — e as duas coisas andam juntas: quem tem "
               "arma natural quase sempre NÃO tem mãos. A 019 já resolve (basta "
               "declarar `body`), mas nada LIGA as duas specs, e o autor não é "
               "avisado.")

    # 2. golpe da criatura contra um humano
    force_roll(14)
    hp0 = status(HESPER).get("hp")
    out = atacar(BICHO, HESPER)
    obs(f"garra contra Hesper: dano {dano(out)} (hp {hp0} -> {status(HESPER).get('hp')})")

    # 3. o humano revida... não pode. Mas pode atacar por vontade própria.
    force_roll(18)
    hp_bicho = status(BICHO).get("hp")
    out_leve = atacar(HESPER, BICHO)          # desarmado: improvisado 1
    obs(f"Hesper desarmado contra a couraça: {regras(out_leve) or 'passou'} "
        f"(hp do bicho {hp_bicho} -> {status(BICHO).get('hp')})")
    if "golpe_absorvido" in regras(out_leve):
        achado("confirmacao",
               "a couraça natural transforma o golpe fraco em `golpe_absorvido`",
               "E não em `ataque_errou` — a distinção que a FR-008 exigia sobrevive "
               "quando a absorção vem da PELE, não de peça vestida. É o material que "
               "A Mente precisa para narrar 'ressoou nas placas' em vez de 'errei'.")

    # ---- LENTE: extremos e degenerados ----------------------------------- #
    print("\n\n--- LENTE 2: extremos e degenerados ------------------------------")

    # couraça vs. arma pesada de verdade
    for base_dano, rotulo in ((6, "espada (6)"), (10, "arma pesada (10)")):
        alvo_fm = fm_de(BICHO)
        mod = motor.rolagem.attr_modifier(fm_de(HESPER)["attributes"]["STR"])
        liquido = max(0, base_dano + mod - motor.protection_of(folder(BICHO)))
        obs(f"{rotulo}: {base_dano} + mod({mod}) − couraça(6) = {liquido} de dano")

    # o bicho é 900 kg: dá para carregá-lo?
    cap_h = motor.fisica.push_capacity(fm_de(HESPER))
    peso_b = fm_de(BICHO).get("weight_kg")
    obs(f"empurrar: capacidade de Hesper {cap_h} kg vs. {peso_b} kg do bicho")
    if peso_b > cap_h * 4:
        achado("confirmacao",
               "o peso da criatura a torna inarrastável, sem regra nova",
               f"{peso_b} kg contra capacidade de {cap_h} kg: `carry`/`push` recusam "
               "pela física que já existia. Nenhum caso especial de 'monstro' foi "
               "preciso — `weight_kg` já dava conta.")

    # couraça absurda: satura?
    f = folder(BICHO)
    fm, body = motor.read_doc(f / "character.md")
    fm["armor"] = {"protection": 99}
    motor.write_doc(f / "character.md", fm, body)
    force_roll(20)
    out_abs = atacar(HESPER, BICHO)
    obs(f"couraça 99: {regras(out_abs) or 'passou'} — protection_of = "
        f"{motor.protection_of(f)}")
    achado("calibragem",
           "não há TETO para a couraça natural: 99 torna a criatura invulnerável",
           "Nenhuma arma do mundo fura, e o resultado é `golpe_absorvido` para "
           "sempre — combate que não pode ser vencido, sem o mundo avisar ninguém. "
           "O validador só exige `>= 0`. Mesma questão vale para `weapon.damage`: "
           "não há teto, e uma garra 999 mata qualquer um de um golpe.")
    fm["armor"] = {"protection": 6}
    motor.write_doc(f / "character.md", fm, body)

    # couraça 0 declarada: é diferente de ausente?
    fm["armor"] = {"protection": 0}
    motor.write_doc(f / "character.md", fm, body)
    obs(f"couraça 0 DECLARADA: protection_of = {motor.protection_of(f)} "
        "(idêntico a ausente — nenhuma semântica extra)")
    fm["armor"] = {"protection": 6}
    motor.write_doc(f / "character.md", fm, body)

    # ---- LENTE: o adversário --------------------------------------------- #
    print("\n\n--- LENTE 3: o adversário ----------------------------------------")

    # golpear quem já caiu: mata sem dado (zona determinística preservada?)
    set_status(HESPER, hp=1)
    force_roll(20)
    atacar(BICHO, HESPER)
    cond = status(HESPER).get("conditions") or []
    obs(f"Hesper após a garra: hp {status(HESPER).get('hp')} conditions {cond}")
    if "incapacitado" in cond:
        set_status(HESPER, hp=0)
        out_exec = atacar(BICHO, HESPER)
        cond2 = status(HESPER).get("conditions") or []
        obs(f"golpe no caído: {cond2} | deliberado="
            f"{(out_exec.get('attack_ops_applied') or [{}])[0].get('deliberado')}")
        if "morto" in cond2:
            achado("confirmacao",
                   "a zona determinística sobreviveu à arma natural",
                   "Garra contra alguém caído MATA sem dado, com `deliberado: True`, "
                   "igual a qualquer arma. A spec 068 mudou o número, não o rito — "
                   "que era exatamente a promessa da FR-003.")

    # a criatura ataca a si mesma
    out_self = atacar(BICHO, BICHO)
    obs(f"criatura atacando a si mesma: {regras(out_self) or out_self.get('rejected')}")

    # ---- LENTE: silêncio e assimetria ------------------------------------ #
    print("\n\n--- LENTE 4: os dois lados da relação ----------------------------")

    from motor.memoria import primitivas as MP
    s_bicho_hesper = MP.sentiment_toward(BICHO, HESPER)
    s_hesper_bicho = MP.sentiment_toward(HESPER, BICHO)
    obs(f"afeto do bicho por Hesper: {s_bicho_hesper}")
    obs(f"afeto de Hesper pelo bicho: {s_hesper_bicho}")
    if s_hesper_bicho < 0 and s_bicho_hesper >= 0:
        achado("confirmacao",
               "a assimetria de rancor funciona com criatura",
               "Quem apanhou guarda mágoa; quem golpeou não guarda nada contra a "
               "vítima. A memória de combate não precisou saber que o agressor é um "
               "bicho — `_record_attack` grava dos dois lados pelo mesmo caminho.")

    # ---- LENTE: a negação como conteúdo ---------------------------------- #
    print("\n\n--- LENTE 5: as recusas são narráveis? ---------------------------")
    todas = regras(out_leve) | regras(out_abs) | regras(out_self)
    for regra in sorted(str(r) for r in todas):
        obs(f"regra emitida: {regra}")
    if None in todas:
        cru = [r for r in out_self.get("rejected") or []
               if isinstance(r, dict) and "regra" not in r]
        achado("lacuna",
               "rejeição de auto-ataque sai SEM chave `regra` (defeito pré-existente)",
               f"{cru} — todas as outras recusas de combate passam por `_rejection`/"
               "`_fail` e carregam `regra`, que é o que o client traduz em frase "
               "in-world. Esta sai só com `why` em português cru. NÃO é da 068 (é da "
               "008), e só é alcançável pelo fallback de texto — o corpo da tool "
               "barra o auto-ataque antes, com `ctx.err`. Mas é um silêncio sem causa "
               "esperando um caminho.")

    # ---- LENTE: combinação cruzada --------------------------------------- #
    print("\n\n--- LENTE 6: a feature nova × as antigas -------------------------")

    # o bicho está morto? butcher lê a prosa dele
    set_status(BICHO, hp=0, conditions=["morto"])
    obs("criatura marcada como morta — `butcher` leria a prosa de um bicho de placas")
    achado("lacuna",
           "`butcher` julga a criatura por régua escrita para corpo de gente",
           "As réguas de esquartejabilidade e rendimento vão ler 'placas "
           "sobrepostas, cinzenta como o minério' e decidir quanta CARNE sai daí. "
           "Não é erro da 068 — mas é a primeira vez que o mundo tem um corpo que "
           "não é humano, e a régua nunca viu um. Precisa de medição com o modelo "
           "real, não de suposição.")

    print("\n" + "=" * 74)
    print(f"{len(ACHADOS)} achado(s)")
    for tipo, titulo, _ in ACHADOS:
        print(f"  [{tipo:12}] {titulo}")
    print("=" * 74)
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
