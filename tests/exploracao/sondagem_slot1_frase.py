"""A UNIDADE DO SLOT MORTO: é a primeira PESSOA ou a primeira FRASE? (spec 066, T019)

`sondagem_posicao_vinculo.py` achou que o primeiro item do trecho social se perde (0/6
contra 6/6 nas posições 2 e 3), e `sondagem_slot1_causa.py` provou que é ordem de LEITURA,
não do harness.

Sobrou a pergunta que decide o CONSERTO, e ela nasceu de uma observação na sondagem
original: a entrada da Hulda era

    "Hulda, irmã de criação. Você guarda mágoa dela."

e ela perdeu o VÍNCULO (1ª frase) mantendo o AFETO (2ª frase) — dentro da MESMA entrada,
da MESMA pessoa. Se o que morre é a primeira FRASE e não a primeira PESSOA, o conserto é
barato e honesto: **abrir o trecho com uma frase que não carrega informação**, e nada mais
muda.

Se for a primeira PESSOA, não há conserto de redação — a composição terá que ORDENAR
pondo em primeiro quem se pode perder, o que é CONTORNAR o defeito, e a spec exige que
isso fique registrado no código.

Três variantes, todas medindo o VÍNCULO da primeira pessoa:

  V0  primeira pessoa, vínculo na 1ª frase          <- o caso original
  V1  primeira pessoa, vínculo na 2ª frase (afeto primeiro)
  V2  trecho aberto por uma FRASE DE ABERTURA sem informação, vínculo logo depois

V1 alto  -> a unidade é a FRASE, e inverter a ordem interna já resolve.
V2 alto  -> a unidade é a FRASE, e a abertura vazia resolve (o conserto preferido:
            não mexe na ordem das pessoas, que carrega significado).
os dois baixos -> a unidade é a PESSOA, e só ordenar resolve.

RESULTADO (2026-09-05, 8 rodadas por variante, e ele NÃO fecha numa regra):

    V0  vínculo na 1ª frase (aposto)                   0/8
    V1  AFETO na 1ª frase, vínculo em aposto depois    6-8/8   <- vence
    V2  abertura vaga ocupando o slot                  0-1/8
    V3  abertura concreta ocupando o slot              0-1/8
    V4  pior caso (só vínculos, apostos)               0-1/8
    V5  vínculo como oração plena, 1º, com afeto após  1-3/8
    V6  pior caso com TODAS as entradas em oração      6-8/8   <- vence
    V7  produção: oração plena, vínculo antes do afeto 0-1/8
    V8  combinada: oração plena + vínculo por último   3/8

DUAS VARIANTES VENCEM, E ELAS SÃO ESTRUTURALMENTE OPOSTAS (V1 usa aposto, V6 usa
oração plena). Cada mecanismo proposto foi falsificado pela variante seguinte:

  "é a primeira FRASE"          -> V2/V3 deveriam salvar. Não salvam.
  "é o aposto após dois-pontos" -> V5 deveria salvar. Não salva.
  "vence o que se diz por último" -> V8 deveria salvar. Não salva.

**O MECANISMO NÃO ESTÁ IDENTIFICADO, e parar aqui é a decisão.** Com n=8 e desfecho
binário o intervalo é largo, e continuar a variar produziria uma regra de desenho que a
medição seguinte derruba — foi exatamente assim que a hipótese do TAMANHO do rótulo
nasceu e morreu (research R1).

E há uma ressalva maior, que vale mais que o número: **a métrica é um PROXY não
validado.** Ela pergunta se o modelo ECOA a palavra do vínculo numa frase de reação por
pessoa — mas o jogo real não pede isso. Ele pede que A Mente ESCOLHA UMA AÇÃO. Um vínculo
não ecoado numa frase descartável não é necessariamente um vínculo não lido. Ligar este
proxy à decisão real exige outra sondagem, sobre escolha de ação, e ela não foi feita.

O QUE FOI ADOTADO: a forma do V1 — a frase de AFETO antes, o vínculo em aposto depois —
por ser o vencedor reprodutível em três execuções. Não porque o mecanismo se entendeu.

Uso:  python3 tests/exploracao/sondagem_slot1_frase.py   (exige só o Ollama de pé)
"""
import json
import re
import urllib.request

MODELO, TEMP, R = "llama3.1:8b", 0.4, 8

LOCAL = {"nome": "Praça do Mercado",
         "descricao": ("Bancas de pano puxado, cheiro de peixe seco e especiaria. "
                       "O sol já está alto e o movimento é grande.")}

NOMES = ["Renn", "Hulda", "Doncel", "Bram"]
ALVO = "Renn"                      # sempre o PRIMEIRO da lista
VINCULO, AFETO = "irmã", "guarda mágoa"
NUCLEO = re.compile(r"irm[ãa]", re.I)
NEUTRO = "conhecido de vista"

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

RESTO = " ".join(f"{n}, {NEUTRO}." for n in NOMES[1:])


def v0():   # vínculo na 1ª frase do trecho
    return (f"Quem lhe diz alguma coisa aqui: {ALVO}, {VINCULO}. "
            f"Você {AFETO} dele. {RESTO}")


def v1():   # afeto na 1ª frase, vínculo na 2ª — mesma pessoa, ordem interna trocada
    return (f"Quem lhe diz alguma coisa aqui: Você {AFETO} de {ALVO}. "
            f"{ALVO}, {VINCULO}. {RESTO}")


def v2():   # uma frase de ABERTURA sem informação ocupa o slot morto
    return (f"Quem lhe diz alguma coisa aqui: Algumas destas pessoas lhe são próximas. "
            f"{ALVO}, {VINCULO}. Você {AFETO} dele. {RESTO}")


def v3():   # abertura CONCRETA (nomeia o lugar) — V2 era vaga; testa se o que conta
            # é a frase anterior ser de conteúdo real, não só existir
    return (f"Quem lhe diz alguma coisa aqui, na Praça do Mercado, num dia de "
            f"movimento: {ALVO}, {VINCULO}. Você {AFETO} dele. {RESTO}")


def v4():   # PIOR CASO: ninguém tem afeto, só vínculos. Não há frase de afeto para
            # pôr antes, e é o caso que a regra de composição precisa cobrir.
    return (f"Quem lhe diz alguma coisa aqui: {ALVO}, {VINCULO}. "
            f"Hulda, primo. Doncel, padrinho. {NOMES[3]}, {NEUTRO}.")


def v5():   # o vínculo como ORAÇÃO PLENA, não aposto. Hipótese: "Renn, irmã." logo
            # depois dos dois-pontos é lido como continuação do cabeçalho; uma oração
            # com sujeito e verbo não seria. Sem possessivo ambíguo ("sua" é dele/dela
            # OU de você) — a 2ª pessoa fica explícita em "Você e X são".
    return (f"Quem lhe diz alguma coisa aqui: Você e {ALVO} são irmãos. "
            f"Você {AFETO} dele. {RESTO}")


def v6():   # o PIOR CASO com a forma do V5 — é o que decide se há conserto geral
    return (f"Quem lhe diz alguma coisa aqui: Você e {ALVO} são irmãos. "
            f"Você e Hulda são primos. Doncel é seu padrinho. {NOMES[3]}, {NEUTRO}.")


def v7():   # A FORMA DE PRODUÇÃO: todas as entradas em oração plena, misturando
            # vínculo e afeto, e OMITINDO quem não qualifica (Bram sai). É esta que
            # a composição do conector vai emitir — mede-se o que se vai enviar.
    return ("Quem lhe diz alguma coisa aqui: "
            f"Você e {ALVO} são irmãos. Você {AFETO} dele. "
            "Você e Hulda são primos. "
            "Você nutre forte estima de Doncel.")


def v8():   # A REGRA COMBINADA. Cruzando V0/V1/V7 aparece que, dentro da entrada de
            # UMA pessoa, vence o que se diz por ÚLTIMO; e cruzando V4/V6, que o aposto
            # logo após os dois-pontos se perde e a oração plena não. As duas juntas:
            # oração plena SEMPRE, e o vínculo depois do afeto.
    return ("Quem lhe diz alguma coisa aqui: "
            f"Você {AFETO} de {ALVO}. Você e {ALVO} são irmãos. "
            "Você e Hulda são primos. "
            "Você nutre forte estima de Doncel.")


VARIANTES = [
    ("V0  vínculo na 1ª frase (o caso original)", v0),
    ("V1  afeto na 1ª frase, vínculo na 2ª", v1),
    ("V2  abertura VAGA ocupa o slot", v2),
    ("V3  abertura CONCRETA ocupa o slot", v3),
    ("V4  PIOR CASO: só vínculos, nenhum afeto", v4),
    ("V5  vínculo como ORAÇÃO PLENA, não aposto", v5),
    ("V6  PIOR CASO com oração plena", v6),
    ("V7  A FORMA DE PRODUÇÃO (oração plena, mista, sem os que não pesam)", v7),
    ("V8  REGRA COMBINADA: oração plena + vínculo por ÚLTIMO na entrada", v8),
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


def montar(social):
    return json.dumps({
        "lugar": LOCAL,
        "contexto_social": social,
        "presentes": [{"nome": n, "fazendo": "circula entre as bancas"} for n in NOMES],
    }, ensure_ascii=False, indent=2)


print(f"modelo={MODELO} temp={TEMP} rodadas={R}")
print(f"Mede o VÍNCULO de {ALVO} (sempre o 1º da lista). Muda só onde a frase cai.\n")

ask(SYSTEM, montar(v0()))          # aquecimento

for nome_v, montar_social in VARIANTES:
    acertos, validas = 0, 0
    for _ in range(R):
        resp = parse(ask(SYSTEM, montar(montar_social())))
        if not resp:
            continue
        validas += 1
        if NUCLEO.search(resp.get(ALVO, "") or ""):
            acertos += 1
    print(f"{nome_v}: {acertos}/{validas}  {'#' * acertos}")

print("\nV1 ou V2 alto -> a unidade é a FRASE; há conserto de redação.")
print("V2 é o conserto PREFERIDO: não mexe na ordem das pessoas, que carrega")
print("significado, e não exige que a composição saiba o que 'se pode perder'.")
print("Os dois baixos -> a unidade é a PESSOA, e só ordenar resolve (contorno).")
