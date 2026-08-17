"""Model Context Protocol sobre stdio — a fronteira ABERTA (spec 043, Fase 8).

Para que qualquer host MCP (uma Mente de terceiro) jogue sem escrever integração
nenhuma. É o irmão do transporte direto: os dois leem o MESMO registro exposto, e o
que este arquivo faz é traduzir JSON-RPC ↔ HTTP. Nada mais.

CLIENTE DO REST, NUNCA SEGUNDO ESCRITOR — e isto não é estilo, é correção. O
`app.py` mantém a trava de turno em processo (`_claim_turn`). Um servidor MCP que
importasse `motor` seria um segundo escritor FORA dessa trava, correndo com o REST
sobre os mesmos `.md`; o Princípio III exige mutação atômica e serializada. Por isso
este módulo **não importa motor** — há um teste que afirma exatamente isso.

ZERO-INFRA preservado: processo local falando stdio com o host e localhost com o
próprio server. Nenhum serviço hospedado novo, nenhuma porta pública.

SESSÃO = UM PERSONAGEM. Um host MCP não passa "de quem é o turno" em `tools/list`, e
não precisa: uma Mente é um personagem, que é o modelo do projeto desde sempre. O id
é fixado ao iniciar.

Uso:
    python3 server/mcp_server.py --character-id fenn-dedos-leves [--base URL]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

import mcp_core

TIMEOUT = 180          # o juízo de uma capacidade arbitrada pode levar dezenas de s


class Mundo:
    """O transporte HTTP para o server do mundo. A única porta deste módulo."""

    def __init__(self, base: str, character_id: str):
        self.base = base.rstrip("/")
        self.cid = character_id

    def _req(self, url: str, corpo: dict | None = None) -> dict:
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(
            url, data=dados,
            headers={"Content-Type": "application/json"} if dados else {})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            corpo_erro = e.read().decode("utf-8", "replace")
            try:
                return json.loads(corpo_erro or "{}")
            except json.JSONDecodeError:
                return {"ok": False, "erro": f"o mundo respondeu {e.code}"}

    def contexto(self) -> dict:
        return self._req(f"{self.base}/api/context?character_id="
                         f"{urllib.parse.quote(self.cid)}")

    def propor(self, nome: str, corpo: dict) -> dict:
        return self._req(f"{self.base}/api/tools/{urllib.parse.quote(nome)}",
                         {**corpo, "character_id": self.cid})


def _escrever(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def servir(sessao) -> None:
    """O laço stdio. A tradução JSON-RPC mora em `mcp_core` — este arquivo é só o
    TRANSPORTE, e é isso que garante que o host externo e a Mente no navegador
    (que fala o mesmo protocolo por `POST /api/mcp`) enxerguem a MESMA face."""
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            msg = json.loads(linha)
        except json.JSONDecodeError:
            continue                      # ruído no fio não derruba a sessão
        for saida in mcp_core.tratar(msg, sessao):
            saida.get("result", {}).pop("_narrativa", None)  # stdio manda só o texto
            _escrever(saida)


def main() -> None:
    ap = argparse.ArgumentParser(description="Loreforge — Model Context Protocol.")
    ap.add_argument("--character-id", required=True,
                    help="uma Mente é um personagem; a sessão inteira fala por ele")
    ap.add_argument("--base", default="http://localhost:8777",
                    help="o server do mundo (o ÚNICO escritor)")
    args = ap.parse_args()
    servir(mcp_core.Sessao(Mundo(args.base, args.character_id)))


if __name__ == "__main__":
    main()
