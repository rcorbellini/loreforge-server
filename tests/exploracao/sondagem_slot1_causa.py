"""O SLOT MORTO É DO MUNDO OU DO MEU INSTRUMENTO? (spec 066, Phase 0)

`sondagem_posicao_vinculo.py` achou que o vínculo da primeira pessoa listada morre (0/6
contra 6/6 nas posições 2 e 3). `sondagem_slot1_vinculo.py` mostrou que mexer na REDAÇÃO
não recupera (0/6, 1/6, 1/6).

Sobra uma hipótese que eu deveria ter testado antes de tirar conclusão de desenho:
**o efeito pode ser do HARNESS.** Nas três sondagens, a pessoa da posição 1 é também a
PRIMEIRA CHAVE que o modelo tem de gerar no JSON de resposta (o `FECHO` fixa a ordem
"Renn, Hulda, Doncel, Bram"). Se o que morre é a primeira chave GERADA, e não o primeiro
item LIDO, então o achado não é sobre o formato do contexto — é sobre o meu pedido de
saída, que o jogo real nem faz (A Mente escolhe UMA ação, não enumera os presentes).

O teste separa as duas ordens:

  A  entrada: Renn 1º   | saída: Renn 1ª chave    <- as duas juntas (o caso original)
  B  entrada: Renn 1º   | saída: Renn ÚLTIMA chave <- só a ordem de saída muda
  C  entrada: Renn 3º   | saída: Renn 1ª chave    <- só a ordem de entrada muda

Se B recupera e C não, a causa é a ORDEM DE GERAÇÃO — artefato do instrumento, e
nenhuma regra de desenho deve sair daí.
Se C recupera e B não, a causa é a ORDEM DE LEITURA — e aí é achado real do formato.

Uso:  python3 tests/exploracao/sondagem_slot1_causa.py   (exige só o Ollama de pé)
"""
import json
import re
import urllib.request

MODELO, TEMP, R = "llama3.1:8b", 0.4, 6

LOCAL = {"nome": "Praça do Mercado",
         "descricao": ("Bancas de pano puxado, cheiro de peixe seco e especiaria. "
                       "O sol já está alto e o movimento é grande.")}

ROTULO, NEUTRO = "irmã", "conhecido de vista"
NUCLEO = re.compile(r"irm[ãa]", re.I)
ALVO = "Renn"

ABERTURA = """\
Você é a mente de um personagem de RPG, numa cena real. Vai reagir ao que está à
sua volta. NUNCA invente relação, sentimento ou fato que não lhe foi dito."""

PERGUNTA = """\
Para CADA pessoa presente, escreva UMA frase curta (até 15 palavras) dizendo o que
você pensa ou sente ao vê-la. Baseie-se SOMENTE no que lhe foi informado."""


def fecho(ordem_saida):
    campos = ", ".join(f'"{n}": "<frase>"' for n in ordem_saida)
    return ("Responda SOMENTE com um objeto JSON, chaves = nomes exatamente como "
            "aparecem, nada antes nem depois, EXATAMENTE assim:\n\n{" + campos + "}")


def montar(ordem_entrada):
    frases = [f"{n}, {ROTULO if n == ALVO else NEUTRO}." for n in ordem_entrada]
    return json.dumps({
        "lugar": LOCAL,
        "contexto_social": "Quem lhe diz alguma coisa aqui: " + " ".join(frases),
        "presentes": [{"nome": n, "fazendo": "circula entre as bancas"}
                      for n in ordem_entrada],
    }, ensure_ascii=False, indent=2)


ENTRADA_ALVO_1o = ["Renn", "Hulda", "Doncel", "Bram"]
ENTRADA_ALVO_3o = ["Hulda", "Doncel", "Renn", "Bram"]
SAIDA_ALVO_1a = ["Renn", "Hulda", "Doncel", "Bram"]
SAIDA_ALVO_ULT = ["Hulda", "Doncel", "Bram", "Renn"]

CASOS = [
    ("A  entrada 1º | saída 1ª  (o caso original)", ENTRADA_ALVO_1o, SAIDA_ALVO_1a),
    ("B  entrada 1º | saída ÚLTIMA", ENTRADA_ALVO_1o, SAIDA_ALVO_ULT),
    ("C  entrada 3º | saída 1ª", ENTRADA_ALVO_3o, SAIDA_ALVO_1a),
]


def ask(system, user):
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": TEMP},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return ((json.loads(urllib.request.urlopen(req, timeout=300).read())
             .get("message") or {}).get("content") or "")


def parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


print(f"modelo={MODELO} temp={TEMP} rodadas={R}")
print(f"Alvo fixo: {ALVO} com o rótulo {ROTULO!r}. Variam a ordem de ENTRADA e a de SAÍDA.\n")

ask(ABERTURA + "\n\n" + PERGUNTA + "\n\n" + fecho(SAIDA_ALVO_1a), montar(ENTRADA_ALVO_1o))

for nome_c, ordem_ent, ordem_sai in CASOS:
    system = ABERTURA + "\n\n" + PERGUNTA + "\n\n" + fecho(ordem_sai)
    acertos, validas = 0, 0
    for _ in range(R):
        resp = parse(ask(system, montar(ordem_ent)))
        if not resp:
            continue
        validas += 1
        if NUCLEO.search(resp.get(ALVO, "") or ""):
            acertos += 1
    print(f"{nome_c}: {acertos}/{validas}  {'#' * acertos}")

print("\nB alto e C baixo  -> causa é a ORDEM DE GERAÇÃO: artefato do harness, e as")
print("                     conclusões de posição das sondagens anteriores caem.")
print("C alto e B baixo  -> causa é a ORDEM DE LEITURA: achado real sobre o formato.")
print("Os dois altos     -> as duas ordens contam, e cada uma pesa um pouco.")
