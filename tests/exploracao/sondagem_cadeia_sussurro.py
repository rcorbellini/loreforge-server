"""O SUSSURRO QUE PEDE UMA CADEIA — a Mente encadeia, ou faz só o primeiro passo?

A PERGUNTA (mantenedor, 2026-08-31): "quando eu sussurro pra um personagem uma
frase que claramente possui uma cadeia de mais de um tool call a ser feita ele
não costuma fazer."

O item 54 já tinha um número parecido, mas por OUTRA via: 2/5 na cena que exige
"acender depois cozinhar" — e ali a Mente decidia SOZINHA o que fazer (escolha
autônoma). Aqui o jogador DIZ a sequência, com todas as letras. É outra medição:
se ela falha até quando lhe entregam o plano pronto, o defeito não é planejar.

O DESENHO, que é o que dá sentido ao número. Quatro famílias de sussurro, e as
duas primeiras são CONTROLE — sem elas um número ruim não distingue "não sabe
encadear" de "não sabe chamar duas ferramentas":

  UMA        1 tool.  Prova que o caminho funciona (piso).
  INDEP      2 tools INDEPENDENTES (a ordem não importa, nenhuma precisa da
             outra). Isola MULTIPLICIDADE.
  CADEIA2    2 tools DEPENDENTES (a segunda só é possível depois da primeira).
             Isola DEPENDÊNCIA.
  CADEIA3    3 tools dependentes. Mede se o problema piora com o comprimento.

Se INDEP passa e CADEIA2 falha, o defeito é encadear.
Se INDEP falha junto, o defeito é emitir mais de uma chamada — outro conserto.

FIDELIDADE AO JOGO: prompt `ESCOLHER_SYSTEM` copiado LETRA POR LETRA de
`mente.js`, payload montado como `_contextoPayload(..., {comCapacidades:false})`
(sem o bloco de capacidades em prosa — repetir o schema derrubava 4 de 9
chamadas, medido em 2026-08-17), temperatura 0.4 como o conector usa, e
`llama3.1:8b`, que é o modelo que a Mente deste jogo de fato roda — não o
qwen3:8b das sondagens de description.

RESULTADO (2026-08-31, llama3.1:8b, 35 rodadas + ablações):

    família   tools pedidas   cadeia completa   média de chamadas
    UMA                   1        10/10                     1.0
    INDEP                 2         0/10                     1.0
    CADEIA2               2         0/10                     1.0
    CADEIA3               3          0/5                     1.0

Nunca saiu mais de UMA chamada. Nenhuma rodada muda. E `INDEP` falha IGUAL a
`CADEIA2` — o controle derruba a hipótese da cadeia: o defeito não é encadear,
é emitir a segunda chamada.

O QUE NÃO É (cada um medido à parte):
  · não é o MODELO nem o runtime — com um system curto e a MESMA face de 39
    tools, o llama3.1:8b devolveu duas chamadas em 10 de 10;
  · não é o PROMPT — duas variantes que mandam, com todas as letras, "chame
    TODAS nesta mesma resposta" não mudaram nada (0/5, 0/5);
  · não é o tamanho do CONTEXTO — cortar o payload de 1222 para 867 tokens
    (fora memórias e personalidade) não moveu o número.

O QUE É: a MASSA do pedido. Num 2x2 com a instrução idêntica —

    system JOGO   + contexto CHEIO    0/5    1.0 chamada
    system MÍNIMO + contexto CHEIO    0/5    1.0
    system JOGO   + contexto VAZIO    2/5    1.4
    system MÍNIMO + contexto VAZIO    4/5    1.8

O bloco `tools` da face sozinho pesa ~13.300 tokens (11x o contexto). Com o
pedido inteiro montado, o modelo colapsa em exatamente uma chamada.

E O LAÇO FECHA A PORTA: `laco.js::_porPropostas` só chama `continuar()` quando
uma proposta é RECUSADA (`if (!parou) break` — "foi até o fim: nada a
repensar"). Quando o único passo proposto DÁ CERTO, o turno acaba ali e a Mente
nunca é perguntada "e agora?". Os dois defeitos se somam: ela propõe um passo,
ele funciona, e a vez termina.

Uso:  python3 tests/exploracao/sondagem_cadeia_sussurro.py
      (exige o Ollama de pé; lê o mundo REAL direto pelo Motor, sem servidor)
"""
import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER_DIR))
os.environ.setdefault("LOREFORGE_LOG", "0")

import motor          # noqa: E402
import face           # noqa: E402
import mcp_core       # noqa: E402

MODELO, RODADAS, TEMPERATURA = "llama3.1:8b", 5, 0.4

# --- LETRA POR LETRA de `mente.js::ESCOLHER_SYSTEM` ------------------------- #
ESCOLHER_SYSTEM = """Você é A Mente de um personagem de RPG num mundo persistente. A instrução do jogador é uma sugestão de vontade — o personagem NÃO é um robô: tem índole e personalidade inegociáveis.

As ferramentas disponíveis são TUDO o que ele pode tentar aqui e agora; o mundo já filtrou pela cena.

ANTES DE AGIR, pense na SEQUÊNCIA de ações que ele quer realizar e escolha as ferramentas que cumprem essa sequência. Depois chame SOMENTE essas, na ordem pensada. A lista disponível não é um cardápio a percorrer: ferramenta que não faz parte da sequência não se chama. Se uma delas falhar, PARE — a cena mudou e o resto da sequência pode não valer mais; pense uma nova a partir do que aconteceu, e aja de novo.

- Toda chamada leva "prosa.acao": o que ele FAZ, in-world e concreto. "prosa.fala" só se falar em voz alta.
- Descreva a TENTATIVA, nunca o desfecho: se convenceu, se acertou, se passou despercebido, quem decide é o mundo.
- Se a instrução violar a personalidade dele, faça o que ele de fato faria — e a prosa conta a recusa.
- Se nada couber exatamente, escolha a ferramenta MAIS PRÓXIMA do que ele quer e diga na prosa o que ele tenta. Quem decide se cabe é o mundo, não você — um "não" dele é jogo; ficar calado não é.
- CONFIRME ANTES DE AGIR. Algumas ferramentas só PERGUNTAM (a sua memória, o momento do dia) — não mudam nada e não gastam a vez. Se o que ele pretende depende de uma CONDIÇÃO ("se aquele ali roubou", "quem é ladrão aqui") ou de um MOMENTO ("ao anoitecer", "no fim do dia"), pergunte primeiro e decida depois. Agir sobre palpite é como se acusa e se fere quem não devia. Nunca cite o nome de uma ferramenta na prosa."""


def _payload(ctx):
    """O mesmo recorte de `_contextoPayload(context, {comCapacidades:false})`."""
    self_ = ctx.get("self") or {}
    loc = ctx.get("location") or {}
    return {
        "personalidade": self_.get("body"),
        "necessidade": self_.get("necessidade"),
        "contexto": {
            "local": loc.get("name"),
            "descricao": loc.get("narrative") or loc.get("description"),
            "presentes": [{"id": c.get("id"), "nome": c.get("name"),
                           "fazendo": c.get("action")}
                          for c in (ctx.get("characters_present") or [])
                          if c.get("state") != "self"],
            "objetos_presentes": [{"id": o.get("id"), "nome": o.get("name")}
                                  for o in (ctx.get("objects_present") or [])],
            "itens_presentes": [{"id": i.get("id"), "nome": i.get("name")}
                                for i in (ctx.get("items_present") or [])],
            "inventario": [{"id": i.get("id"), "nome": i.get("name")}
                           for i in (self_.get("inventory") or [])],
        },
        "memorias": [m.get("summary") or m.get("content")
                     for m in (ctx.get("memories") or [])][:20],
        "rotas_disponiveis": [{"id": r.get("id"), "nome": r.get("name"),
                               "para": r.get("destination_name")}
                              for r in (ctx.get("routes") or [])],
    }


def _tools(ctx):
    """A face REAL, no formato OpenAI que o adaptador do Ollama exige."""
    out = []
    for cap in face.build(ctx):
        out.append({"type": "function", "function": {
            "name": cap["nome"],
            "description": cap.get("descricao") or "",
            "parameters": mcp_core.input_schema(cap)}})
    return out


def _chat(system, user, tools):
    body = {"model": MODELO, "stream": False,
            "options": {"temperature": TEMPERATURA},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "tools": tools}
    req = urllib.request.Request(
        "http://localhost:11434/api/chat", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    msg = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return (msg.get("message") or {})


# --- os casos --------------------------------------------------------------- #
# `esperado` = as capacidades que a instrução PEDE, na ordem. `familia` agrupa.
CASOS = [
    ("UMA     ", "torvin-ferreiro",
     "Entregue uma das suas moedas de cobre ao Obadiah.",
     ["give"]),
    ("UMA     ", "torvin-ferreiro",
     "Pegue o frasco de óleo que está no chão.",
     ["take"]),
    ("INDEP   ", "torvin-ferreiro",
     "Repare bem no frasco de óleo que está no chão, e pergunte à Odila o "
     "que ela sabe sobre a Hulda.",
     ["examine", "ask_about"]),
    ("INDEP   ", "torvin-ferreiro",
     "Pergunte à Odila por onde se vai daqui, e repare no cantil de água "
     "que está no chão.",
     ["ask_directions", "examine"]),
    ("CADEIA2 ", "torvin-ferreiro",
     "Pegue o frasco de óleo do chão e entregue ao Obadiah.",
     ["take", "give"]),
    ("CADEIA2 ", "torvin-ferreiro",
     "Pegue o cantil de água do chão e guarde na sua bolsa de couro.",
     ["take", "stow"]),
    ("CADEIA3 ", "torvin-ferreiro",
     "Pegue o frasco de óleo do chão, guarde na sua bolsa de couro, e "
     "depois pergunte à Odila por onde se vai daqui.",
     ["take", "stow", "ask_directions"]),
]


def main():
    print(f"modelo {MODELO} · temperatura {TEMPERATURA} · {RODADAS} rodadas por caso")
    print("prompt: ESCOLHER_SYSTEM verbatim de mente.js · payload sem "
          "`capacidades` em prosa\n")
    por_familia = {}
    for familia, quem, instr, esperado in CASOS:
        ctx = motor.get_context(quem)
        tools = _tools(ctx)
        user = ("O que ele faz?\n\nINSTRUÇÃO: " + instr + "\n\n"
                + json.dumps(_payload(ctx), ensure_ascii=False, indent=2))
        print("=" * 78)
        print(f"[{familia}] {instr}")
        print(f"   espera: {' -> '.join(esperado)}  ({len(tools)} tools na face)")
        acertos = mudos = 0
        chamadas_por_rodada = []
        vistos = Counter()
        for r in range(RODADAS):
            msg = _chat(ESCOLHER_SYSTEM, user, tools)
            calls = [c.get("function", {}).get("name")
                     for c in (msg.get("tool_calls") or [])]
            calls = [c for c in calls if c]
            chamadas_por_rodada.append(len(calls))
            vistos.update(calls)
            if not calls:
                mudos += 1
            # ACERTO = todas as esperadas saíram, na ordem pedida (extras não
            # invalidam: o mundo recusa o que não couber, e o que se mede aqui
            # é se a CADEIA saiu).
            pos, ok = 0, True
            for alvo in esperado:
                if alvo in calls[pos:]:
                    pos = calls.index(alvo, pos) + 1
                else:
                    ok = False
                    break
            acertos += 1 if ok else 0
            print(f"   r{r+1}: {calls or '— MUDO —'}")
        print(f"   => {acertos}/{RODADAS} cadeias completas · "
              f"{mudos} mudo(s) · média {sum(chamadas_por_rodada)/RODADAS:.1f} "
              f"chamada(s) por rodada")
        f = por_familia.setdefault(familia, {"ok": 0, "n": 0, "chamadas": [],
                                             "mudo": 0, "esperadas": 0})
        f["ok"] += acertos
        f["n"] += RODADAS
        f["mudo"] += mudos
        f["chamadas"] += chamadas_por_rodada
        f["esperadas"] = len(esperado)

    print("\n" + "=" * 78)
    print("PLACAR POR FAMÍLIA")
    print("=" * 78)
    print(f"{'família':10} {'tools pedidas':>14} {'cadeia completa':>17} "
          f"{'média chamadas':>15} {'mudo':>6}")
    for familia, f in por_familia.items():
        media = sum(f["chamadas"]) / len(f["chamadas"])
        print(f"{familia:10} {f['esperadas']:>14} "
              f"{f['ok']:>8}/{f['n']:<8} {media:>15.1f} {f['mudo']:>6}")


if __name__ == "__main__":
    main()
