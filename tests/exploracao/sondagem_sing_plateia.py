"""LABORATÓRIO DE RÉGUA — `sing`, EXPERIMENTO 4: quem julga a plateia?

Complementa `sondagem_sing_regua.py`. A pergunta aqui é a que a skill
`loreforge-arbitrated-action` já responde para as outras tools arbitradas, e que a
primeira rodada de opções tinha esquecido:

  "NÃO peça ao Árbitro que some memórias de cabeça — ele faz mal (spec 016 mediu
   nota 7 para quem o personagem espancou). O mundo entrega o afeto à régua em
   RÓTULO ('guarda mágoa', 'nutre estima'), que COLORE a nota."

O afeto de cada ouvinte pelo cantor JÁ é medido pelo mundo (`motor.sentiment_toward`).
Então há duas formas de a plateia entrar na régua:

  JA  a régua vê a cena crua (nome, o que faz, humor) e o modelo estima tudo sozinho
  JE  o mundo MEDE a disposição de cada ouvinte pelo cantor e entrega em RÓTULO; a
      régua é instruída a NÃO reestimar, só usar

O teste isola exatamente isso: a MESMA cena, a MESMA lembrança, mudando SÓ a
disposição da plateia pelo cantor. Se a nota não se mover, o rótulo é peso morto e
JA vence por ser mais barato. Se se mover em JE e não em JA, o rótulo está fazendo
um trabalho que o modelo não faria sozinho.

Uso:  python3 tests/exploracao/sondagem_sing_plateia.py   (exige só o Ollama de pé)
"""
import json
import os
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from motor import juizo  # noqa: E402

MODELO, TEMP, R = "llama3.1:8b", 0.2, 5

LEMBRANCA = ("Vi Torvin descer ao poço com uma marreta e voltar arrastando aquilo "
             "pelo pescoço. Ninguém falou nada por um minuto inteiro.")
LUGAR = {"nome": "Taverna do Gancho",
         "descricao": ("Salão baixo de vigas negras, cheiro de peixe e cerveja azeda. "
                       "A lareira range. As mesas estão cheias e ninguém tem pressa.")}

# A MESMA gente, fazendo A MESMA coisa. Só a relação com o cantor muda.
def plateia(rotulo):
    base = [("Elga, a Taverneira", "seca canecas atrás do balcão", "cansada"),
            ("Bram", "conta moedas devagar", "tranquilo"),
            ("Ossian", "olha a porta a cada ruído", "arisco")]
    saida = []
    for nome, fazendo, humor in base:
        p = {"nome": nome, "fazendo": fazendo, "humor": humor}
        if rotulo is not None:
            p["disposicao_por_voce"] = rotulo
        saida.append(p)
    return saida


ABERTURA = """\
Você vai julgar UMA tentativa de cantar uma lembrança para quem está presente.
Leia a lembrança e a cena REAIS fornecidas com cuidado — nunca invente detalhes
que não estejam nelas."""

ESCADA = """\
Régua da CANÇÃO (o quanto ESTE episódio, NESTA cena, comporta virar canção — não
o quanto o cantor é bom, que não é assunto seu):
  0  não vira canção — nada de memorável aconteceu, OU a cena não comporta canção
     nenhuma (correria, briga, incêndio, todos dormindo) (sem teste)
  5  o caso comum — um feito de verdade, uma mesa que pode ouvir
  10 a canção se canta sozinha — feito extraordinário diante de quem quer ouvi-lo
Julgue o EPISÓDIO e a CENA, nunca quem canta. A nota é segredo do mundo."""

USE_O_ROTULO = """\
A disposição de cada ouvinte POR QUEM CANTA já vem MEDIDA pelo mundo, no campo
`disposicao_por_voce`. NÃO a reestime a partir do que você acha das pessoas: use
o que está escrito. Uma sala que já gosta dele ouve o que ele canta; uma sala que
guarda mágoa dele escuta de má vontade, por melhor que seja o feito."""

LETRA = """\
A LETRA é o que a plateia ouve, na voz de quem canta para uma mesa. Duas a quatro
frases. Use o lugar e quem está ouvindo. Não invente pessoas, lugares ou feitos
que não estejam na lembrança."""

FECHO = """\
Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"cancao": <inteiro 0-10>, "letra": "<a canção>"}"""

VARIANTES = [
    ("JA sem rótulo (modelo estima)", ABERTURA + "\n\n" + ESCADA + "\n\n" + LETRA
     + "\n\n" + FECHO, False),
    ("JE com rótulo medido pelo mundo", ABERTURA + "\n\n" + ESCADA + "\n\n"
     + USE_O_ROTULO + "\n\n" + LETRA + "\n\n" + FECHO, True),
]

RELACOES = [
    ("plateia que NUTRE ESTIMA por ele", "nutre estima por você"),
    ("plateia que NÃO O CONHECE      ", "não te conhece"),
    ("plateia que GUARDA MÁGOA dele  ", "guarda mágoa de você"),
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


print(f"modelo={MODELO} temp={TEMP} rodadas={R}")
print("A MESMA cena e a MESMA lembrança nas três linhas — só a relação muda.\n")
for nome_v, system, usa_rotulo in VARIANTES:
    print(f"--- {nome_v} ---")
    medias = []
    for rot_nome, rotulo in RELACOES:
        vals = []
        for _ in range(R):
            user = json.dumps({
                "lembranca": LEMBRANCA, "sobre": "Torvin, o Ferreiro", "lugar": LUGAR,
                "plateia": plateia(rotulo if usa_rotulo else None),
                "prosa": "Renn puxa o banco para perto da lareira."},
                ensure_ascii=False, indent=2)
            j = juizo.julgamento(ask(system, user), {"cancao": 5}, {"letra": ""})
            vals.append(j["cancao"])
        medias.append(statistics.mean(vals))
        print(f"   {rot_nome} → {vals}  média {statistics.mean(vals):.1f}")
    print(f"   >> AMPLITUDE (estima − mágoa): {medias[0] - medias[2]:+.1f}\n")

print("Leitura: amplitude ~0 em JE = o rótulo é peso morto (vence JA, mais barato).")
print("Amplitude >0 só em JE = o mundo está informando algo que o modelo não infere.")
