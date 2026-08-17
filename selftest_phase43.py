"""Auto-teste da Fase 43 — Expulsar (spec 041), fatia MOVIMENTO (US1/US2) + dedup.

Cobre o VERBO: com força, o alvo sai e o ATOR FICA; sem força, o alvo não se move
e volta recusa; recusas (a si mesmo, ausente); dedup por alvo no turno. A MEMÓRIA
(rancor + depende_observador, US3) é fatia à parte e NÃO é coberta aqui.

`_roll_d20` forçado. Uso:  python3 server/selftest_phase43.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test43-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
from motor import rolagem  # noqa: E402
from motor.deslocamento.declaracao import _expel  # noqa: E402

FAILS = []
ATOR, ALVO = "torvin-ferreiro", "elga-taverneira"
TAVERNA, ROTA = "Taverna do Gancho", "portao-lateral"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _force_roll(v):
    rolagem._roll_d20 = lambda: v


def _presentes(cid):
    return {p["id"] for p in motor.get_context(cid)["characters_present"]}


def _local(cid):
    return motor.get_context(cid)["location"]["name"]


def _mk_char(cid, name, loc_folder):
    d = loc_folder / cid
    (d / "memories").mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        "---\ntype: character\nid: %s\nname: %s\ncontrolled_by: player_local\n"
        "attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        "skills:\n  observacao: 1\nstatus:\n  hp: 20\n  hp_max: 20\n  hunger: saciado\n"
        "  fatigue: leve\n  action: parado na taverna.\n  mood: neutro\n  conditions: []\n"
        "origin: editorial\n---\n\n%s observa a cena.\n" % (cid, name, name),
        encoding="utf-8")


def _seed_mem(cid, loc_folder, sobre, valencia):
    import time
    d = loc_folder / cid / "memories"
    d.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    mid = f"mem-{now}-{cid}-seed"
    (d / f"{mid}.md").write_text(
        "---\ntype: memory\nid: %s\nkind: acontecimento\ninvolved: [%s]\n"
        "timestamp_start: %d\ntimestamp_end: %d\nintensity: large\nstate: active\n"
        "summary: seed\ndomain: social\nvalence:\n  %s: %s\n---\n\nlembrança semeada.\n"
        % (mid, sobre, now, now + 10 ** 7, sobre, valencia), encoding="utf-8")


def run() -> int:
    FAILS.clear()
    from motor.memoria.primitivas import sentiment_toward
    # UM mundo só, ordenado estático→movimento (o deslocamento por último — a lição
    # do exploratório). Forço o desfecho trocando forte/fraco: FRACO expulsa FORTE
    # com dado 1 → falha garantida; FORTE expulsa fraco com dado 20 → sucesso.

    # TESTEMUNHAS com afeto PRÉVIO pelo expulso (Elga), para o depende_observador:
    loc = motor.find_character_folder(ATOR).parent  # a taverna
    _mk_char("wodeia", "Wodeia", loc); _seed_mem("wodeia", loc, ALVO, "negativa")
    _mk_char("wpreza", "Wpreza", loc); _seed_mem("wpreza", loc, ALVO, "positiva")
    _mk_char("wneutro", "Wneutro", loc)  # sem afeto prévio por Elga
    check("seed: Wodeia guarda mágoa de Elga", sentiment_toward("wodeia", ALVO) < 0)
    check("seed: Wpreza nutre estima por Elga", sentiment_toward("wpreza", ALVO) > 0)

    # US2 — força NÃO basta (Elga, fraca, tenta expulsar Torvin com dado 1)
    _force_roll(1)
    out2 = motor.apply_resolution(ALVO, {"expel_ops": [{"alvo": ATOR, "rota": ROTA}]},
                                  ensure_action=False)
    check("US2: força não basta → o alvo (Torvin) NÃO saiu",
          ATOR in _presentes(ALVO), str(_presentes(ALVO)))
    check("US2: volta recusa estruturada (não silêncio)", bool(out2.get("rejected")),
          str(out2.get("rejected"))[:80])

    # Recusas do executor (nada se move)
    _force_roll(20)
    out_self = motor.apply_resolution(ATOR, {"expel_ops": [{"alvo": ATOR, "rota": ROTA}]},
                                      ensure_action=False)
    check("recusa: expulsar a si mesmo", bool(out_self.get("rejected")))
    out_abs = motor.apply_resolution(ATOR, {"expel_ops": [{"alvo": "ninguem-xyz", "rota": ROTA}]},
                                     ensure_action=False)
    check("recusa: alvo ausente", bool(out_abs.get("rejected")))

    # US1 — força BASTA (Torvin, forte, expulsa Elga com dado 20) — POR ÚLTIMO (move)
    _force_roll(20)
    antes = _presentes(ATOR)
    motor.apply_resolution(ATOR, {"expel_ops": [{"alvo": ALVO, "rota": ROTA}]},
                           ensure_action=False)
    check("US1: força basta → o ALVO (Elga) SAIU da cena",
          ALVO in antes and ALVO not in _presentes(ATOR), str(_presentes(ATOR)))
    check("US1: o ATOR PERMANECE no lugar", _local(ATOR) == TAVERNA, _local(ATOR))

    # US3 — MEMÓRIA: rancor no expulso + depende_observador nas testemunhas
    check("US3: o EXPULSO (Elga) guarda RANCOR do ator (dispara trauma)",
          sentiment_toward(ALVO, ATOR) < 0, f"sent={sentiment_toward(ALVO, ATOR):.2f}")
    check("US3: quem ODIAVA o expulso → APROVA o expulsor (Wodeia +)",
          sentiment_toward("wodeia", ATOR) > 0, f"sent={sentiment_toward('wodeia', ATOR):.2f}")
    check("US3: quem PREZAVA o expulso → REPROVA o expulsor (Wpreza −)",
          sentiment_toward("wpreza", ATOR) < 0, f"sent={sentiment_toward('wpreza', ATOR):.2f}")
    check("US3: indiferente ao expulso → NEUTRO com o expulsor (Wneutro 0)",
          sentiment_toward("wneutro", ATOR) == 0, f"sent={sentiment_toward('wneutro', ATOR):.2f}")

    # DEDUP (T010): a guarda barra a 2ª expulsão do MESMO alvo no turno
    errs = []
    ctx = types.SimpleNamespace(
        actor=ATOR, chars={ATOR: "Torvin", ALVO: "Elga"}, routes={ROTA: "Forja"},
        expulsos=set(), queue={"expel_ops": []},
        validos=lambda m: list(m), err=lambda *a, **k: (errs.append(a), {"ok": False})[1])
    r1, _ = _expel("expulsar", {"alvo": ALVO, "rota": ROTA}, ctx)
    r2, _ = _expel("expulsar", {"alvo": ALVO, "rota": ROTA}, ctx)
    check("dedup: 1ª expulsão enfileira", r1.get("ok") is True and ALVO in ctx.expulsos)
    check("dedup: 2ª expulsão do mesmo alvo é BARRADA", r2.get("ok") is False,
          str(r2))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S) na Fase 43: {', '.join(FAILS)}")
        return 1
    print("Fase 43 (Expulsar — movimento + dedup, spec 041) OK.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
