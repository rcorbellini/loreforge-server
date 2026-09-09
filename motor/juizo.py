"""O Motor / juizo — a primitiva do JUÍZO (spec 043). NÍVEL 0.

O VOCABULÁRIO compartilhado de quem pergunta uma nota ao mundo — e só ele. O
PROCEDIMENTO (que payload montar, que régua usar, que default adotar) é de CADA
capacidade, porque cada régua lê coisas diferentes: a do furto lê a descrição do item
e a atenção do dono; a da disposição a informar lê o que o informante guarda de quem
pergunta. Não existe payload genérico correto, e um helper que tentasse montá-lo
rachar-ia o contrato da capacidade entre dois arquivos.

Aqui mora o que NÃO pode divergir entre capacidades: a frase que pede a nota (para
que a taxa de acerto do parse seja comparável entre elas) e o parse em si.

Puro: sem I/O, sem modelo, sem conhecer tool. Roda no selftest sem runtime nenhum —
que é o motivo de o transporte (`ctx.ask`) ser injetado e não importado.
"""
from __future__ import annotations

import json as _json
import re

# A frase canônica. Toda capacidade julgada compõe a SUA régua com esta — se cada uma
# inventasse a própria ("responda com número", "de 0 até 10", "apenas o número"), as
# taxas de parse divergiriam entre capacidades sem ninguém perceber.
NOTA_0_10 = "\n\nResponda APENAS com um número inteiro de 0 a 10, nada mais."

_PRIMEIRO_NUMERO = re.compile(r"-?\d+")

# O TERCEIRO ESTADO (spec 071): não há modelo ligado. É o que `arbiter._sem_juizo`
# devolve, e SÓ acontece no arnês de teste — em produção `ctx.ask` é sempre o
# transporte real, e a pane dele vira string vazia, que É ausência e recusa.
#
# Precisa de um valor PRÓPRIO, e não da string vazia que usava antes, porque a 071
# passou a distinguir "não julgou" de "julgou": sem isto, todo selftest que exercita
# uma capacidade julgada sem scriptar juízo passaria a recusar — e a suíte estaria
# medindo o arnês, não o jogo. Com isto, cada capacidade cai no PRÓPRIO default,
# exatamente como antes desta spec (o neutro do golpe não é o neutro da troca).
#
# É deliberadamente impronunciável por um modelo: nenhuma resposta real coincide.
SEM_MODELO = "\x00sem-modelo-ligado\x00"


class NaoJulgado(Exception):
    """O mundo perguntou e NINGUÉM julgou (spec 071, US1).

    Não é "julgou torto": é resposta que não permite extrair juízo nenhum — o
    modelo recusou o tema, desistiu, ou o transporte devolveu vazio.

    POR QUE ISTO EXISTE. Antes da 071, essas respostas caíam no default da
    capacidade — tipicamente `5`. Como TODO gate do projeto é `nota == 0`, uma
    recusa virava "prossiga com nota média": a ação acontecia sem ninguém ter
    julgado, e o jogador lia um efeito que o mundo nunca decidiu (Princípio X,
    metade "o player NUNCA lê um efeito que não houve"). E era invisível: uma
    recusa é HTTP 200 sem JSON, então o `JUÍZO FALHOU` de `app.py` — que só
    dispara em exceção de runtime — nunca acusava. Medido: 8 em 108 chamadas ao
    modelo real (~7%), concentradas nas réguas mais carregadas.

    A FRONTEIRA, e ela é estreita de propósito (FR-006):

        AUSENTE  nenhum juízo legível          -> levanta daqui
        PARCIAL  juízo legível, chave faltando -> default por campo, como sempre

    Alargar para "qualquer chave faltando é falha" seria outra feature, com risco
    próprio e sem medição por trás. O que foi medido é a ausência total.

    O TERCEIRO ESTADO, e é ele que justifica `SEM_MODELO` abaixo. "Não há modelo
    ligado" NÃO é "o modelo não julgou": o primeiro só existe no arnês de teste (em
    produção há sempre um runtime, e quando ele falha o `build_ask` captura a
    exceção, registra em `juizo_falhas` e devolve vazio — que É ausência, e recusa
    com razão). Antes da 071 os dois estados eram a mesma string vazia, e foi isso
    que fez metade da suíte exercitar capacidades julgadas com nota de default sem
    ninguém perceber.

    QUEM TRATA. Ninguém, aqui embaixo. Ela sobe pelo corpo da capacidade e é
    convertida em RECUSA (`juizo_ausente`) num ponto único, `arbiter.py::_execute`
    — o despacho por onde toda tool passa. É o que faz as 19 chamadas de juízo do
    projeto ficarem cobertas por uma edição só, e a 20ª nascer coberta. Nenhuma
    capacidade deve capturar isto: capturar é reintroduzir o defeito.
    """


def _sanear_quebras_em_string(bruto: str) -> str:
    """Escapa `\\n`/`\\r`/`\\t` CRUS que estejam DENTRO de uma string JSON, antes
    do parse (spec 058, FR-013).

    O DEFEITO QUE ISTO CONSERTA. Pedida uma letra de canção em quatro versos, o
    modelo devolve algo como `{"letra": "verso um,\\nverso dois"}` — quebra de
    linha CRUA dentro da string, JSON tecnicamente inválido. `json.loads` falha,
    `julgamento` cai no default, e a resposta inteira SOME em silêncio: medido,
    8 de 8 respostas de um contrato inteiro perdidas assim (research.md da spec
    058, M4). Nenhuma capacidade anterior tinha pedido texto multi-linha — as
    outras (`cook`, `brew`...) pedem parágrafo único e nunca esbarraram nisto.

    Percorre caractere a caractere respeitando escape (`\\`) e o estar-dentro-de-
    string (aspas não-escapadas alternam o estado); fora de string (a
    indentação do objeto) NUNCA é tocado. Não conserta uma resposta TRUNCADA
    (o objeto nunca fecha) — não há o que salvar aí, e inventar seria alucinar
    conteúdo; essa cai no default como sempre (FR-015).
    """
    saida: list[str] = []
    dentro_de_string = False
    escapado = False
    for ch in bruto:
        if escapado:
            saida.append(ch)
            escapado = False
            continue
        if ch == "\\":
            saida.append(ch)
            escapado = True
            continue
        if ch == '"':
            dentro_de_string = not dentro_de_string
            saida.append(ch)
            continue
        if dentro_de_string and ch in "\n\r\t":
            saida.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[ch])
            continue
        saida.append(ch)
    return "".join(saida)


def nota(raw: str, default: int) -> int:
    """A nota que o mundo leu, grampeada em 0-10.

    `default` é da CAPACIDADE, não desta primitiva: o neutro do golpe (combate limpo)
    não é o neutro da troca (o padrão é NÃO negociar). Quem sabe disso é a régua, e a
    régua mora com a tool.

    Resposta SEM NÚMERO NENHUM não é "respondeu torto" — é não ter respondido, e
    levanta `NaoJulgado` (spec 071). O default seguia valendo para o que É juízo mas
    veio estranho (um inteiro absurdamente grande), porque aí houve resposta: o turno
    já mexeu no mundo quando chega aqui, e derrubá-lo por isso seria trocar o certo
    pelo cosmético — mesmo tratamento que `attack` já dava a uma nota inválida.

    MEDIDO antes de escolher a regra (spec 071, research R9): das 8 respostas sem
    juízo capturadas do modelo real, **8 não contêm nenhum algarismo**. A regra
    simples cobre as oito; endurecer além disso seria complexidade especulativa.
    """
    if raw == SEM_MODELO:         # arnês sem modelo: default, como antes da 071
        return default
    achado = _PRIMEIRO_NUMERO.search(raw or "")
    if achado is None:
        raise NaoJulgado("resposta sem número")
    try:
        return max(0, min(10, int(achado.group())))
    except ValueError:            # inteiro absurdamente grande: houve juízo, veio torto
        return default


def julgamento(raw: str, campos: dict, texto_campos: dict[str, str] | None = None) -> dict:
    """Várias notas NOMEADAS (e, opcionalmente, um ou mais textos) na MESMA
    resposta — UMA chamada ao modelo em vez de uma por eixo (spec 046, `eat`:
    quatro julgamentos independentes por ato tornavam a ação lenta e cara; o
    custo é a prioridade sobre isolar cada régua na própria chamada).

    `campos` = `{chave: default}` — cada valor sai grampeado em 0-10, ou cai no
    PRÓPRIO default se ausente/ilegível (mesma disciplina do `nota()`, por
    campo). `texto_campos` = `{chave: default}` de texto livre, se houver —
    generalizado de um texto único (spec 046/047) para VÁRIOS (spec 048,
    `cook`: três descriptions candidatas, uma por banda, porque a banda só se
    decide DEPOIS da rolagem — nenhuma sabida no momento desta chamada).
    `eat`/`drink` migraram para a forma nova no mesmo commit (mesmo espírito da
    migração de `ToolSpec.juizo` para tupla de pares, spec 046 R2): uma forma
    só, nunca um texto singular E um dict convivendo.

    Formato canônico: JSON com as chaves exatas de `campos`/`texto_campos` —
    pedido explicitamente no prompt da capacidade. MEDIDO (spec 046, sondagem
    real): pedir ao modelo pra responder um formato livre (nota numa linha,
    texto na outra) é o que falha — o modelo já quer responder em JSON por
    conta própria; brigar com isso é que quebra. Pedindo o JSON com o schema
    explícito, a taxa de acerto medida foi 9 de 9 (e, para 3 textos candidatos
    na mesma resposta — spec 048 — 3 de 3 na sondagem real).

    Antes do parse, SANEIA quebras de linha cruas dentro de string (spec 058,
    `_sanear_quebras_em_string`) — necessário desde que uma capacidade (`sing`)
    passou a pedir texto multi-linha; byte-idêntico para toda resposta que já
    era válida (uma linha, texto antes/depois do objeto, `\\n` já escapado)."""
    campos_texto = texto_campos or {}
    resultado = dict(campos)
    resultado.update(campos_texto)
    if raw == SEM_MODELO:         # arnês sem modelo: defaults, como antes da 071
        return resultado
    bruto = _sanear_quebras_em_string((raw or "").strip())
    # spec 071: os TRÊS caminhos abaixo são AUSÊNCIA de juízo — não há objeto, ou o
    # que há não é legível, ou não é um mapa. Antes devolviam os defaults em
    # silêncio, e o gate `nota == 0` deixava a ação passar com nota média.
    inicio, fim = bruto.find("{"), bruto.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise NaoJulgado("resposta sem objeto JSON")
    try:
        obj = _json.loads(bruto[inicio:fim + 1])
    except ValueError:
        raise NaoJulgado("objeto JSON ilegível") from None
    if not isinstance(obj, dict):
        raise NaoJulgado("juízo não é um mapa")
    # DAQUI PARA BAIXO É O CAMINHO PARCIAL, e ele NÃO muda (FR-006): houve juízo,
    # e cada chave ausente ou de tipo errado cai no default da CAPACIDADE, que é
    # quem sabe o neutro do seu eixo (o do golpe não é o da troca).
    for chave, default in campos.items():
        v = obj.get(chave)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            resultado[chave] = max(0, min(10, int(v)))
    for chave in campos_texto:
        v = obj.get(chave)
        if isinstance(v, str) and v.strip():
            resultado[chave] = v.strip()
    return resultado
