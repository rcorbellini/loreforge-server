"""Auto-teste da Fase 7 — Equipamentos, Partes do Corpo e Física (spec 004).

Cobre os cenários do quickstart da spec 004 (§1, 1–19), sem LLM real:
  - Validator: régua de tamanho, wearable, container (parcial inválida,
    max_size ≤ size), state.slot
  - Física derivada: peso efetivo recursivo, capacidades por STR, portador final
  - US1 equip: vestir com state.slot; slot_ocupado com motivo estruturado
  - US2 take/give/stow/drop: encaixe, vaga, mãos, carga (agregada), visibilidade
    (guardado some do contexto de terceiros), cascata ao portador final, bypass
    de peso em destinos sem portador
  - US3 unequip/troca: nunca dois no slot; conteúdo intacto
  - US4 legado: mundo pré-004 tolerado + aviso de migração
  - US5 shove: empurrar o que não se carried_item_ids; peso_excede_empurrar
  - Pipeline único: a MESMA violação produz o MESMO {regra, valores} pela guarda
    de tools e pelo caminho clássico (fallback JSON → Motor)

Roda sobre uma CÓPIA temporária do mundo de teste. Uso:  python3 server/selftest_phase7.py
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
import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import selftest_helpers  # noqa: E402
import motor  # noqa: E402
import validator  # noqa: E402

# spec 006: o empurrar na zona intermediária rola dado — fixa em 20 para manter
# esta fase determinística (a rolagem em si é coberta pela fase 9).
motor._roll_d20 = lambda: 20

FAILS = []
TAVERNA = None  # definido após o setup


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def res(actor=None, **parts):
    base = {"narrative_hint": parts.pop("hint", "faz o que pretendia"),
            "movement": None, "mutations": [], "item_transfers": [],
            "equip_ops": [], "memories": []}
    base.update(parts)
    return base


INTENT = {"action": "interage com o que está por perto", "target": None,
          "utterance": None, "movement": None, "note": ""}

_SYSTEM_TERMS = ("slot", "state", "regra", "max_size", "json", "frontmatter")


def sem_termos_de_sistema(texto: str) -> bool:
    low = (texto or "").lower()
    return not any(t in low for t in _SYSTEM_TERMS)


try:
    TAVERNA = motor.WORLD_DIR / "taverna-do-gancho"
    TORVIN = TAVERNA / "torvin-ferreiro"

    # ===================== Foundational (cenários 1, 2, 19) ================== #
    check("mundo-fixture íntegro no boot", motor.validate_world() == [],
          str(motor.validate_world()))

    err_parcial = validator.validate({"type": "item", "id": "x", "name": "X",
                                      "container": {"max_size": "PP"}})
    check("1: container parcial (só max_size) rejeitado com motivo",
          any("max_items" in e for e in err_parcial))
    # spec 019: vocabulário de slot ABERTO — um nome arbitrário ("cauda") PASSA;
    # só a FORMA inválida (slot vazio/ausente) é reprovada.
    err_slot_livre = validator.validate({"type": "item", "id": "x", "name": "X",
                                         "wearable": {"slot": "cauda"}})
    check("2a: wearable.slot de nome livre é aceito (vocab aberto, spec 019)",
          not any("wearable.slot" in e for e in err_slot_livre))
    err_slot_vazio = validator.validate({"type": "item", "id": "x", "name": "X",
                                         "wearable": {"slot": ""}})
    check("2a': wearable.slot vazio rejeitado (forma)",
          any("wearable.slot" in e for e in err_slot_vazio))
    err_size = validator.validate({"type": "item", "id": "x", "name": "X",
                                   "size": "GG"})
    check("2b: size fora da régua rejeitado", any("'size'" in e for e in err_size))
    err_maior = validator.validate({"type": "item", "id": "x", "name": "X",
                                    "size": "P",
                                    "container": {"max_size": "G", "max_items": 2}})
    check("19: max_size > size do próprio contêiner rejeitado",
          any("não pode exceder" in e for e in err_maior))
    # spec 019: state.slot de nome livre ("asa") é aceito; só forma inválida reprova
    check("state.slot de nome livre é aceito (vocab aberto, spec 019)",
          not any("state.slot" in e for e in validator.validate(
              {"type": "item", "id": "x", "name": "X", "state": {"slot": "asa"}})))
    check("state.slot vazio rejeitado (forma)",
          any("state.slot" in e for e in validator.validate(
              {"type": "item", "id": "x", "name": "X", "state": {"slot": ""}})))

    # física derivada
    torvin_fm, _ = motor.read_doc(TORVIN / "character.md")
    check("capacidades: carregar = STR×7 e empurrar = STR×14 (Torvin STR 16)",
          motor.carry_capacity(torvin_fm) == 112
          and motor.push_capacity(torvin_fm) == 224)
    bolsa = TORVIN / "bolsa-de-couro"
    check("peso efetivo recursivo (bolsa 0.3 + frasco legado 1.0 = 1.3)",
          abs(motor.effective_weight(bolsa) - 1.3) < 1e-6)
    check("portador final: frasco aninhado na bolsa → Torvin",
          motor.porter_of(bolsa / "frasco-de-oleo") == TORVIN)
    check("defaults legados: size ausente ⇒ P; peso ausente ⇒ padrão da classe",
          motor.item_size({}) == "P" and motor.item_own_weight({"size": "XG"}) == 100.0)

    # 14: legado tolerado + aviso de migração
    warns = motor.migration_warnings()
    check("14: item legado junto ao personagem vira AVISO de migração (não erro)",
          any(w["id"] == "bolsa-de-couro" for w in warns))
    fis0 = motor.get_context("torvin-ferreiro")["self"]["fisico"]
    check("14: segurado de cortesia não conta slots nem carga",
          fis0["peso_carregado_kg"] == 0.0 and fis0["maos_livres"] == 2)

    # ===================== US1 — equip (cenários 3, 4) ======================= #
    out = motor.apply_resolution("torvin-ferreiro", res(
        equip_ops=[{"op": "equip", "item": "calca-de-linho"}]))
    check("3: equip aplica — pasta no personagem e state.slot = pernas",
          out["equip_ops_applied"] == [{"op": "equip", "item": "calca-de-linho",
                                        "slot": "pernas"}]
          and (TORVIN / "calca-de-linho" / "item.md").exists())
    calca_fm, _ = motor.read_doc(TORVIN / "calca-de-linho" / "item.md")
    check("3: state.slot gravado no item", motor.item_slot(calca_fm) == "pernas")
    check("3: equipamento saiu do chão da taverna",
          not (TAVERNA / "calca-de-linho").exists())

    ctx = motor.get_context("torvin-ferreiro")
    captured = []
    r_guard = selftest_helpers.resolve_scripted(INTENT, ctx,
        [("equip", {"item": "calca-de-la"}),
         ("narrate", {"narrative_hint": "desiste de trocar de calça por ora"})],
        captured=captured)
    check("4: guarda nega 2ª calça com regra slot_ocupado + valores",
          captured[0].get("ok") is False
          and captured[0].get("regra") == "slot_ocupado"
          and captured[0].get("valores", {}).get("ocupantes") == ["calca-de-linho"])
    check("4: rejeição não corrigida vira tool_rejection estruturada",
          any(r.get("regra") == "slot_ocupado" for r in r_guard["tool_rejections"]))
    out4 = motor.apply_resolution("torvin-ferreiro", res(
        equip_ops=[{"op": "equip", "item": "calca-de-la"}]))
    check("4: Motor (autoritativo) nega igual — pipeline único guarda×Motor",
          out4["equip_ops_applied"] == []
          and any(r.get("regra") == "slot_ocupado" for r in out4["rejected"]))
    check("SC-002: hint de negação sem termos de sistema",
          sem_termos_de_sistema(r_guard["narrative_hint"]))

    # ===================== US2 — guardar/pegar (5–9, 13, 16, 18) ============ #
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "moeda-de-cobre", "to": "torvin-ferreiro"}]))
    moeda_fm, _ = motor.read_doc(TORVIN / "moeda-de-cobre" / "item.md")
    check("take: item pego vai para a mão (state.slot = mao)",
          motor.item_slot(moeda_fm) == "mao")
    out5 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "moeda-de-cobre", "to": "calca-de-linho"}]))
    check("5: stow moeda (PP) no bolso da calça vestida aplicado",
          out5["item_transfers_applied"] == [{"item": "moeda-de-cobre",
                                              "to": "calca-de-linho"}]
          and (TORVIN / "calca-de-linho" / "moeda-de-cobre" / "item.md").exists())
    moeda_fm2, _ = motor.read_doc(TORVIN / "calca-de-linho" / "moeda-de-cobre" / "item.md")
    check("5: guardado não tem state.slot", motor.item_slot(moeda_fm2) is None)

    # 5b — ITEM 44: `stow` SEM destino. Guardar é o gesto com que se libera a mão, e
    # exigir que A Mente escolha o contêiner é cobrar dela uma decisão que o corpo toma
    # sozinho. Medido em jogo: das 9 chamadas de `stow`, 3 morreram por não nomear
    # contêiner — duas omitindo o campo e uma chamando-o `to` (o nome que `give` e
    # `shove` usam para a mesma ideia).
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "seixo-preto", "to": "torvin-ferreiro"}]))
    cap5b = []
    selftest_helpers.resolve_scripted(INTENT, motor.get_context("torvin-ferreiro"),
                               [("stow", {"item": "seixo-preto"}),
                                ("narrate", {"narrative_hint": "guarda"})],
                               captured=cap5b)
    destino5b = (cap5b[0].get("aplicado") or {}).get("to")
    check("5b: `stow` sem destino ACHA a bolsa sozinho e tira o item da mão",
          cap5b[0].get("ok") is True and destino5b
          and (TORVIN / destino5b / "seixo-preto").is_dir()
          and "seixo-preto" not in (motor.slots_in_use(TORVIN).get("mao") or []),
          str(cap5b[0]))
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "seixo-preto", "to": "taverna-do-gancho"}]))

    ctx_elga = motor.get_context("elga-taverneira")
    torvin_vis = next(c for c in ctx_elga["characters_present"]
                      if c["id"] == "torvin-ferreiro")
    vis_ids = {i["id"] for i in torvin_vis["carrying"]}
    check("13: terceiros veem o vestido (calça), não o guardado (moeda)",
          "calca-de-linho" in vis_ids and "moeda-de-cobre" not in vis_ids)
    try:
        motor.observe_entity("elga-taverneira", "moeda-de-cobre")
        vazou = True
    except motor.MotorError:
        vazou = False
    check("13: observar o que está no bolso alheio é negado", not vazou)

    # 6 + 16: mesma violação, mesmo {regra} pela guarda e pelo caminho clássico
    ctx = motor.get_context("torvin-ferreiro")
    cap6 = []
    selftest_helpers.resolve_scripted(INTENT, ctx,
        [("stow", {"item": "aticador-de-ferro", "container": "calca-de-linho"}),
         ("narrate", {"narrative_hint": "o atiçador não passa da boca do bolso"})],
        captured=cap6)
    out6 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "aticador-de-ferro", "to": "calca-de-linho"}]))
    rej6 = [r for r in out6["rejected"] if r.get("regra")]
    check("6: atiçador (M) no bolso (PP) negado — tamanho_excede_container",
          cap6[0].get("regra") == "tamanho_excede_container"
          and cap6[0].get("valores", {}).get("max_size") == "PP")
    check("16: pipeline único — guarda e Motor devolvem a MESMA regra",
          rej6 and rej6[0]["regra"] == cap6[0]["regra"]
          and rej6[0]["valores"]["max_size"] == cap6[0]["valores"]["max_size"])

    # 7: quantidade máxima (calça: 4; moeda já dentro)
    for extra in ("botao-de-osso", "agulha-de-ferro", "seixo-branco"):
        motor.apply_resolution("torvin-ferreiro", res(
            item_transfers=[{"item": extra, "to": "calca-de-linho"}]))
    check("7-pré: bolsos com 4 itens",
          len(motor._direct_items(TORVIN / "calca-de-linho")) == 4)
    out7 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "seixo-preto", "to": "calca-de-linho"}]))
    check("7: 5º item negado — container_lotado (4/4)",
          any(r.get("regra") == "container_lotado"
              and r.get("valores", {}).get("atuais") == 4
              for r in out7["rejected"]))

    # 8: mãos ocupadas — ITEM 44: agora ACOMODA em vez de recusar.
    # Até aqui, quem estivesse com as duas mãos cheias não pegava NADA, nem um seixo.
    # Torvin segura o atiçador e uma bolsa: o seixo vai PARA A BOLSA que ele segura,
    # e nenhuma mão se mexe. A recusa `maos_ocupadas` continua existindo — só passou a
    # valer quando não há mesmo onde pôr (ver 15c).
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "aticador-de-ferro", "to": "torvin-ferreiro"}]))
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "bolsa-pequena", "to": "torvin-ferreiro"}]))
    out8 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "seixo-preto", "to": "torvin-ferreiro"}]))
    ac8 = (out8.get("item_transfers_applied") or [{}])[0].get("acomodou") or {}
    check("8: o desvio é DECLARADO no applied (Princípio X: nada em silêncio)",
          ac8.get("modo") == "guardou_o_que_recebeu" and ac8.get("para"), str(ac8))
    # o destino é o que o mundo DISSE ter escolhido — o teste não adivinha qual bolsa,
    # confere que a coisa está mesmo onde o applied afirma (é o que o jogador leu).
    check("8: pegar de mãos cheias ACOMODA — o seixo foi para a bolsa anunciada",
          not out8["rejected"]
          and (TORVIN / (ac8.get("para") or "?") / "seixo-preto").is_dir(),
          str(out8["rejected"]) + str(ac8))
    check("8: e chega narrado ao jogador",
          any("Bolsa" in f for f in server_app.inworld_effects(out8)),
          str(server_app.inworld_effects(out8)))
    # devolve o seixo ao chão: os cenários seguintes contam com ele solto
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "seixo-preto", "to": "taverna-do-gancho"}]))

    # 18: depositar o que se carried_item_ids em contêiner no chão — bypass de B e D
    out18 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "aticador-de-ferro", "to": "arca-de-ferro"}]))
    check("18: guardar na arca do chão aplicado (sem teto de peso: ninguém a porta)",
          out18["item_transfers_applied"] == [{"item": "aticador-de-ferro",
                                               "to": "arca-de-ferro"}])

    # 9: peso agregado excede a carga (arca 150 + atiçador 3 = 153 > 112)
    out9 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "arca-de-ferro", "to": "torvin-ferreiro"}]))
    rej9 = [r for r in out9["rejected"] if r.get("regra") == "peso_excede_carga"]
    check("9: erguer a arca (153 kg efetivos) negado — peso_excede_carga",
          bool(rej9) and rej9[0]["valores"]["capacidade_carga"] == 112)

    # ===================== US5 — shove (10, 11) ============================== #
    ctx = motor.get_context("torvin-ferreiro")
    cap10 = []
    r10 = selftest_helpers.resolve_scripted(INTENT, ctx,
        [("shove", {"item": "arca-de-ferro", "to": "mesa-de-madeira"}),
         ("narrate", {"narrative_hint": "arrasta a arca até junto da mesa"})],
        captured=cap10)
    out10 = motor.apply_resolution("torvin-ferreiro", r10)
    check("10: shove da arca (153 ≤ 224) aplicado, sem entrar na estrutura",
          cap10[0].get("ok") is True
          and out10["item_transfers_applied"] == [{"item": "arca-de-ferro",
                                                   "to": "mesa-de-madeira"}]
          and (TAVERNA / "mesa-de-madeira" / "arca-de-ferro" / "item.md").exists()
          and not (TORVIN / "arca-de-ferro").exists())

    ctx = motor.get_context("torvin-ferreiro")
    cap11 = []
    r11 = selftest_helpers.resolve_scripted(INTENT, ctx,
        [("shove", {"item": "bigorna-de-pedra", "to": "mesa-de-madeira"}),
         ("narrate", {"narrative_hint": "a bigorna não cede um dedo"})], captured=cap11)
    out11 = motor.apply_resolution("torvin-ferreiro", r11)
    check("11: bigorna (300 > 224) negada — peso_excede_empurrar (guarda e Motor)",
          cap11[0].get("regra") == "peso_excede_empurrar"
          and any(r.get("regra") == "peso_excede_empurrar"
                  for r in r11["tool_rejections"])
          and out11["item_transfers_applied"] == [])

    # ===================== US3 — troca e unequip (12) ======================== #
    motor.apply_resolution("torvin-ferreiro", res(
        equip_ops=[{"op": "equip", "item": "mochila-de-couro"}]))
    out_stow_own = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "bolsa-pequena", "to": "mochila-de-couro"}]))
    check("17a: reorganizar os próprios pertences (bolsa → mochila vestida) aplicado",
          out_stow_own["item_transfers_applied"] == [{"item": "bolsa-pequena",
                                                      "to": "mochila-de-couro"}])
    # cascata cross-portador: Elga guarda algo na mochila vestida de Torvin (D nele)
    motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "seixo-preto", "to": "elga-taverneira"}]))
    out17 = motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "seixo-preto", "to": "mochila-de-couro"}]))
    check("17b: guardar no contêiner de OUTRO valida o portador final e aplica",
          out17["item_transfers_applied"] == [{"item": "seixo-preto",
                                               "to": "mochila-de-couro"}])
    peso_torvin = motor.carried_weight(TORVIN)
    check("17c: peso cascateia ao portador (mochila + bolsa + seixo somam nele)",
          peso_torvin > 1.4)

    ctx = motor.get_context("torvin-ferreiro")
    cap12 = []
    r12 = selftest_helpers.resolve_scripted(INTENT, ctx,
        [("unequip", {"item": "calca-de-linho"}),
         ("equip", {"item": "calca-de-la"}),
         ("narrate", {"narrative_hint": "troca a calça de linho pela de lã"})],
        captured=cap12)
    check("12: guarda aceita a TROCA no mesmo turno (unequip + equip)",
          cap12[0].get("ok") is True and cap12[1].get("ok") is True
          and r12["equip_ops"] == [
              {"op": "unequip", "item": "calca-de-linho", "to": "torvin-ferreiro"},
              {"op": "equip", "item": "calca-de-la"}])
    out12 = motor.apply_resolution("torvin-ferreiro", r12)
    check("12: aplicação da troca — lã vestida, linho na mão",
          len(out12["equip_ops_applied"]) == 2
          and (motor.slots_in_use(TORVIN).get("pernas") == ["calca-de-la"]))
    linho_fm, _ = motor.read_doc(TORVIN / "calca-de-linho" / "item.md")
    check("12: linho tirado foi para a mão, com os bolsos INTACTOS (4 itens)",
          motor.item_slot(linho_fm) == "mao"
          and len(motor._direct_items(TORVIN / "calca-de-linho")) == 4)
    check("SC-003: nunca dois equipamentos na mesma parte",
          all(len(ids) <= validator.SLOTS[s] for s, ids
              in motor.slots_in_use(TORVIN).items()))

    # ============= 15 — o RECEBEDOR de mãos cheias ACOMODA (item 44) ========= #
    # O caso que ABRIU os itens 44/45: dar uma moeda a quem segurava duas coisas era
    # recusado por `maos_ocupadas`. Mecanicamente correto, e o efeito era que ninguém
    # de mãos cheias recebia nada — o gesto social mais comum do jogo virava turno
    # perdido. Medido em jogo: dois dias de tentativas do Torvin contra o Obadiah, que
    # estava de mãos cheias justamente com o que Torvin queria.
    #
    # A decisão do mantenedor foi SIMETRIA: os dois lados acomodam. Duas saídas, a
    # menos invasiva primeiro — (a) o que chega vai para uma bolsa de quem recebe;
    # (b) só se não couber, libera uma mão guardando o que já estava nela.
    motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "moeda-de-ouro", "to": "elga-taverneira"}]))
    motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "bolsa-de-couro", "to": "elga-taverneira"}]))
    ELGA = TAVERNA / "elga-taverneira"

    # 15a — o que chega CABE na bolsa dela: nenhuma mão se mexe.
    out15a = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "seixo-preto", "to": "elga-taverneira"}]))
    check("15a: quem recebe de mãos cheias guarda o recebido na PRÓPRIA bolsa",
          not out15a["rejected"]
          and (ELGA / "bolsa-de-couro" / "seixo-preto").is_dir()
          and motor.slots_in_use(ELGA).get("mao")
              == ["bolsa-de-couro", "moeda-de-ouro"],
          str(out15a["rejected"]) + str(motor.slots_in_use(ELGA)))

    # 15b — o que chega NÃO cabe (atiçador M numa bolsa P): aí sim libera a mão,
    # guardando o que estava nela. Nunca desloca o item da própria ação.
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "aticador-de-ferro", "to": "torvin-ferreiro"}]))
    out15b = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "aticador-de-ferro", "to": "elga-taverneira"}]))
    ac15 = (out15b.get("item_transfers_applied") or [{}])[0].get("acomodou") or {}
    check("15b: não cabendo na bolsa, ela LIBERA a mão guardando o que segurava",
          not out15b["rejected"] and ac15.get("modo") == "liberou_a_mao"
          and (ELGA / "bolsa-de-couro" / "moeda-de-ouro").is_dir()
          and "aticador-de-ferro" in (motor.slots_in_use(ELGA).get("mao") or []),
          str(out15b["rejected"]) + str(ac15))
    check("15b: e o jogador é avisado do que ela guardou (Princípio X)",
          any("abrir a mão" in f for f in server_app.inworld_effects(out15b)),
          str(server_app.inworld_effects(out15b)))

    # 15c — SEM SAÍDA a recusa continua valendo, agora honesta: não há mesmo onde.
    # Elga passa a bolsa adiante e fica com duas coisas que não guardam nada.
    motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "bolsa-de-couro", "to": "taverna-do-gancho"}]))
    motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "seixo-branco", "to": "elga-taverneira"}]))
    out15 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "calca-de-linho", "to": "elga-taverneira"}]))
    check("15c: sem bolsa onde acomodar, `maos_ocupadas` segue negando",
          any(r.get("regra") == "maos_ocupadas" for r in out15["rejected"]),
          str(out15["rejected"]))
    check("15c: e nada foi mexido nas mãos dela ao tentar",
          len(motor.slots_in_use(ELGA).get("mao") or []) == 2,
          str(motor.slots_in_use(ELGA)))

    # ============ item 31 §2: posse/vestir viram autoridade do executor ======= #
    # equip de item que está com OUTRA pessoa (calca-de-linho está no torvin) e
    # unequip de item NÃO vestido: as duas eram pré-voo da tool; agora a recusa vem
    # do executor `_apply_equip_ops`, CORRIGÍVEL (leva os validos), sem "não refaça".
    ctx_e = motor.get_context("elga-taverneira")
    cap_al = []
    selftest_helpers.resolve_scripted(INTENT, ctx_e,
        [("equip", {"item": "calca-de-linho"}),
         ("narrate", {"narrative_hint": "a calça é de Torvin"})], captured=cap_al)
    check("item31: equip de item alheio recusa item_alheio (corrigível, com validos)",
          cap_al[0].get("regra") == "item_alheio" and bool(cap_al[0].get("validos"))
          and "não refaça" not in cap_al[0].get("erro", ""))
    ctx_t = motor.get_context("torvin-ferreiro")
    cap_nv = []
    selftest_helpers.resolve_scripted(INTENT, ctx_t,
        [("unequip", {"item": "seixo-branco"}),
         ("narrate", {"narrative_hint": "o seixo não estava vestido"})], captured=cap_nv)
    check("item31: unequip de item não-vestido recusa nao_vestido_em_voce (corrigível)",
          cap_nv[0].get("regra") == "nao_vestido_em_voce"
          and "não refaça" not in cap_nv[0].get("erro", ""))

    # ===================== failed_effects estruturado (FR-011/SC-007) ======== #
    frases = server_app.inworld_failures(out15["rejected"])
    estruturadas = [f for f in frases if isinstance(f, dict) and f.get("regra")]
    check("failed_effects carried_item_ids {regra, valores} além do texto in-world",
          estruturadas and estruturadas[0]["regra"] == "maos_ocupadas"
          and "valores" in estruturadas[0])
    check("frase de mundo presente na entrada estruturada",
          bool(estruturadas[0].get("o_que_falhou")))

    # manifest: tools por verbo, omissão sem candidato
    tools = {t["name"] for t in arbiter.build_tools(motor.get_context("torvin-ferreiro"))}
    check("manifest: tools por verbo presentes na cena",
          {"take", "give", "stow", "drop", "unequip", "mutate",
           "create_memory", "narrate"} <= tools and "transfer_item" not in tools)
    ctx_vazio = {"characters_present": [{"id": "a", "name": "A"}],
                 "objects_present": [], "items_present": [],
                 "self": {"id": "a", "inventory": [], "fisico": {}},
                 "location": {"id": "x", "name": "X"}, "routes": [],
                 "in_transit": True}
    tools_vazio = {t["name"] for t in arbiter.build_tools(ctx_vazio)}
    check("manifest: cena sem itens omite os verbos de item",
          not ({"take", "give", "stow", "drop", "shove", "equip",
                "unequip"} & tools_vazio))

    # mundo segue íntegro após toda a sequência (nenhum arquivo corrompido)
    check("mundo íntegro ao final (validator em tudo)", motor.validate_world() == [],
          str(motor.validate_world()))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 7 (spec 004) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
