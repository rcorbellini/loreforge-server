"""Auto-teste da Fase 46 — o Model Context Protocol (spec 043, Fase 8).

(Número de FASE ≠ número de SPEC.)

O MCP é o transporte ABERTO: qualquer host joga sem escrever integração. O risco
que este teste guarda não é o protocolo (é simples) — é a DIVERGÊNCIA. Se a face do
MCP não for idêntica à do transporte direto, uma Mente de terceiro proporia coisas
que o mundo recusa, e o erro seria invisível dos dois lados.

E guarda o invariante estrutural: o MCP é CLIENTE do REST, nunca um segundo escritor.
`app.py` mantém a trava de turno EM PROCESSO; um servidor MCP que importasse `motor`
correria com o REST sobre os mesmos `.md`, violando a mutação atômica e serializada
que o Princípio III exige.

Sem rede: o `Mundo` é substituído por um dublê que devolve uma cena fixa. O que se
testa é a TRADUÇÃO, não o HTTP.

Uso:  python3 server/selftest_phase46.py
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVER_DIR))

import mcp_core  # noqa: E402
import mcp_server  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# Uma cena fixa, no MESMO formato que `/api/context` devolve.
CENA = {
    "capacidades": [
        {"nome": "take", "descricao": "Pega um item ao alcance.",
         "alvos": {"item": ["faca-cega", "moeda-cobre-001"]}, "exige": ["item"]},
        {"nome": "ask_directions", "descricao": "Pergunta por onde se vai.",
         "alvos": {"quem": ["torvin-ferreiro"]}, "exige": ["quem"]},
    ]
}


class MundoFalso:
    def __init__(self, cena=None, resposta=None):
        self.cid = "fenn-dedos-leves"
        self._cena = cena if cena is not None else CENA
        self._resposta = resposta or {"aconteceu": ["pegou a Faca Cega"],
                                      "narrative_hint": "pegou a faca"}
        self.propostas = []

    def contexto(self):
        return self._cena

    def propor(self, nome, corpo):
        self.propostas.append((nome, corpo))
        return self._resposta


def _rodar(mundo, linhas):
    """Roda o laço do servidor sobre um stdin de mentira; devolve as mensagens."""
    entrada = io.StringIO("\n".join(json.dumps(m) for m in linhas) + "\n")
    saida = io.StringIO()
    stdin, stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = entrada, saida
    try:
        mcp_server.servir(mcp_core.Sessao(mundo))
    finally:
        sys.stdin, sys.stdout = stdin, stdout
    return [json.loads(l) for l in saida.getvalue().splitlines() if l.strip()]


def run() -> int:
    FAILS.clear()

    # --- PARIDADE: os dois transportes respondem do MESMO núcleo --------------- #
    # O MCP é o caminho da MENTE (por HTTP, porque ela roda no navegador) e também o
    # do host externo (por stdio). Se as duas faces divergissem, uma Mente proporia
    # o que a outra não pode. Por isso `mcp_core` é único e os transportes são finos.
    fonte_stdio = (SERVER_DIR / "mcp_server.py").read_text(encoding="utf-8")
    fonte_app = (SERVER_DIR / "app.py").read_text(encoding="utf-8")
    check("stdio e HTTP tratam pelo MESMO núcleo (mcp_core.tratar)",
          "mcp_core.tratar" in fonte_stdio and "mcp_core.tratar" in fonte_app)
    check("nenhum transporte reimplementa o schema da capacidade",
          "def input_schema" not in fonte_stdio
          and "def input_schema" not in fonte_app)

    # --- GATE ESTRUTURAL: cliente do REST, nunca segundo escritor -------------- #
    fonte = (SERVER_DIR / "mcp_server.py").read_text(encoding="utf-8")
    check("o MCP não importa `motor` (é cliente do REST, não 2º escritor)",
          not re.search(r"^\s*(import motor|from motor)", fonte, re.M))
    check("o MCP não importa `arbiter` nem toca o mundo direto",
          not re.search(r"^\s*(import arbiter|from arbiter)", fonte, re.M))

    # --- initialize ----------------------------------------------------------- #
    msgs = _rodar(MundoFalso(), [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])
    r = msgs[0].get("result", {})
    check("initialize declara listChanged (a face muda a cada cena)",
          (r.get("capabilities", {}).get("tools", {}).get("listChanged")) is True,
          str(r))

    # --- tools/list é a MESMA face -------------------------------------------- #
    msgs = _rodar(MundoFalso(), [{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    tools = msgs[0]["result"]["tools"]
    check("tools/list traz exatamente as capacidades da cena",
          [t["name"] for t in tools] == [c["nome"] for c in CENA["capacidades"]],
          str([t["name"] for t in tools]))
    take = tools[0]
    check("os alvos viram enum — só o que existe na cena",
          take["inputSchema"]["properties"]["item"]["enum"]
          == ["faca-cega", "moeda-cobre-001"])
    check("`prosa` é parâmetro OBRIGATÓRIO de toda capacidade (FR-019/FR-035)",
          all("prosa" in t["inputSchema"]["required"] for t in tools)
          and all("acao" in t["inputSchema"]["properties"]["prosa"]["required"]
                  for t in tools))
    check("a descrição desce (é a player-facing da declaração)",
          all(t["description"] for t in tools))


    # --- ITEM 52.3: o MATERIAL das consultivas CHEGA ao client ------------------ #
    # Dos cinco canais de MATERIAL (`arbiter._MATERIAL_CH`), só `reconhecimentos` e
    # `informes` eram encaminhados. `lido` (o texto que o `examine` leu), `wares` (o
    # que o vendedor tem) e `falas` (o que o informante disse do caminho) morriam no
    # servidor — a Mente consultava e não recebia NADA de volta.
    #
    # Medido na Nerissa em 11h: `examine` 90x, `ask_directions` 83x, `ask_wares` 24x —
    # 197 dos 391 turnos dela em capacidades cujo resultado nunca chegava. Ela olhou a
    # MESMA bolsa de ervas 40 vezes porque olhar não lhe devolvia nada.
    m = MundoFalso(resposta={
        "narrative_hint": "olha a bolsa",
        "lido": ["Uma bolsa de couro puída, gasta de tanto abrir e fechar."],
        "wares": [{"item": "corda", "preco": 2}],
        "falas": [{"rota": "portao-lateral", "informante": "grum-estalajadeiro"}],
    })
    # PELO NÚCLEO, não pelo `_rodar`: o transporte STDIO descarta `_narrativa` de
    # propósito ("stdio manda só o texto", mcp_server.py) — um host externo recebe só
    # a frase de mundo. Quem recebe o material é o caminho HTTP, que é por onde A
    # Mente do conector fala. Testar pelo stdio media a decisão do outro transporte.
    _msgs52 = mcp_core.tratar({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                               "params": {"name": "examine",
                                          "arguments": {"alvo": "bolsa",
                                                        "prosa": {"acao": "olha"}}}},
                              mcp_core.Sessao(m))
    _narr = _msgs52[0]["result"].get("_narrativa") or {}
    for _canal in ("lido", "wares", "falas"):
        check(f"o material `{_canal}` CHEGA à Mente (era descartado pelo MCP)",
              _canal in _narr, str(sorted(_narr)))
    check("e o texto lido vem inteiro, não um resumo",
          "bolsa de couro puída" in str(_narr.get("lido")), str(_narr.get("lido")))

    # --- tools/call: traduz e injeta o personagem da sessão -------------------- #
    m = MundoFalso()
    msgs = _rodar(m, [{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "take",
                                  "arguments": {"item": "faca-cega",
                                                "prosa": {"acao": "apanha a faca"}}}}])
    check("tools/call repassa a capacidade e os argumentos ao mundo",
          m.propostas and m.propostas[0][0] == "take"
          and m.propostas[0][1].get("item") == "faca-cega",
          str(m.propostas))
    # o `character_id` é injetado pelo ADAPTADOR de cada transporte, não pelo núcleo:
    # uma sessão é UM personagem, e quem sabe qual é quem abriu a sessão.
    check("os dois adaptadores injetam o personagem da sessão",
          '"character_id": self.cid' in fonte_stdio
          and '"character_id": self.cid' in fonte_app)
    texto = msgs[0]["result"]["content"][0]["text"]
    check("o resultado é o FATO em linguagem de mundo",
          "pegou a Faca Cega" in texto, texto)
    check("sucesso não vem marcado como erro",
          msgs[0]["result"].get("isError") is False)

    # --- recusa in-world: resultado com isError, NUNCA erro de protocolo ------- #
    m = MundoFalso(resposta={"ok": False, "erro": "as mãos já estão ocupadas"})
    msgs = _rodar(m, [{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                       "params": {"name": "take",
                                  "arguments": {"item": "faca-cega",
                                                "prosa": {"acao": "apanha"}}}}])
    res = msgs[0].get("result")
    check("recusa do mundo volta como RESULTADO (isError), não erro JSON-RPC",
          res is not None and res.get("isError") is True
          and "error" not in msgs[0], str(msgs[0])[:160])
    check("a recusa carrega o motivo, em linguagem de mundo",
          "mãos já estão ocupadas" in res["content"][0]["text"])

    # --- nenhuma nota, nenhuma mecânica, atravessa ---------------------------- #
    m = MundoFalso(resposta={"aconteceu": ["furtou a bolsa"], "rolls": [
        {"rolagem": 17, "dc": 12, "vantagem": 8}], "narrative_hint": "furtou"})
    msgs = _rodar(m, [{"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                       "params": {"name": "take",
                                  "arguments": {"item": "faca-cega",
                                                "prosa": {"acao": "furta"}}}}])
    bruto = json.dumps(msgs, ensure_ascii=False)
    check("a rolagem e a nota NÃO atravessam para o host",
          not any(t in bruto for t in ("rolagem", "vantagem", '"dc"', "17")),
          bruto[:160])

    # --- list_changed dispara quando a cena muda ------------------------------ #
    class MundoQueMuda(MundoFalso):
        def __init__(self):
            super().__init__()
            self._n = 0

        def contexto(self):
            # 1ª leitura (tools/list) vê a cena cheia; a 2ª (a checagem depois do
            # tools/call) já vê uma capacidade a menos — alguém saiu do lugar.
            self._n += 1
            if self._n <= 1:
                return CENA
            return {"capacidades": [CENA["capacidades"][0]]}

    msgs = _rodar(MundoQueMuda(), [
        {"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
         "params": {"name": "take", "arguments": {"item": "faca-cega",
                                                  "prosa": {"acao": "x"}}}},
    ])
    notificou = any(m.get("method") == "notifications/tools/list_changed"
                    for m in msgs)
    check("mudou a cena → notifications/tools/list_changed", notificou,
          str([m.get("method") or m.get("id") for m in msgs]))

    # --- método desconhecido não derruba a sessão ----------------------------- #
    msgs = _rodar(MundoFalso(), [
        {"jsonrpc": "2.0", "id": 8, "method": "coisa/inexistente"},
        {"jsonrpc": "2.0", "id": 9, "method": "tools/list"},
    ])
    check("método desconhecido vira erro JSON-RPC e a sessão SEGUE",
          msgs[0].get("error", {}).get("code") == -32601
          and msgs[1].get("result", {}).get("tools"), str(msgs)[:160])

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S) na Fase 46: {', '.join(FAILS)}")
        return 1
    print("todos os checks da Fase 46 passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
