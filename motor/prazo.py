"""O Motor / prazo (spec 070) — O RELÓGIO QUE CORRE SOZINHO, e o que acontece quando ele
para.

NÍVEL 0 quanto a decisão: as funções de leitura são puras (bloco + `agora`) e rodam sem
tocar disco. O APLICADOR toca disco, porque vencer é mutação — mas só compõe primitivas
que já existem, nunca reimplementa nenhuma (Princípio XII).

POR QUE ESTE MÓDULO EXISTE. `motor/trabalho.py` já tinha os DOIS relógios do jogo, e a
distinção entre eles é o coração da feature:

    por_esforco  (`tempo_necessario_s`)  só avança COM ALGUÉM PRESENTE trabalhando
    por_prazo    (`pronto_ts`)           corre SOZINHO

Só que o segundo vivia dentro do bloco `trabalho` de uma peça em processo — quer dizer, o
mundo sabia fazer o tempo passar para uma panela no fogo e não sabia fazer o pão mofar.
Aqui o relógio que corre sozinho ganha um bloco que QUALQUER entidade pode carregar.

A DOR, medida em campo (Draven, 2026-09-07, 265 turnos em 16 h): ele começou a consertar
um alaúde que exige 1800 s de esforço, trabalhou 11,5 s e nunca voltou. Nada no mundo
vencia, nada apertava, nada cobrava por não voltar — e sem custo de tempo não existe custo
de oportunidade, logo não existe escolha.

AS DUAS RESTRIÇÕES DURAS, e elas explicam quase todo o desenho abaixo:

1. **Vencer não chama modelo.** Uma chamada de Árbitro por leitura é proibitiva, e o
   cenário que mata é banal: uma cena com dez coisas vencidas custaria dez chamadas numa
   LEITURA. Por isso o que vencer SIGNIFICA é decidido uma vez, na criação, e gravado —
   `urgencia` e `descricao_vencida` vêm do Árbitro junto com as descrições que ele já
   escreve. Vencer é trocar uma string.
2. **Preguiçoso, nunca processo de fundo** (Princípio VII). Não há varredura periódica: o
   vencimento é calculado quando alguém olha, e o resultado é o mesmo tenha havido zero ou
   mil leituras no intervalo.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import io

BLOCO = "prazo"

# --------------------------------------------------------------------------- #
# O vocabulário fechado de consequência (spec 070, research.md R1)
# --------------------------------------------------------------------------- #
#
# QUATRO verbos, e nenhum deles é novo: três são as primitivas de estado que a auditoria
# do item 28 extraiu, e o quarto não escreve estado nenhum — troca texto.
#
# A lista é FECHADA porque quem escolhe o verbo é o Árbitro, lendo a prosa da entidade.
# Deixá-lo escolher entre "qualquer op do Motor" seria superfície grande demais para uma
# decisão de LLM — é a primeira das três camadas de contenção que o Princípio XI exige
# quando prosa vira efeito: enum de alternativas REAIS.
VERBOS = ("condicao", "campo", "extinguir", "virar")

_EXIGE = {
    "condicao": ("valor",),          # o nome da condição a pôr
    "campo": ("campo", "valor"),     # o caminho e o valor
    "extinguir": (),
    "virar": (),                     # usa `descricao_vencida`, validado à parte
}


def forma_valida(bloco) -> str | None:
    """O bloco está bem formado? Devolve o MOTIVO quando não — nunca só `False`.

    Um prazo mal formado que vence e não faz nada é falha SILENCIOSA, a família de
    defeito que mais custou a este projeto (a spec 067 sozinha rendeu três). Por isso a
    validação devolve texto e o `validator` a reporta em vez de ignorar.
    """
    if not isinstance(bloco, dict):
        return "o bloco `prazo` não é um mapa"
    if not isinstance(bloco.get("vence_em"), (int, float)):
        return "`prazo.vence_em` ausente ou não numérico"
    ao = bloco.get("ao_vencer")
    if not isinstance(ao, dict):
        return "`prazo.ao_vencer` ausente ou não é um mapa"
    verbo = ao.get("verbo")
    if verbo not in VERBOS:
        return f"verbo `{verbo}` fora do vocabulário {list(VERBOS)}"
    for chave in _EXIGE[verbo]:
        if ao.get(chave) in (None, ""):
            return f"verbo `{verbo}` exige `{chave}`"
    if verbo == "virar" and not (bloco.get("descricao_vencida") or "").strip():
        return "verbo `virar` exige `prazo.descricao_vencida`"
    return None


# --------------------------------------------------------------------------- #
# Leitura — pura, avaliada no momento da pergunta (Princípio VII)
# --------------------------------------------------------------------------- #

def tem_prazo(fm: dict) -> bool:
    return isinstance((fm or {}).get(BLOCO), dict)


def ja_venceu(bloco: dict, agora: float | None = None) -> bool:
    """O prazo passou? Só isso — não diz se a consequência já foi aplicada."""
    if not isinstance(bloco, dict):
        return False
    if agora is None:
        agora = time.time()
    return agora >= (bloco.get("vence_em") or 0)


def pendente(bloco: dict, agora: float | None = None) -> bool:
    """Venceu E ainda não foi aplicado. É esta a pergunta do caminho de leitura.

    `vencido_em` preenchido é fato consumado: nenhuma comparação posterior o desfaz, e é
    isso que torna um relógio de sistema andando para trás inofensivo (FR-014).
    """
    if not isinstance(bloco, dict) or bloco.get("vencido_em"):
        return False
    return ja_venceu(bloco, agora)


def restante_s(bloco: dict, agora: float | None = None) -> float:
    """Quanto falta, em segundos. Nunca negativo. SEGREDO DO MUNDO — não desce ao
    contexto (Princípio V); serve a régua e a decisão do Motor."""
    if not isinstance(bloco, dict):
        return 0.0
    if agora is None:
        agora = time.time()
    return max(0.0, (bloco.get("vence_em") or 0) - agora)


# --------------------------------------------------------------------------- #
# Escrita — vencer
# --------------------------------------------------------------------------- #

def carimbar(pasta: Path, dura_s: float, ao_vencer: dict,
             urgencia: str = "", descricao_vencida: str = "",
             filename: str = "item.md", agora: float | None = None) -> None:
    """Nasce o prazo. A DURAÇÃO é relativa; o INSTANTE é o que fica gravado.

    A distinção não é preciosismo (FR-005): um arquivo editorial escrito hoje e jogado
    daqui a três meses não pode nascer vencido. O autor escreve quanto DURA; quem carimba
    quando VENCE é o Motor, no momento em que a coisa entra em jogo.
    """
    if agora is None:
        agora = time.time()
    fm, corpo = io.read_doc(pasta / filename)
    fm[BLOCO] = {
        "vence_em": agora + float(dura_s),
        "ao_vencer": dict(ao_vencer or {}),
        "urgencia": urgencia or "",
        "descricao_vencida": descricao_vencida or "",
        "vencido_em": None,
    }
    io.write_doc(pasta / filename, fm, corpo)


# --------------------------------------------------------------------------- #
# O ATALHO QUE TODA CAPACIDADE QUE CRIA COISA USA
# --------------------------------------------------------------------------- #

# Quanto a JANELA DE RETOMADA é maior que o esforço que a peça exige. Quem larga uma obra
# de trinta minutos tem uma hora e meia para voltar.
#
# CALIBRAGEM, não desenho — o número certo se descobre jogando, e este é conservador de
# propósito: janela curta demais vira armadilha, e a spec 070 avisa que punir por algo que
# a Mente não alcança é o modo de falha a evitar. Vive aqui, num lugar só, para não virar
# cinco constantes divergentes espalhadas pelas capacidades.
JANELA_POR_ESFORCO = 3.0


def carimbar_se_houver(pasta: Path, dados: dict, dura_s: float,
                       verbo: dict | None = None, filename: str = "item.md") -> bool:
    """Carimba o prazo SE o Árbitro tiver escrito a descrição pós-vencimento.

    O ponto único que todas as capacidades criadoras chamam — `craft`, `forja`, `cozinha`,
    `botica`, `forage`, `butcher`. Sem ele, cada uma repetiria as mesmas quatro linhas e
    elas divergiriam no dia em que uma fosse calibrada (Princípio I).

    **Sem `descricao_vencida`, não carimba** — e isso não é defensividade, é a regra: sem
    ela não há o que a coisa VIRA, e um prazo que vence sem consequência é pior que prazo
    nenhum. Um modelo que não devolver o campo faz a coisa nascer sem prazo, que é o
    comportamento de antes desta spec, preservado (FR-010).
    """
    vencida = (dados.get("descricao_vencida") or "").strip()
    if not vencida or dura_s <= 0:
        return False
    carimbar(pasta, dura_s, verbo or {"verbo": "virar"},
             urgencia=(dados.get("urgencia") or "").strip(),
             descricao_vencida=vencida, filename=filename)
    return True


def vencer_se_for_hora(pasta: Path, fm: dict, filename: str = "item.md",
                       agora: float | None = None) -> dict | None:
    """O GANCHO DO CAMINHO DE LEITURA. Recebe o `fm` que o chamador já leu, para não
    reler; só toca disco se de fato houver o que vencer.

    ONDE ISTO É CHAMADO, e por que não é no `read_doc`: `read_doc` roda 200 mil vezes
    numa única montagem de cena (medido na spec 063) — pôr escrita ali seria catastrófico.
    O gancho fica na MONTAGEM DA CENA, uma vez por entidade presente, que é O(cena) e não
    O(mundo).

    É a mesma lição que a spec 013 já tinha aprendido e escrito em
    `deslocamento.lazy_evaluate`: varrer o mundo inteiro a cada consulta é barato com
    nove memórias e deixa de ser quando cada turno gera uma.
    """
    bloco = (fm or {}).get(BLOCO)
    if not pendente(bloco, agora):
        return None
    return aplicar(pasta, filename=filename, agora=agora)


def aplicar(pasta: Path, filename: str = "item.md",
            agora: float | None = None) -> dict | None:
    """Vence, se for a hora — e devolve o que aconteceu, ou `None` se não era a hora.

    NUMA ESCRITA SÓ. A consequência e o carimbo de `vencido_em` vão juntos: é isso que
    torna o vencimento idempotente sob N leituras e sob leituras concorrentes do mesmo
    turno (FR-004). A trava do turno, no processo do server, é quem serializa.

    ZERO CHAMADA DE MODELO daqui para baixo. Se um dia alguém precisar perguntar algo ao
    Árbitro nesta função, o desenho quebrou — é o cenário de colapso que a spec nomeia.
    """
    alvo = pasta / filename
    fm, corpo = io.read_doc(alvo)
    bloco = fm.get(BLOCO)
    if not pendente(bloco, agora):
        return None
    if forma_valida(bloco) is not None:
        return None                      # inválido não vence: o validator já reportou

    ao = bloco.get("ao_vencer") or {}
    verbo = ao.get("verbo")
    feito = {"verbo": verbo, "entidade": fm.get("id") or pasta.name,
             "nome": fm.get("name") or pasta.name}

    if verbo == "condicao":
        cond = list(fm.get("status", {}).get("conditions") or [])
        if ao["valor"] not in cond:
            cond.append(ao["valor"])
        fm.setdefault("status", {})["conditions"] = cond
        feito["condicao"] = ao["valor"]
    elif verbo == "campo":
        alvo_fm, chave = fm, ao["campo"]
        partes = str(chave).split(".")
        for p in partes[:-1]:
            alvo_fm = alvo_fm.setdefault(p, {})
        alvo_fm[partes[-1]] = ao["valor"]
        feito["campo"] = chave
    elif verbo == "extinguir":
        feito["extinto"] = True

    # `virar` acompanha qualquer um dos outros: a prosa é trocada sempre que houver
    # descrição pós-vencimento. É ela que faz o vencimento chegar a quem olha — e para a
    # Mente a coisa vencida não é "um item com uma flag", é um item cuja descrição mudou.
    nova = (bloco.get("descricao_vencida") or "").strip()
    if nova:
        corpo = nova
        feito["prosa_trocada"] = True

    fm[BLOCO] = {**bloco, "vencido_em": agora if agora is not None else time.time()}
    io.write_doc(alvo, fm, corpo)

    if verbo == "extinguir":
        io.marcar_extinto(pasta)
    return feito


def lembrar(pasta_de_quem: Path, feito: dict) -> str | None:
    """NADA MUDA NO MUNDO EM SILÊNCIO (Princípio X, terceiro compromisso).

    E aqui ele é o mais fácil de esquecer, porque o vencimento **não tem ator**: ninguém
    agiu, o tempo passou. A tentação é tratar isso como mudança de estado sem história —
    e aí o alaúde apodrece, o jogador nunca fica sabendo, e a pressão que a spec inteira
    existe para criar não chega a ninguém.

    Só forma memória quem é AFETADO e está presente. Quem passa e vê um pão mofado não
    guarda um evento — vê um item, e a prosa dele já mudou (o verbo `virar`).

    Importado aqui dentro de propósito: `motor/prazo.py` é nível 0 quanto a decisão, e
    puxar `memoria` no topo criaria um ciclo de import com quem já depende de `prazo`.
    """
    from .memoria import primitivas as _mem

    nome = feito.get("nome") or feito.get("entidade") or "algo"
    if feito.get("extinto"):
        texto = f"{nome} não estava mais lá quando voltei."
    elif feito.get("prosa_trocada"):
        texto = f"Deixei passar o tempo, e {nome} não é mais o que era."
    else:
        texto = f"O tempo passou sobre {nome}."
    return _mem._write_memory(
        pasta_de_quem, texto, intensity="small",
        involved=[feito.get("entidade")] if feito.get("entidade") else None,
        summary=texto, evento="prazo_vencido")
