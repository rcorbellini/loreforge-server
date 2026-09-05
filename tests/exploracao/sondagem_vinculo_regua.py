"""LABORATÓRIO DE RÉGUA — o vínculo move a nota da DISPOSIÇÃO? (spec 066, T028/US3)

A pergunta que decide se a feature nasce viva ou decorativa: **um parente pedindo é
diferente de um estranho pedindo?** Se a nota não se mover, o vínculo é peso morto no
juízo, e a spec 066 repetiria a lacuna da memória de testemunha (spec 024), que ficou
inerte até o item 20 porque nenhuma régua a lia.

`medir-prompt-do-arbitro-antes-de-aplicar`: toda régua nova nasce com 2+ propostas e
medição com o modelo real. A intuição errou o sinal duas vezes na 058 — e nesta mesma
spec ela já errou uma vez (a hipótese do tamanho do rótulo, research R1).

DUAS REDAÇÕES para o mesmo fato:

  P1  PASSO PRÓPRIO — o vínculo ganha um passo separado (1c), depois do afeto, dizendo
      que é FATO declarado e distinto do sentimento.
  P2  DENTRO DO AFETO — o vínculo entra como mais um ingrediente do passo 1b, junto do
      saldo, sem passo próprio.

TRÊS CENÁRIOS por redação, e o terceiro é o que importa de verdade:

  a) estranho, sem afeto que pese      <- linha de base
  b) irmão, sem afeto que pese         <- o vínculo sozinho move?
  c) irmão, COM mágoa                  <- OS DOIS EIXOS EM CONFLITO. É a célula que
                                          motivou a spec inteira, e a única que
                                          distingue "o vínculo conta" de "o vínculo
                                          só repete o que o afeto já dizia"

Uso:  python3 tests/exploracao/sondagem_vinculo_regua.py   (exige só o Ollama de pé)
"""
import json
import os
import statistics
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from motor import juizo  # noqa: E402

MODELO, TEMP, R = "llama3.1:8b", 0.2, 5

BASE = """\
Régua da DISPOSIÇÃO A INFORMAR.

PASSO 1 — se houver em "lembra_de_voce" QUALQUER lembrança de violência ou humilhação
sofrida às mãos de quem pergunta, a nota É 0. Ponto final. Quem apanhou não indica
caminho.

PASSO 1b — o mundo já mediu o afeto do informante por quem pergunta e te entrega em
"saldo_afeto". NÃO o recalcule de cabeça. Um saldo negativo puxa a nota para baixo; um
positivo, para cima."""

P1_PASSO_PROPRIO = """
PASSO 1c — o mundo também te entrega o VÍNCULO declarado entre os dois, em "vinculo"
(ex.: "irmã", "padrinho", "primo"). Ele é FATO, não sentimento: um irmão continua irmão
mesmo quando há mágoa entre os dois, e as duas coisas contam JUNTAS, sem uma anular a
outra. Um vínculo de família ou de ofício pesa a favor de atender — não porque o
informante goste, mas porque é o que se deve a um parente."""

P2_DENTRO_DO_AFETO = """
Além do saldo, "vinculo" traz a relação declarada entre os dois (ex.: "irmã",
"padrinho"). Leia os dois juntos ao dimensionar a disposição."""

ESCADA = """
PASSO 2 — dimensione:
  0  não fala com quem pergunta
  5  o caso comum — atende quem pergunta, sem entusiasmo
  10 diria mesmo sem lhe perguntarem
A nota é segredo do mundo."""

FECHO = """
Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"disposicao": <inteiro 0-10>}"""

INFORMANTE = ("Hulda, a Taverneira. Seca canecas atrás do balcão, atenta ao salão. "
              "Direta, pouco dada a conversa fiada.")

CENARIOS = [
    ("a) estranho, sem afeto            ", None, "sem história que pese num sentido ou noutro"),
    ("b) IRMÃ, sem afeto                ", "irmã", "sem história que pese num sentido ou noutro"),
    ("c) IRMÃ + MÁGOA (eixos em conflito)", "irmã", "guarda mágoa"),
]

PROPOSTAS = [
    ("P1  vínculo em PASSO PRÓPRIO", BASE + P1_PASSO_PROPRIO + ESCADA + FECHO),
    ("P2  vínculo DENTRO do afeto ", BASE + P2_DENTRO_DO_AFETO + ESCADA + FECHO),
    ("P0  SEM o vínculo (controle) ", BASE + ESCADA + FECHO),
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
print("A MESMA cena e o MESMO informante nas três linhas. Só a relação muda.\n")

for nome_p, system in PROPOSTAS:
    print(f"--- {nome_p} ---")
    medias = []
    for nome_c, vinculo, saldo in CENARIOS:
        vals = []
        for _ in range(R):
            payload = {"lembra_de_voce": [], "saldo_afeto": saldo,
                       "informante": INFORMANTE,
                       "prosa": "Pergunta onde fica o poço da mina."}
            # No controle o campo nem existe — é o que separa "não leu" de "leu e ignorou"
            if vinculo and not nome_p.startswith("P0"):
                payload["vinculo"] = vinculo
            j = juizo.julgamento(ask(system, json.dumps(payload, ensure_ascii=False,
                                                        indent=2)),
                                 {"disposicao": 5})
            vals.append(j["disposicao"])
        medias.append(statistics.mean(vals))
        print(f"   {nome_c} → {vals}  média {statistics.mean(vals):.1f}")
    print(f"   >> vínculo sozinho move (b−a): {medias[1] - medias[0]:+.1f}")
    print(f"   >> sobrevive à mágoa  (c−a): {medias[2] - medias[0]:+.1f}\n")

print("Leitura: no CONTROLE (P0) as três linhas devem ficar próximas — ele não recebe")
print("o vínculo, então só o afeto pode mover. Se P1/P2 movem (b−a) > 0 e o P0 não, o")
print("vínculo está informando algo que o modelo não inferia sozinho.")
print("A linha (c) é a decisiva: se ela desabar ao nível do afeto puro, os dois eixos")
print("colapsaram na régua — e a ortogonalidade que a spec inteira defende morreu aqui.")
