"""DECLARAÇÃO + CORPO da tool de CANTAR (spec 058).

Cantar não é cozinhar: não há régua de admissão, nenhum portão, nenhuma recusa
de mérito. O personagem abre a boca e canta — o que varia é o que ele cantou e
o que aquilo gera, nunca SE algo acontece. Único gate real: o portão de ESTADO
(dormindo/descansando) que qualquer tool de ação já respeita — aplicado no
EXECUTOR (`motor/musica/executores.py`), não aqui.

A LLM do Árbitro faz DUAS coisas nesta tool, as duas MEDIDAS (ver
specs/058-sing-deed-propagation/research.md): escreve a LETRA e lê a prosa do
INSTRUMENTO. Não há régua de qualidade da canção — medido que o modelo
inverte a ordem dos feitos (banal=5, médio=10, grande=10); o tamanho do feito
vem de `intensity`, campo que o Motor já escreve (ver `data-model.md`).
"""
from __future__ import annotations

import json as _json

import motor

from .. import juizo
from ..registro import ToolSpec, inworld, tool_spec

_STR = {"type": "string"}


# --------------------------------------------------------------------------- #
# O prompt — texto MEDIDO (research.md M5: cópia literal 8,5% contra 17,4%/
# 20,8% das alternativas; refrão 4/4; uso da cena 4/4; zero respostas
# perdidas). NÃO reescrever de cabeça: reescrever invalida a medição (regra do
# mantenedor, 2026-08-29 — todo prompt novo ao Árbitro nasce com 2+ propostas
# e é medido antes de aplicar).
# --------------------------------------------------------------------------- #

_ABERTURA = """\
Um personagem está cantando, para quem está presente, uma lembrança que ele guarda.
Ele VAI cantar — isso não está em questão. Você escreve a LETRA: o que essa gente
ouve sair da boca dele."""

CONTRATO_LETRA = """\
A LETRA é o que a plateia ouve, na voz de quem canta para uma mesa. Cante para ESTA
sala: o lugar e quem está ouvindo entram na letra. Nada na canção pode ser pessoa,
lugar ou feito que não esteja na lembrança ou na sala.
A LETRA tem forma: QUATRO VERSOS curtos. O primeiro e o último são o MESMO — é o
refrão que a mesa repete. Os dois do meio contam o que aconteceu, por imagem.
NÃO REPITA O RELATO palavra por palavra: uma canção não é um depoimento. Escolha UMA
imagem do que aconteceu e construa em cima dela — o resto pode ficar subentendido.
Escreva a letra em UMA ÚNICA LINHA, separando os versos com " / ". Nunca use quebra
de linha, e nunca escreva rótulos como "Refrão:" ou "Verso 1:"."""

# spec 058, US4 (research M7): medida determinística — alaúde rachado 2, caneca
# 0, alaúde fino 10. Só entra no prompt (e no schema pedido) quando HÁ
# instrumento — pedir nota sobre o que não existe convida alucinação (mesma
# disciplina de `drink`, que omite a régua de consumo para uma fonte
# inesgotável).
REGUA_INSTRUMENTO = """\
Régua do INSTRUMENTO (o quanto o que ele tem NA MÃO, PELA DESCRIÇÃO, ajuda a canção
— não se é valioso, bonito ou raro):
  0  não é instrumento — uma caneca, uma faca, uma corda
  5  improvisado — algo que se percute ou sopra sem ter sido feito para isso
  10 instrumento pleno e em ordem, feito para acompanhar a voz
Um instrumento AVARIADO (rachado, cordas faltando, colado) fica na faixa baixa — 1 a
3 —, nunca 0: ainda é um instrumento, só não ajuda muito. Esta nota nunca atrapalha;
ela só soma."""

_FECHO_SEM_INSTR = """\

Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"letra": "<a canção, em uma linha>"}"""

_FECHO_COM_INSTR = """\

Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE assim:

{"letra": "<a canção, em uma linha>", "instrumento": <inteiro 0-10>}"""


def _regua_sing(com_instrumento: bool, registro: str) -> str:
    partes = [_ABERTURA, CONTRATO_LETRA]
    if registro:
        partes.append(registro)
    if com_instrumento:
        partes.append(REGUA_INSTRUMENTO)
    partes.append(_FECHO_COM_INSTR if com_instrumento else _FECHO_SEM_INSTR)
    return "\n\n".join(partes)


# a que `ToolSpec.juizo` cita — a mais rica (com instrumento), usada só para o
# manifest declarar QUE há juízo nesses dois parâmetros; o prompt de VERDADE é
# remontado em cada chamada real por `_regua_sing`, conforme há ou não instrumento.
REGUA_SING = _regua_sing(True, "")


@inworld("musica_ops_applied")
def _iw_sing(op):
    desfecho = op.get("desfecho")
    if not op.get("ouvintes"):
        return "cantou, embora não houvesse ninguém para ouvir"
    if desfecho == "otimo":
        return "cantou, e a sala inteira parou para escutar"
    if desfecho == "comum":
        return "cantou, e alguns pararam para escutar"
    return "tentou cantar, mas a voz não pegou"


def _sing_desc(scene):
    # a listagem das lembranças é OBRIGATÓRIA — medida (research M1): sem ela a
    # Mente escolhe a lembrança errada (FN=7, 3 ids errados) contra (FN=1, 0
    # errados) com ela, e ela NÃO induz chamada indevida (FP=0 nas três
    # variantes). Molde de `_accuse_desc`.
    memorias = scene.cand.get("sing_memorias") or {}
    listagem = "; ".join(
        f"{mid} (sobre {motor.name_of(info['sobre'])}: '{info['resumo']}')"
        for mid, info in sorted(memorias.items()))
    base = ("Canta, para quem estiver aqui, uma lembrança sua. Quem ouvir passa a "
            "saber do que aconteceu, mesmo sem ter estado lá. Em `memoria_id` vai a "
            "lembrança a cantar; em `instrumento`, algo que você já tenha na mão.")
    if listagem:
        base += f" Lembranças disponíveis: {listagem}."
    return base


def _sing(name: str, args: dict, ctx) -> tuple[dict, bool]:
    memorias = ctx.cand.get("sing_memorias") or {}
    memoria_id = args.get("memoria_id")
    if memoria_id not in memorias:
        return ctx.err(f"'{memoria_id}' não é uma memória sua válida", "memoria_id",
                       [{"id": mid, "nome": info["resumo"]}
                        for mid, info in sorted(memorias.items())]), False

    instrumentos = ctx.cand.get("sing_instrumento") or []
    instrumento = args.get("instrumento")
    if instrumento is not None and instrumento not in instrumentos:
        return ctx.err(f"'{instrumento}' não está na sua mão", "instrumento",
                       ctx.validos({i: ctx.items[i] for i in instrumentos})), False

    if memoria_id in ctx.sung_asked:
        return ctx.err("cantar essa lembrança já foi tentado neste turno — o "
                       "desfecho sai na aplicação; NÃO repita: siga para outra "
                       "ação ou narrate"), False
    ctx.sung_asked.add(memoria_id)

    info = memorias[memoria_id]
    lugar = ctx.describe(ctx.place_id) or {"nome": ctx.context.get("location", {})
                                           .get("name")}
    plateia = [{"nome": p.get("name"), "fazendo": p.get("action"),
               "humor": p.get("mood")}
              for p in (ctx.context.get("characters_present") or [])
              if p.get("id") != ctx.actor]
    payload = {"lembranca": info["conteudo"], "sobre": motor.name_of(info["sobre"]),
              "lugar": lugar, "plateia": plateia, "prosa": ctx.prosa}
    tem_instrumento = instrumento is not None
    if tem_instrumento:
        payload["instrumento"] = ctx.describe(instrumento)

    registro = motor.musica.registro_de_intensidade(info.get("intensity"))
    raw = ctx.ask(_regua_sing(tem_instrumento, registro),
                  _json.dumps(payload, ensure_ascii=False, indent=2))
    # a chave JSON pedida ao modelo é "instrumento" (texto MEDIDO — ver
    # `_FECHO_COM_INSTR`); renomeada para `instrumento_nota` só ao sair daqui,
    # porque "instrumento" já nomeia a ESCOLHA (o item na mão) na `ToolSpec` —
    # duas coisas com o mesmo nome fariam `build_face` esconder o parâmetro
    # errado da face.
    campos = {"instrumento": 0} if tem_instrumento else {}
    julgado = juizo.julgamento(raw, campos, texto_campos={"letra": info["resumo"]})
    letra = julgado.get("letra") or info["resumo"]
    nota_instrumento = julgado.get("instrumento", 0)

    rej, rolled = ctx.apply_arbitrated("musica_ops", {
        "memoria_id": memoria_id, "instrumento": instrumento, "letra": letra,
        "instrumento_nota": nota_instrumento})
    if rej:
        return ctx.arb_deny(rolled, ("sing", memoria_id), {"memoria_id": memoria_id},
                            rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


SING = tool_spec(ToolSpec(
    names=("sing",),
    juizo=(
        ("letra", REGUA_SING),
        ("instrumento_nota", REGUA_SING),
    ),
    description=_sing_desc,
    params={"memoria_id": _STR, "instrumento": _STR,
            "letra": _STR, "instrumento_nota": {"type": "integer", "minimum": 0,
                                                "maximum": 10}},
    required=("memoria_id",),
    enum_sources={"memoria_id": lambda s: sorted(s.cand.get("sing_memorias") or {}),
                 "instrumento": "sing_instrumento"},
    omit_if_empty=("instrumento",),
    apply=_sing,
))
