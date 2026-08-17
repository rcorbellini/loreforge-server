"""Auto-teste da Fase 9 — Teste de Força com Rolagem no Empurrar (spec 006).

Cobre, com rolagem forçada (motor._roll_d20 injetável):
  - os 4 quadrantes natural×rolagem: resultado aplicado e VIRADA presente só nos
    dois invertidos (SC-001)
  - zonas determinísticas: trivial nunca rola; impossível nunca passa (SC-002)
  - falha de rolagem nega com teste_de_forca_falhou + rolagem nos valores
  - viradas sobem no shape do app (fate_twists) com frase in-world
  - a guarda do Árbitro DEIXA tentar acima da capacidade (até 2×) — quem rola é
    o Motor (single roll)

Cenário: Torvin STR 16 ⇒ empurra 224 kg; arca 150 kg (natural SIM, zona de
rolagem); bigorna 500 kg (> 448 = impossível); moeda (trivial). Elga STR 11 ⇒
154 kg; arca carregada a ~154.6 kg ⇒ natural NÃO na zona de rolagem.

Uso:  python3 server/selftest_phase9.py
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

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def force_roll(value):
    motor._roll_d20 = lambda: value


def forbid_roll():
    def _boom():
        raise AssertionError("rolagem não deveria acontecer aqui")
    motor._roll_d20 = _boom


def res(**parts):
    base = {"narrative_hint": "empurra o que está pela frente", "movement": None,
            "mutations": [], "item_transfers": [], "equip_ops": [],
            "lock_ops": [], "memories": []}
    base.update(parts)
    return base


try:
    TAVERNA = motor.WORLD_DIR / "taverna-do-gancho"

    # --- unidades: modificador, DC e limites --------------------------------- #
    check("modificador D&D: STR 16 → +3; STR 8 → -1",
          motor.attr_modifier(16) == 3 and motor.attr_modifier(8) == -1)
    check("DC no limite natural = 10; a 2× = 20",
          motor.push_dc(224, 224) == 10 and motor.push_dc(448, 224) == 20)
    check("limites: check_empurrar só nega acima de 2× (zona de rolagem passa)",
          motor.check_empurrar("t", "x", 300, 224) is None
          and motor.check_empurrar("t", "x", 500, 224) is not None)

    # --- trivial: nunca rola (SC-002) ---------------------------------------- #
    forbid_roll()
    out_triv = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "moeda-de-cobre", "to": "mesa-de-madeira"}]))
    check("trivial: moeda empurrada sem rolagem (dado proibido não foi chamado)",
          out_triv["item_transfers_applied"] == [{"item": "moeda-de-cobre",
                                                  "to": "mesa-de-madeira"}]
          and out_triv["rolls"] == [])

    # --- impossível: nunca passa, mesmo com sorte máxima (SC-002) ------------ #
    force_roll(20)
    out_imp = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "bigorna-de-pedra", "to": "mesa-de-madeira"}]))
    check("impossível: bigorna 500 kg negada mesmo com d20=20 (sem rolagem)",
          any(r.get("regra") == "peso_excede_empurrar" for r in out_imp["rejected"])
          and out_imp["rolls"] == [])

    # --- quadrante 1: natural SIM + rolagem boa ⇒ sucesso SEM virada --------- #
    force_roll(20)
    out_q1 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "arca-de-ferro", "to": "mesa-de-madeira"}]))
    check("Q1: natural sim + d20 alto ⇒ move, roll registrado, SEM virada",
          out_q1["item_transfers_applied"] and out_q1["rolls"]
          and out_q1["rolls"][0]["virada"] is False
          and out_q1["rolls"][0]["resultado"] == "sucesso")
    check("Q1: sem virada ⇒ nada para o client (fate_twists vazio)",
          server_app.fate_twists(out_q1["rolls"]) == [])
    # devolve a arca ao salão para os próximos quadrantes
    force_roll(20)
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "arca-de-ferro", "to": "taverna-do-gancho"}]))

    # --- quadrante 2: natural SIM + rolagem ruim ⇒ falha COM virada ---------- #
    force_roll(1)
    out_q2 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "arca-de-ferro", "to": "mesa-de-madeira"}]))
    rej_q2 = [r for r in out_q2["rejected"]
              if r.get("regra") == "teste_de_forca_falhou"]
    check("Q2: natural sim + d20=1 ⇒ NÃO move; teste_de_forca_falhou com rolagem",
          out_q2["item_transfers_applied"] == [] and rej_q2
          and rej_q2[0]["valores"]["rolagem"]["d20"] == 1
          and rej_q2[0]["valores"]["natural_conseguiria"] is True
          and rej_q2[0]["valores"]["virada"] is True)
    twists_q2 = server_app.fate_twists(out_q2["rolls"])
    check("Q2: virada negativa vira narrativa in-world para o client",
          twists_q2 and "devia ceder" in twists_q2[0]["o_que"]
          and twists_q2[0]["rolagem"]["dc"] >= 2)

    # --- quadrantes 3/4 com Elga: enche a arca até passar dos 154 kg dela ----- #
    # 150 (arca) + 3 (atiçador) + 1.2 (mochila) + 0.41 (caixa) = 154.61 > 154
    force_roll(20)
    for carga in ("aticador-de-ferro", "mochila-de-couro", "caixa-de-pinho"):
        motor.apply_resolution("torvin-ferreiro", res(
            item_transfers=[{"item": carga, "to": "arca-de-ferro"}]))
    arca_folder = TAVERNA / "arca-de-ferro"
    check("preparo: arca carregada acima do limite natural de Elga (154 kg)",
          motor.effective_weight(arca_folder) > 154)
    # Q4: natural NÃO + rolagem ruim ⇒ falha SEM virada (fracasso esperado)
    force_roll(1)
    out_q4 = motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "arca-de-ferro", "to": "mesa-de-madeira"}]))
    check("Q4: natural não + d20=1 ⇒ falha esperada, roll registrado SEM virada",
          out_q4["item_transfers_applied"] == []
          and out_q4["rolls"] and out_q4["rolls"][0]["virada"] is False
          and server_app.fate_twists(out_q4["rolls"]) == [])
    # Q3: natural NÃO + rolagem boa ⇒ sucesso COM virada
    force_roll(20)
    out_q3 = motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "arca-de-ferro", "to": "mesa-de-madeira"}]))
    check("Q3: natural não + d20=20 ⇒ MOVE, com virada positiva",
          out_q3["item_transfers_applied"] == [{"item": "arca-de-ferro",
                                                "to": "mesa-de-madeira"}]
          and out_q3["rolls"][0]["virada"] is True
          and out_q3["rolls"][0]["natural_conseguiria"] is False)
    twists_q3 = server_app.fate_twists(out_q3["rolls"])
    check("Q3: virada positiva vira narrativa in-world ('arranque além do corpo')",
          twists_q3 and "arranque" in twists_q3[0]["o_que"])

    # --- guarda: deixa TENTAR acima da capacidade (quem rola é o Motor) ------ #
    ctx = motor.get_context("elga-taverneira")
    idx = arbiter._scene_index(ctx)
    cand = arbiter._verb_candidates(idx)
    check("guarda: arca (acima da capacidade natural de Elga) segue no enum de shove",
          "arca-de-ferro" in cand["shove"])

    # --- objeto fixo: tentar CARREGAR mobília nega com narrativa clara ------- #
    r_fixo = selftest_helpers.resolve_scripted(
        {"action": "leva a mesa embora"}, ctx,
        [("take", {"item": "mesa-de-madeira"})])
    check("objeto_fixo: guarda nega take de object com regra estruturada",
          any(r.get("regra") == "objeto_fixo"
              for r in r_fixo.get("tool_rejections", [])))
    out_fixo = motor.apply_resolution("elga-taverneira", res(
        item_transfers=[{"item": "mesa-de-madeira", "to": "elga-taverneira"}]))
    rej_fixo = [r for r in out_fixo["rejected"] if r.get("regra") == "objeto_fixo"]
    check("objeto_fixo: Motor (fallback) nega igual — pipeline único",
          bool(rej_fixo))
    frases = server_app.inworld_failures(out_fixo["rejected"])
    check("objeto_fixo: frase de mundo clara ('faz parte do lugar')",
          any(isinstance(f, dict) and "faz parte do lugar" in f.get("o_que_falhou", "")
              for f in frases))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 9 (spec 006) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
