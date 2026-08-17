"""Auto-teste da Fase 24 — trava de turno-em-andamento (spec 022, reduzida pela 045).

O streaming NDJSON de `/api/act` (turn_start/heartbeat/op_applied/done) que esta
fase testava foi TODO retirado pela spec 045 — o endpoint não existe mais, e o
guichê único (`/api/tools/<nome>`, `/api/mcp`) sempre responde JSON simples, sem
eventos incrementais. Não há como migrar aquela cobertura: o que ela testava
deixou de existir no jogo.

O que sobrevive, porque o MECANISMO sobrevive (`_claim_turn`/`_release_turn`,
usado por `resolver_proposta`, o guichê único de hoje):
  - unidade da trava: _claim_turn/_release_turn
  - trava de turno-em-andamento (FR-005b), agora contra o guichê único: um
    turno já em andamento faz `/api/tools/<nome>` responder 409 com o motivo
    `turn_in_flight` — sem precisar de corrida de threads pra provar, já que
    `_claim_turn` é o mesmo estado compartilhado dos dois lados.

Uso:  python3 server/selftest_phase24.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402

FAILS = []
TORVIN = "torvin-ferreiro"


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def post_tool(port, nome, payload) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/tools/{nome}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    # --- unidade da trava --------------------------------------------------- #
    check("trava: _claim_turn marca e o 2º do mesmo id é negado",
          server_app._claim_turn("x") and not server_app._claim_turn("x"))
    server_app._release_turn("x")
    check("trava: após _release_turn, _claim_turn volta a valer",
          server_app._claim_turn("x"))
    server_app._release_turn("x")

    # --- a mesma trava, vista pelo guichê único (FR-005b) -------------------- #
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_app.Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        # simula um turno já em andamento pra este personagem — mesmo estado
        # compartilhado que um /api/tools/<nome> concorrente veria de verdade,
        # sem precisar de corrida de threads pra provar.
        server_app._claim_turn(TORVIN)
        try:
            post_tool(port, "examine",
                {"character_id": TORVIN, "alvo": TORVIN,
                 "prosa": {"acao": "olha ao redor"}})
            check("turno em andamento: guichê único rejeita com 409", False,
                  "não levantou HTTPError")
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            check("turno em andamento: guichê único rejeita com 409",
                  e.code == 409, str(e.code))
            check("turno em andamento: motivo é o mesmo da trava (turn_in_flight)",
                  "andamento" in (body.get("erro") or ""), body.get("erro"))
        finally:
            server_app._release_turn(TORVIN)

        # controle: sem turno em andamento, a mesma chamada resolve normalmente
        resp = post_tool(port, "examine",
            {"character_id": TORVIN, "alvo": TORVIN, "prosa": {"acao": "olha ao redor"}})
        check("sem trava em vigor, a mesma capacidade resolve (guichê único vivo)",
              "narrative_hint" in resp, str(list(resp)[:5]))
    finally:
        httpd.shutdown()

    print()
    if FAILS:
        print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS))
        sys.exit(1)
    print("Fase 24 (trava de turno, spec 022 reduzida pela 045) OK.")


if __name__ == "__main__":
    main()
