"""Log de desenvolvimento — terminal do server + arquivo persistente.

Mostra o fluxo de cada turno, do ponto de vista do server:
  1. o que chegou do client (character_id + intenção)
  2. o que foi enviado à LLM do Árbitro (system + user)
  3. o que a LLM do Árbitro devolveu (cru)
  4. o que voltou ao client (narrative_hint + mutações aplicadas)

Cada entrada carried_item_ids data, hora e a VERSÃO DO SERVER que a produziu, e é APPEND
em arquivo de texto —
sobrevive a reinícios do server (o terminal/redirect trunca; o arquivo não).
Arquivo padrão: server/devlog.log (mude com LOREFORGE_LOG_FILE=<caminho>).

Ligado por padrão. Para silenciar:  LOREFORGE_LOG=0 python3 server/app.py
(silencia terminal E arquivo — os selftests rodam assim, sem sujar o log real).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from version import __version__

ENABLED = os.environ.get("LOREFORGE_LOG", "1") != "0"
LOG_FILE = os.environ.get("LOREFORGE_LOG_FILE") or str(
    Path(__file__).resolve().parent / "devlog.log")


def log(label: str, content=None) -> None:
    if not ENABLED:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    # a VERSÃO vai em toda entrada: ler um log sem saber que código o produziu
    # já custou uma hora e meia de jogo contra um server desatualizado
    lines = [f"\n──────── {ts} · v{__version__} · {label} ────────"]
    if content is not None:
        if isinstance(content, str):
            lines.append(content.rstrip())
        else:
            try:
                lines.append(json.dumps(content, ensure_ascii=False, indent=2))
            except (TypeError, ValueError):
                lines.append(str(content))
    text = "\n".join(lines)
    print(text, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass  # log nunca derruba o jogo: sem disco/permissão, segue só no terminal
