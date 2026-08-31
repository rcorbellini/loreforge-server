"""LABORATÓRIO DE RÉGUA — `write` (spec 059), o GATE de admissão.

Mede o prompt que o corpo da tool manda ao Árbitro para julgar DUAS coisas, uma
chamada só: a SUPERFÍCIE (o alvo aceita escrita?) e o INSTRUMENTO (o que está na
mão serve para escrever?). Não precisa de server nem de mundo de laboratório — é
função pura de prompt→JSON, com o parse REAL (`motor.juizo.julgamento`).

Duas formulações (research.md R4):
  G1  cada régua com só os dois extremos (0 e 10) + uma frase de viés-para-aceitar.
  G2  cada régua com três pontos (0, 5, 10) — o meio nomeia o caso "serve mas mal".

Itens REAIS do mundo (para a superfície) e descrições candidatas (para o
instrumento, que ainda não existe em nenhum item — research.md R6).

Uso:  python3 tests/exploracao/sondagem_write_gate.py
      (exige só o Ollama de pé)
"""
import json
import os
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from motor import juizo  # noqa: E402 — o parse REAL, não uma cópia

MODELO, TEMP, R = "llama3.1:8b", 0.2, 3

# --------------------------------------------------------------------------- #
# SUPERFÍCIE — itens REAIS do mundo (loreforge-world), copiados do .md.
# --------------------------------------------------------------------------- #
SUPERFICIE_POS = [
    ("livro-de-orais (item real)",
     {"nome": "Livro de Orais",
      "descricao": ("Um livro fino de capa de couro rachada, páginas amareladas "
                    "cobertas de orações copiadas à mão, algumas em letra que já "
                    "não se pratica mais fora deste santuário.")}, (7, 10)),
    ("mapa-remendado-do-vau (item real)",
     {"nome": "Mapa Remendado do Vau",
      "descricao": ("Um mapa da região, desenhado a carvão sobre couro fino e "
                    "remendado com retalhos costurados nas bordas gastas.")}, (7, 10)),
    ("carta-lacrada (item real)",
     {"nome": "Carta Lacrada",
      "descricao": ("Um envelope de pergaminho grosso, fechado com um lacre de "
                    "cera vermelha sem nenhum brasão.")}, (5, 10)),
    ("pergaminho em branco (candidato, spec 059)",
     {"nome": "Pergaminho em Branco",
      "descricao": "Uma folha de pergaminho em branco, ainda sem uma palavra."},
     (7, 10)),
    ("quadro de avisos (candidato, spec 059)",
     {"nome": "Quadro de Avisos",
      "descricao": ("Um quadro de madeira maciça, com furos de prego antigos onde "
                    "recados já foram pendurados.")}, (7, 10)),
]
SUPERFICIE_NEG = [
    ("faca-de-escamar (item real, ARMA)",
     {"nome": "Faca de Escamar",
      "descricao": ("Lâmina curta e curva, o cabo enrolado em corda encerada. O "
                    "fio já foi afiado tantas vezes que a lâmina ficou mais fina "
                    "do que deveria — mas ainda corta.")}, (0, 3)),
    ("moeda-cobre (item real, MOEDA)",
     {"nome": "Moeda de Cobre",
      "descricao": "Uma moedinha de cobre, escura de tanto passar de mão em mão."},
     (0, 2)),
    ("maçã (item real, ALIMENTO)",
     {"nome": "Maçã",
      "descricao": ("Uma maçã vermelha, firme e brilhante, ainda pendurada entre "
                    "as folhas.")}, (0, 2)),
]

# --------------------------------------------------------------------------- #
# INSTRUMENTO — nenhum existe ainda no mundo (research.md R6); testando a
# âncora CANDIDATA (T009) e casos limítrofes.
# --------------------------------------------------------------------------- #
INSTRUMENTO_POS = [
    ("pena-e-tinteiro (âncora candidata, T009)",
     {"nome": "Pena e Tinteiro",
      "descricao": ("Uma pena de ganso aparada e um pequeno tinteiro de vidro, "
                    "tampado, que ele carrega para lacrar e endereçar as próprias "
                    "entregas.")}, (7, 10)),
    ("toco de carvão (candidato, spec 059)",
     {"nome": "Toco de Carvão",
      "descricao": "Um toco de carvão, envolto num pano para não sujar o bolso."},
     (5, 10)),
]
INSTRUMENTO_LIMITROFE = [
    ("faca-de-escamar (poderia RISCAR/talhar?)",
     {"nome": "Faca de Escamar",
      "descricao": ("Lâmina curta e curva, o cabo enrolado em corda encerada. O "
                    "fio já foi afiado tantas vezes que a lâmina ficou mais fina "
                    "do que deveria — mas ainda corta.")}, None),  # sem faixa esperada — é o PONTO em disputa
]
INSTRUMENTO_NEG = [
    ("moeda-cobre (item real)",
     {"nome": "Moeda de Cobre",
      "descricao": "Uma moedinha de cobre, escura de tanto passar de mão em mão."},
     (0, 2)),
    ("maçã (item real)",
     {"nome": "Maçã",
      "descricao": ("Uma maçã vermelha, firme e brilhante, ainda pendurada entre "
                    "as folhas.")}, (0, 2)),
]

# --------------------------------------------------------------------------- #
# As duas formulações do prompt (G1/G2) — SÓ o texto muda; o payload é sempre
# {"alvo": {...}, "instrumento": {...}}.
# --------------------------------------------------------------------------- #
_ABERTURA = """\
Um personagem quer escrever sobre um objeto, usando algo que tem na mão. Julgue
DUAS coisas, só pela DESCRIÇÃO de cada um — nunca pelo nome, raridade ou valor."""

_FECHO = """\

Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"superficie": <inteiro 0-10>, "instrumento": <inteiro 0-10>}"""

G1_EXTREMOS = """\
Nota da SUPERFÍCIE (0-10): o quanto a descrição do ALVO sugere algo em que se
escreve (página, quadro, pergaminho, parede lisa, couro, madeira lisa...).
  0  claramente NÃO é algo em que se escreve (arma, comida, moeda, ferramenta
     sem superfície)
  10 claramente é algo em que se escreve
Em DÚVIDA, penda para CIMA — um objeto comum descrito como "liso" ou "com
espaço" já basta.

Nota do INSTRUMENTO (0-10): o quanto a descrição do que está NA MÃO sugere algo
com que se escreve (pena, carvão, giz, ponta que risca ou mancha...).
  0  claramente NÃO serve para escrever (comida, moeda, algo sem ponta nem tinta)
  10 claramente serve para escrever
Em DÚVIDA, penda para CIMA."""

G2_TRES_PONTOS = """\
Nota da SUPERFÍCIE (0-10) — o quanto a descrição do ALVO sugere algo em que se
escreve:
  0  claramente não é superfície de escrita (arma, comida, moeda)
  5  duvidoso, mas tem ALGUMA chance (um objeto liso, plano, sem função óbvia
     descrita) — EM DÚVIDA, use este valor ou mais, nunca 0-2
  10 claramente é superfície de escrita (página, pergaminho, quadro, couro)

Nota do INSTRUMENTO (0-10) — o quanto a descrição do que está NA MÃO sugere algo
com que se escreve:
  0  claramente não serve (comida, moeda, algo redondo e liso)
  5  serve mal / improvisado (algo pontiagudo ou que mancha, mas não feito para
     isso) — EM DÚVIDA, use este valor ou mais, nunca 0-2
  10 claramente serve (pena, carvão, giz, estilete)"""


def payload(alvo, instrumento):
    return json.dumps({"alvo": alvo, "instrumento": instrumento},
                      ensure_ascii=False, indent=2)


def ask(system, user):
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": TEMP},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return ((r.get("message") or {}).get("content") or "")


def faixa(v, esperado):
    if esperado is None:
        return None
    lo, hi = esperado
    return lo <= v <= hi


INSTRUMENTO_NEUTRO = {"nome": "Toco de Carvão",
                      "descricao": "Um toco de carvão, envolto num pano."}
ALVO_NEUTRO = {"nome": "Pergaminho em Branco",
              "descricao": "Uma folha de pergaminho em branco."}


def roda_bloco(nome_g, system, titulo, casos, chave, outro_fixo, outro_pos):
    print(f"\n--- {titulo} ({nome_g}) ---")
    acertos, total = 0, 0
    for rot, item, esperado in casos:
        vals = []
        for _ in range(R):
            if outro_pos == "alvo":
                raw = ask(system, payload(item, outro_fixo))
            else:
                raw = ask(system, payload(outro_fixo, item))
            j = juizo.julgamento(raw, {"superficie": 5, "instrumento": 5}, {})
            v = j.get(chave, 5)
            vals.append(v)
            if esperado is not None:
                total += 1
                if faixa(v, esperado):
                    acertos += 1
        marcador = "esperado " + (f"{esperado[0]}-{esperado[1]}" if esperado else "EM DISPUTA")
        print(f"   {rot:44s} → {vals}  ({marcador})")
    if total:
        print(f"   ACERTOS na faixa: {acertos}/{total}")
    else:
        print("   (sem faixa esperada — caso em disputa)")


for nome_g, system_txt in (("G1 extremos", _ABERTURA + "\n\n" + G1_EXTREMOS + _FECHO),
                           ("G2 três pontos", _ABERTURA + "\n\n" + G2_TRES_PONTOS + _FECHO)):
    print("\n" + "=" * 78)
    print(f"FORMULAÇÃO {nome_g}")
    print("=" * 78)
    roda_bloco(nome_g, system_txt, "SUPERFÍCIE — casos POSITIVOS",
              SUPERFICIE_POS, "superficie", INSTRUMENTO_NEUTRO, "alvo")
    roda_bloco(nome_g, system_txt, "SUPERFÍCIE — casos NEGATIVOS",
              SUPERFICIE_NEG, "superficie", INSTRUMENTO_NEUTRO, "alvo")
    roda_bloco(nome_g, system_txt, "INSTRUMENTO — casos POSITIVOS",
              INSTRUMENTO_POS, "instrumento", ALVO_NEUTRO, "instrumento")
    roda_bloco(nome_g, system_txt, "INSTRUMENTO — casos NEGATIVOS",
              INSTRUMENTO_NEG, "instrumento", ALVO_NEUTRO, "instrumento")
    roda_bloco(nome_g, system_txt, "INSTRUMENTO — caso LIMÍTROFE (faca)",
              INSTRUMENTO_LIMITROFE, "instrumento", ALVO_NEUTRO, "instrumento")

print("\nFIM.")
