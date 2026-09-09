"""LABORATÓRIO DE RÉGUA — extração de matéria-prima (`mine`/`chop`/`forage`).

Mede o JUÍZO (o prompt que o corpo da tool manda ao modelo do ÁRBITRO), não a
description. Molde exato de `sondagem_sing_regua.py`: sem server, sem mundo — o
juízo é função pura de prompt->JSON, e o parse medido é o REAL
(`motor.juizo.julgamento`, importado).

A PERGUNTA. A régua de admissão da extração tem DOIS fatores (o alvo e a
ferramenta na mão). Duas formas de perguntar:

  VA  UMA nota composta  — "o quanto ISTO, com ISTO na mão, rende minério"
  VB  DUAS notas         — "o quanto o ALVO tem" + "o quanto a FERRAMENTA serve"

`[[duas-reguas-numa-chamada-a-primeira-vence]]` diz que, com dois eixos numa
resposta só, o segundo é arrastado — então VB é suspeita por construção. Mas VA
só vale se a nota única REALMENTE olhar os dois fatores; se ela ignorar a
ferramenta, é pior que VB.

  VC  UMA nota, contrato CURTO (9 chaves, o tamanho da `forage` de hoje) — o
      CONTROLE de custo: VA/VB pedem 13-14 chaves. Se VC discriminar melhor que
      VA nas mesmas cenas, o preço das chaves extras (renovacao/tamanho/prazo)
      está sendo pago em qualidade de nota.

TRÊS ARMADILHAS entre as seis cenas — é nelas que uma régua ruim se denuncia:
  ★ alvo certo + ferramenta ERRADA   (veio de estanho, colher de pau)
  ★ alvo certo + MÃO VAZIA
  ★ alvo ERRADO + ferramenta certa   (moita de amora, picareta)

E, de brinde na mesma resposta, o segundo experimento:
  RENOVAÇÃO — a nota nova. Um veio de estanho (nunca volta) e uma moita de
  amora (volta em dias) têm que sair separados. Se a nota for sempre a mesma, a
  régua é peso morto e a spec cai para rebrota constante, como a 054 decidiu.

Uso:  python3 tests/exploracao/sondagem_extracao_regua.py
      (exige só o Ollama de pé)
"""
import json
import os
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from motor import juizo  # noqa: E402  — o parse REAL, não uma cópia

# o modelo do ÁRBITRO real (config.server.json), não o da Mente.
MODELO, TEMP, R = "llama3.1:8b", 0.2, 3

# --------------------------------------------------------------------------- #
# As cenas. `esperado` é a FAIXA que um humano diria — mede-se se o modelo
# SEPARA as cenas, nunca se acerta um número exato.
# --------------------------------------------------------------------------- #
VEIO = ("Parede de rocha úmida onde uma veia de estanho aflora, exposta no ponto "
        "em que a pedra lascou. O metal aparece em fios cinzentos, presos fundo.")
ARGILA = ("Barranco de terra batida à beira do riacho, a argila cinzenta exposta "
          "pela enxurrada, lisa e sem pedra dentro.")
AMORA = ("Moita fechada de amoreiras silvestres, os ramos vergados de fruta madura "
         "e as folhas ainda com o orvalho da noite.")
CONVES = ("Convés de tábuas calafetadas, o breu preto nas juntas ainda cheirando "
          "forte. Nem um fio de verde em lugar nenhum.")

PICARETA = ("Picareta de mineiro, o cabo de freixo gasto e o bico de ferro "
            "arredondado de tanto bater na pedra.")
COLHER = "Colher de pau de cozinha, larga e rasa, a borda lascada de tanto mexer panela."

CENAS = [
    # (rótulo, alvo, ferramenta-na-mão, admissão esperada, renovação esperada)
    ("C1 veio de estanho + PICARETA   ", VEIO,   PICARETA, (7, 10), (0, 2)),
    ("C2 veio de estanho + COLHER  ★  ", VEIO,   COLHER,   (0, 2),  (0, 2)),
    ("C3 veio de estanho + MÃO VAZIA ★ ", VEIO,  None,     (0, 1),  (0, 2)),
    ("C4 moita de amora + PICARETA  ★ ", AMORA,  PICARETA, (0, 1),  (7, 10)),
    ("C5 barranco de argila + PICARETA", ARGILA, PICARETA, (5, 9),  (4, 8)),
    ("C6 convés calafetado + PICARETA ", CONVES, PICARETA, (0, 0),  (0, 3)),
]

# --------------------------------------------------------------------------- #
# As réguas
# --------------------------------------------------------------------------- #
_ABERTURA = """\
Você vai julgar UMA tentativa de arrancar matéria MINERAL — pedra, minério,
argila, sal — de um alvo, com o que quem tenta estiver segurando. Leia a
descrição REAL do alvo e da ferramenta com cuidado — nunca invente detalhe que
não esteja nelas."""

# VA — UMA nota composta.
VA_ADMISSAO = """\
Régua da EXTRAIBILIDADE (o quanto ESTE alvo, com ESTA ferramenta na mão, rende
matéria mineral de verdade — os dois fatores juntos, nunca um só):
  0  não sai nada: o alvo não tem mineral nenhum, OU a ferramenta não tem como
     arrancar o que há ali (sem teste)
  1  quase certamente não
  2  muito improvável
  3  duvidoso
  4  incerto
  5  ambíguo — a descrição não decide
  6  provável
  7  bastante provável
  8  evidente: o alvo tem, e a ferramenta é própria para tirar
  9  muito evidente
  10 é exatamente o que se faz com isto ali (sem teste)
OS DOIS FATORES DERRUBAM SOZINHOS. Um alvo rico em minério com uma ferramenta
que não arranca nada dele é nota BAIXA, não alta — a ferramenta errada não
desaparece da leitura por o alvo ser bom. E uma ferramenta perfeita diante de um
alvo sem mineral nenhum também é nota BAIXA. Mão vazia contra pedra é 0.
A nota é segredo do mundo: nunca o número na narrativa; nota 0 recusa a
tentativa."""

# VB — DUAS notas separadas.
VB_ADMISSAO = """\
Régua do ALVO (o quanto, PELA DESCRIÇÃO, há neste alvo matéria mineral que se
possa arrancar — ignorando com o que se vai arrancar):
  0  não há mineral nenhum ali
  5  a descrição não decide
  10 mineral evidente e abundante

Régua da FERRAMENTA (o quanto o que está na mão serve para arrancar mineral —
ignorando o alvo; mão vazia é 0):
  0  não serve para arrancar nada de mineral
  5  serve mal, mas serve
  10 é a ferramenta própria para isso
As notas são segredo do mundo: nunca o número na narrativa."""

RENDIMENTO = """\
Régua do RENDIMENTO (o quanto, PELA ABUNDÂNCIA e ESTADO do que está descrito, há
matéria aproveitável AGORA):
  0  nada aproveitável — esgotado, já revirado, estéril (sem teste)
  3  escasso
  5  comum — algo se aproveita, sem fartura
  8  farto
  10 fartura densa (sem teste)
A nota é segredo do mundo. Entre 1 e 9 há um teste resolvido no Motor."""

RENOVACAO = """\
Régua da RENOVAÇÃO (o quanto ESTE alvo volta a render sozinho, com o tempo,
depois de ser extraído — julgue a NATUREZA do alvo, nunca a pressa de quem
extrai):
  0  nunca volta: uma veia de metal arrancada não se refaz, um bloco de pedra
     tirado não cresce de novo
  3  volta em anos — uma árvore antiga, um barranco que a chuva reconstrói devagar
  5  volta em estações
  8  volta em dias
  10 volta em horas — folha, broto, mato rasteiro
A nota é segredo do mundo. O Motor a converte num tempo real; nota 0 significa
que o alvo fica esgotado PARA SEMPRE."""

TAMANHO = """\
Régua do TAMANHO físico de cada porção extraída (a escala do mundo, do menor ao
maior): "PP", "P", "M", "G", "XG". Um punhado de minério ou um torrão de argila
é P; uma laje ou um bloco de pedra é G."""

BANDAS = """\
A rolagem que decide a banda final (pobre/comum/rica) acontece DEPOIS desta
resposta, no Motor — você não sabe qual vai sair. Por isso escreva TRÊS pares de
nome+descrição: o QUE SAIU do alvo em cada banda, nunca o alvo de onde saiu.
  pobre: o que mãos desajeitadas trariam
  comum: o que uma extração comum rende
  rica:  o que alguém que conhece a matéria traria daqui
O NOME é sempre da coisa extraída, nunca do alvo. ERRADO: extrair da "Veia de
Estanho" e nomear "Veia de Estanho". CERTO: "Pedaço de Estanho Bruto".

Escreva também `descricao_extraida`: o que ESTE alvo passaria a dizer de si logo
depois de ser trabalhado."""

PRAZO = """\
Escreva `urgencia` e `descricao_vencida` SOMENTE se o que foi extraído se
deteriora sozinho com o tempo (folha murcha, fruta apodrece). Pedra, metal,
argila e madeira NÃO se deterioram: para eles, devolva as duas chaves com string
VAZIA."""

_JSON_COMPLETO = ('{%s, "rendimento": <inteiro 0-10>, "renovacao": <inteiro 0-10>, '
                  '"tamanho": "<PP|P|M|G|XG>", '
                  '"nome_pobre": "<nome curto>", "descricao_pobre": "<texto factual>", '
                  '"nome_comum": "<nome curto>", "descricao_comum": "<texto factual>", '
                  '"nome_rica": "<nome curto>", "descricao_rica": "<texto factual>", '
                  '"descricao_extraida": "<texto factual do alvo depois>", '
                  '"urgencia": "<uma frase, ou vazio>", '
                  '"descricao_vencida": "<texto factual, ou vazio>"}')

_JSON_CURTO = ('{"extraibilidade": <inteiro 0-10>, "rendimento": <inteiro 0-10>, '
               '"nome_pobre": "<nome curto>", "descricao_pobre": "<texto factual>", '
               '"nome_comum": "<nome curto>", "descricao_comum": "<texto factual>", '
               '"nome_rica": "<nome curto>", "descricao_rica": "<texto factual>", '
               '"descricao_extraida": "<texto factual do alvo depois>"}')

_FECHO = """\
Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE com estas
chaves (todas OBRIGATÓRIAS):

%s"""


def _monta(admissao, extras, contrato):
    return "\n\n".join([_ABERTURA, admissao, RENDIMENTO] + extras
                       + [BANDAS, _FECHO % contrato])


VARIANTES = [
    ("VA nota unica  (13 chaves)",
     _monta(VA_ADMISSAO, [RENOVACAO, TAMANHO, PRAZO],
            _JSON_COMPLETO % '"extraibilidade": <inteiro 0-10>'),
     {"extraibilidade": 5, "rendimento": 5, "renovacao": 5},
     ("extraibilidade",)),
    ("VB duas notas  (14 chaves)",
     _monta(VB_ADMISSAO, [RENOVACAO, TAMANHO, PRAZO],
            _JSON_COMPLETO % '"alvo": <inteiro 0-10>, "ferramenta": <inteiro 0-10>'),
     {"alvo": 5, "ferramenta": 5, "rendimento": 5, "renovacao": 5},
     ("alvo", "ferramenta")),
    ("VC nota unica  ( 9 chaves)",
     _monta(VA_ADMISSAO, [], _JSON_CURTO),
     {"extraibilidade": 5, "rendimento": 5},
     ("extraibilidade",)),
]

_TEXTOS = {"tamanho": "", "nome_pobre": "", "descricao_pobre": "",
           "nome_comum": "", "descricao_comum": "", "nome_rica": "",
           "descricao_rica": "", "descricao_extraida": "",
           "urgencia": "", "descricao_vencida": ""}


def payload(alvo, ferramenta):
    p = {"onde": {"descricao": alvo},
         "ferramenta": ({"descricao": ferramenta} if ferramenta
                        else "nada nas mãos — mãos vazias")}
    return json.dumps(p, ensure_ascii=False, indent=2)


def ask(system, user):
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": TEMP},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return ((r.get("message") or {}).get("content") or "")


def _presentes(raw, chaves):
    """Quais chaves o modelo REALMENTE devolveu (o `julgamento` mascara ausência
    com default — aqui se mede a ausência, que é o custo do contrato longo)."""
    i, f = raw.find("{"), raw.rfind("}")
    if i == -1 or f <= i:
        return set()
    try:
        obj = json.loads(raw[i:f + 1])
    except ValueError:
        return set()
    return {k for k in chaves if k in obj} if isinstance(obj, dict) else set()


def faixa(v, lo, hi):
    return "ok " if lo <= v <= hi else "XX "


def main():
    todas = ["extraibilidade", "alvo", "ferramenta", "rendimento", "renovacao",
             "tamanho", "nome_pobre", "nome_comum", "nome_rica",
             "descricao_extraida", "urgencia", "descricao_vencida"]
    print(f"modelo={MODELO} temp={TEMP} repeticoes={R} "
          f"cenas={len(CENAS)} variantes={len(VARIANTES)}")
    print("=" * 100)
    resumo = {}
    for vnome, system, campos, chaves_adm in VARIANTES:
        print(f"\n### {vnome}\n")
        acertos, falhas_chave, tempos = 0, 0, []
        for rot, alvo, ferr, (lo, hi), (rlo, rhi) in CENAS:
            adms, renos, tams, vazios = [], [], [], 0
            for _ in range(R):
                t0 = time.time()
                raw = ask(system, payload(alvo, ferr))
                tempos.append(time.time() - t0)
                j = juizo.julgamento(raw, campos=campos, texto_campos=_TEXTOS)
                pres = _presentes(raw, todas)
                falhas_chave += len([c for c in campos if c not in pres])
                # a nota de ADMISSÃO: em VB, o mínimo dos dois eixos é o que a
                # tool usaria como gate (qualquer um em 0 recusa).
                adms.append(min(j[c] for c in chaves_adm))
                if "renovacao" in campos:
                    renos.append(j["renovacao"])
                tams.append(j.get("tamanho") or "-")
                if not (j.get("urgencia") or "").strip():
                    vazios += 1
            med = statistics.median(adms)
            ok = faixa(med, lo, hi)
            acertos += 1 if ok == "ok " else 0
            linha = (f"  {rot} adm={adms} med={med:>4} esp={lo}-{hi} {ok}")
            if renos:
                rmed = statistics.median(renos)
                linha += f"| renov={renos} med={rmed:>4} esp={rlo}-{rhi} {faixa(rmed, rlo, rhi)}"
            linha += f"| tam={tams} prazo_vazio={vazios}/{R}"
            print(linha)
        resumo[vnome] = (acertos, len(CENAS), falhas_chave,
                         round(statistics.mean(tempos), 1))
        print(f"  -> {acertos}/{len(CENAS)} cenas na faixa | "
              f"{falhas_chave} chaves de nota ausentes | "
              f"{resumo[vnome][3]}s/chamada")

    print("\n" + "=" * 100)
    print("RESUMO")
    for v, (a, t, fk, seg) in resumo.items():
        print(f"  {v}: {a}/{t} cenas na faixa | {fk} chaves ausentes | {seg}s/chamada")


if __name__ == "__main__":
    main()
