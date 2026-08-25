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


def requisicao(metodo: str, caminho: str, corpo, porta: int = 8777) -> None:
    """Registra um POST **por inteiro, reproduzível como curl** (spec 053).

    POR QUE ISTO PRECISOU EXISTIR. O devlog prometia, no próprio docstring, registrar
    "o que foi enviado à LLM do Árbitro (system + user)" — e registrava 80 caracteres
    da RESPOSTA, sem o prompt. Quando um julgamento saiu errado no jogo (um sílex
    julgado como combustível excelente, 2026-08-24), não havia como saber o que o
    Árbitro tinha recebido: foi preciso adivinhar a causa e reproduzi-la à mão.

    Um log que não permite REPRODUZIR o caso é log de conforto, não de diagnóstico.
    A entrada sai como um `curl` colável: o caso volta a rodar sem reconstruir nada.
    """
    if not ENABLED:
        return
    try:
        corpo_txt = json.dumps(corpo, ensure_ascii=False)
    except Exception:
        corpo_txt = repr(corpo)
    curl = (f"curl -s -X {metodo} http://localhost:{porta}{caminho} \\\n"
            f"  -H 'Content-Type: application/json' \\\n"
            f"  -d '{corpo_txt}'")
    log(f"REQUISIÇÃO {metodo} {caminho} — reproduzível", curl)


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
