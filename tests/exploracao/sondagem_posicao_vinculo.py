"""LABORATÓRIO DE POSIÇÃO — o que decide o vínculo sobreviver é o TAMANHO ou o LUGAR?

NASCEU DE UM ERRO DE LEITURA MEU (spec 066, Phase 0). A primeira sondagem
(`sondagem_vinculo_afeto.py`) mostrou "primo" sobrevivendo 7/8 e "irmã de criação" 1/8, e
eu concluí que **o modelo poda a qualificação** — que rótulo longo se perde.

A segunda (`sondagem_rotulo_vinculo.py`) desmentiu: com quatro rótulos numa cena, "primo"
(1 palavra) caiu para 1/8 e "irmão de criação" (3 palavras) subiu para 3/8. Tamanho não
ordena nada.

O que as duas têm em comum é POSIÇÃO: nas duas, o rótulo de PRIMEIRO da lista sobreviveu
1/8, e um dos últimos sobreviveu 6-7/8.

Este script isola a variável: **o MESMO rótulo, na MESMA cena, rodando por todas as
posições.** Se a taxa acompanhar a posição e não o rótulo, o achado é de ORDEM, e a
decisão que ele afeta não é o tamanho do campo `bonds.label` — é como o conector ordena o
trecho social.

Uso:  python3 tests/exploracao/sondagem_posicao_vinculo.py   (exige só o Ollama de pé)
"""
import json
import re
import sys
import urllib.request

MODELO, TEMP, R = "llama3.1:8b", 0.4, 6

LOCAL = {"nome": "Praça do Mercado",
         "descricao": ("Bancas de pano puxado, cheiro de peixe seco e especiaria. "
                       "O sol já está alto e o movimento é grande.")}

NOMES = ["Renn", "Hulda", "Doncel", "Bram"]
ROTULO = "irmã"                       # UM rótulo só, para a variável ser a posição
NUCLEO = re.compile(r"irm[ãa]", re.I)
NEUTRO = "conhecido de vista"          # o que preenche as outras posições

ABERTURA = """\
Você é a mente de um personagem de RPG, numa cena real. Vai reagir ao que está à
sua volta. NUNCA invente relação, sentimento ou fato que não lhe foi dito."""

PERGUNTA = """\
Para CADA pessoa presente, escreva UMA frase curta (até 15 palavras) dizendo o que
você pensa ou sente ao vê-la. Baseie-se SOMENTE no que lhe foi informado."""

FECHO = """\
Responda SOMENTE com um objeto JSON, chaves = nomes exatamente como aparecem,
nada antes nem depois, EXATAMENTE assim:

{"Renn": "<frase>", "Hulda": "<frase>", "Doncel": "<frase>", "Bram": "<frase>"}"""

SYSTEM = ABERTURA + "\n\n" + PERGUNTA + "\n\n" + FECHO


def montar_user(pos_do_rotulo: int):
    """A cena é sempre a mesma; só QUEM leva o rótulo `irmã` muda de lugar."""
    frases = []
    for i, nome in enumerate(NOMES):
        frases.append(f"{nome}, {ROTULO if i == pos_do_rotulo else NEUTRO}.")
    presentes = [{"nome": n, "fazendo": "circula entre as bancas"} for n in NOMES]
    return json.dumps({
        "lugar": LOCAL,
        "contexto_social": "Quem lhe diz alguma coisa aqui: " + " ".join(frases),
        "presentes": presentes,
    }, ensure_ascii=False, indent=2)


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


print(f"modelo={MODELO} temp={TEMP} rodadas={R} por posição")
print(f"O MESMO rótulo ({ROTULO!r}) rodando pelas 4 posições. Só a ORDEM muda.\n")

ask(SYSTEM, montar_user(0))            # aquecimento, não conta

resultado = []
for pos in range(len(NOMES)):
    nome = NOMES[pos]
    acertos, validas = 0, 0
    for _ in range(R):
        resp = parse(ask(SYSTEM, montar_user(pos)))
        if not resp:
            continue
        validas += 1
        if NUCLEO.search(resp.get(nome, "") or ""):
            acertos += 1
    resultado.append((pos + 1, nome, acertos, validas))
    print(f"   posição {pos+1} de 4 ({nome}): {acertos}/{validas}")

print("\n=== RESULTADO ===")
for pos, nome, acertos, validas in resultado:
    barra = "#" * acertos
    print(f"posição {pos}  {acertos}/{validas}  {barra}")

primeira = resultado[0][2]
ultima = resultado[-1][2]
print(f"\nprimeira posição {primeira} x última posição {ultima}")
print("Se a última vence a primeira com folga, o achado é de ORDEM — e a decisão que")
print("ele afeta é como o conector ORDENA o trecho social, não o tamanho do rótulo.")
print("Se as quatro empatam, a posição não explica, e as duas sondagens anteriores")
print("estavam medindo ruído — o que também é resultado, e muda o que se pode afirmar.")
