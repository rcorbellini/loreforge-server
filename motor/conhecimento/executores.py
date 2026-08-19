"""O Motor / conhecimento — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` + `@registro.handler` `_h_*`. Chamam as primitivas do domínio.
"""
from __future__ import annotations

import os
import random
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from .. import fisica, io, memoria, registro, rolagem, rotas
from ..fisica import (
    DOWN_CONDITIONS,
)
from ..io import (
    MotorError,
    _fail,
    _rejection,
    find_character_folder,
    name_of,
    read_doc,
)
from ..memoria import (
    ROTA,
    _is_alive,
    _rec,
    _rec_unico,
    _record_hearsay,
    _remember_route,
    memory_involved,
    memory_kind,
    has_trauma_from,
)
from ..rolagem import (
    LEARN_ROUTE_DC,
    _roll_d20,
    attr_modifier,
    learn_dc_from,
    persuade_dc,
    persuade_tendencia,
)
from ..rotas import (
    find_route,
    knows_route,
)




from .primitivas import (  # noqa: F401
    _find_hearsay_source,
    _normalize_for_search,
    _reject_all,
    quote_matches,
    roll_confidencia,
    roll_disposicao,
    roll_learn_check,
)

def _apply_learn_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list[dict], list[dict]]:
    """Aprender caminhos lidos num conteúdo (spec 014).

    Cada rota é resolvida por SI: um material de três pode render dois. Rota já
    conhecida apenas RENOVA, sem rolagem — não se falha em lembrar o que já se
    sabe (FR-011).

    Prosa aponta para o que existe; nunca cria. Rota inexistente é recusada aqui
    mesmo que o Árbitro a tenha proposto — com o enum de rotas reais ele nem
    consegue propô-la, então isto é a SEGUNDA camada de contenção.
    """
    applied, rejected = [], []
    ops = [o for o in (resolution.get("learn_ops") or []) if isinstance(o, dict)]
    # a citação do trecho NÃO é validada: o Motor não confere se o texto de fato
    # diz aquilo. Ela existe para o devlog — é o que permite auditar depois se o
    # Árbitro leu ou chutou, sem transformar julgamento de leitura em regra.
    citado = {}
    for o in ops:
        for c in o.get("citacoes") or []:
            if isinstance(c, dict) and c.get("rota"):
                citado[c["rota"]] = c.get("trecho") or ""
    # o que ele LEU neste turno: é contra isto que a citação é conferida
    fontes = [f for f in (resolution.get("lido") or []) if isinstance(f, str) and f]
    # o que ele OUVIU, e de quem (spec 015). A guarda do Árbitro já cobra a
    # `fonte`, mas guarda não é autoridade: sem esta conferência, uma resolução
    # montada sem fonte passaria pelo caminho da spec 014 — DC fixa, portão
    # nenhum — usando a fala que `ask_directions` pôs em `lido`.
    falas = {f["rota"]: f for f in (resolution.get("falas") or [])
             if isinstance(f, dict) and f.get("rota")}
    if not ops:
        return applied, rejected, []  # nada a ler: não toca em disco
    # a pasta do ator pode ter mudado no meio do turno (carry e persuade movem
    # gente para dentro de rotas). Resolver de novo, como `_record_events` já
    # aprendeu a fazer — confiar no snapshot aqui quebrou a fase 13.
    try:
        actor_folder = find_character_folder(character_id)
    except MotorError:
        return applied, rejected, []
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or fisica.is_cooking(actor_fm):  # spec 031/048: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected, []
    # o portão de disposição é resolvido UMA VEZ POR INFORMANTE POR TURNO, nunca
    # por rota: quem explica o caminho não decide de novo a cada trecho da
    # explicação. Memoizar aqui é o que faz a rolagem ser única (FR-017, FR-009).
    portoes: dict[str, tuple[bool, dict]] = {}
    sem_resp: list[dict] = []      # item 52.6: as perguntas que não renderam
    for op in ops:
        fonte = op.get("fonte") or None
        fonte_fm = None
        if fonte:
            # a pasta do informante também pode ter mudado no meio do turno
            try:
                fonte_folder = find_character_folder(fonte)
            except MotorError:
                fonte_folder = None
            if fonte_folder is None:
                _reject_all(rejected, op, "informante_indisponivel",
                                informante=fonte)
                continue
            fonte_fm, _ = read_doc(fonte_folder / "character.md")
            condicoes = ((fonte_fm.get("status") or {}).get("conditions") or [])
            if set(condicoes) & set(DOWN_CONDITIONS):
                _reject_all(rejected, op, "informante_indisponivel",
                                informante=fonte)
                continue
            if fonte not in portoes:
                portoes[fonte] = roll_disposicao(
                    character_id, actor_fm, fonte,
                    op.get("disposicao") or 0, rolls)
            passou_portao, _pinfo = portoes[fonte]
            if not passou_portao:
                # ele não quis contar: NADA se aprende nesta op, ainda que ele
                # conheça todos os caminhos do mundo (FR-010). A `atitude` viaja
                # junto porque é a única rejeição do projeto que carrega texto
                # diegético — é com ela que A Mente narra o MOTIVO da recusa.
                _reject_all(rejected, op, "recusou_informar",
                                informante=fonte,
                                atitude=op.get("atitude") or "")
                # spec 043: perguntar e ser recusado cobra de QUEM PERGUNTOU (supera
                # a spec 030 FR-003) — senão reperguntar na mesma cena é de graça.
                fisica.spend_fatigue(character_id, fisica.CUSTO_TENTATIVA_SOCIAL)
                # ITEM 52.6: e DEIXA MEMÓRIA nos dois lados. A fadiga sozinha não
                # quebrava o laço — a Nerissa perguntou o caminho à Odila 50 VEZES,
                # porque nada guardava que ela já havia perguntado e sido rebatida.
                sem_resp.append({"informante": fonte, "motivo": "nao_quis",
                                 "rota": (op.get("rotas") or [None])[0]})
                continue
        for route_id in op.get("rotas") or []:
            found = find_route(route_id)
            if not found:
                rejected.append(_rejection({"rota": route_id},
                                          _fail("rota_inexistente", rota=route_id)))
                continue
            nome = found[1].get("name") or route_id
            # SEGUNDA CAMADA: o enum da tool é o mundo inteiro (herdado da 014),
            # então o Árbitro PODE propor um caminho real que o informante não
            # conhece. Quem recusa é o arquivo, não o prompt.
            if not fonte and route_id in falas:
                rejected.append(_rejection(
                    {"rota": route_id, "nome": nome,
                     "informante": falas[route_id].get("informante")},
                    _fail("fonte_omitida", rota=route_id,
                          informante=falas[route_id].get("informante"))))
                continue
            if fonte and not knows_route(fonte, route_id):
                rejected.append(_rejection(
                    {"rota": route_id, "nome": nome, "informante": fonte},
                    _fail("informante_nao_sabe", rota=route_id,
                          informante=fonte)))
                # ITEM 52.6: "ele não conhece esse caminho" é INFORMAÇÃO — vale
                # guardar, e é diferente de "não quis dizer". A distinção fica no
                # `motivo` porque é ela que a MENTIRA vai usar depois: mentir é
                # responder `nao_sabe` a quem, na verdade, `nao_quis`.
                sem_resp.append({"informante": fonte, "motivo": "nao_sabe",
                                 "rota": route_id})
                continue
            # a citação precisa EXISTIR no que ele leu neste turno. Rota que ele
            # lembrou por outro motivo não é rota que o texto descreve.
            trecho = citado.get(route_id, "")
            # Sem NADA lido no turno, não há contra o que conferir — e essa era a
            # brecha: o modelo pulava o `examine`, inventava a citação, e a
            # conferência não se aplicava. Foi medido: dois falsos positivos
            # passaram exatamente assim. Citação que não se pode conferir vale o
            # mesmo que citação falsa.
            if not fontes or not any(quote_matches(trecho, f) for f in fontes):
                rejected.append(_rejection(
                    {"rota": route_id, "nome": nome, "trecho": trecho},
                    _fail("citacao_nao_confere", rota=route_id)))
                continue
            if knows_route(character_id, route_id):
                _remember_route(actor_folder, route_id, nome)
                item = {"rota": route_id, "nome": nome, "renovou": True}
                if fonte:
                    item["fonte"] = fonte
                applied.append(item)
                continue
            dc = learn_dc_from(fonte_fm) if fonte else None
            passou, _info = roll_learn_check(character_id, actor_fm, route_id,
                                             rolls, dc)
            if not passou:
                rejected.append(_rejection(
                    {"rota": route_id, "nome": nome,
                     "trecho": citado.get(route_id, ""),
                     **({"informante": fonte} if fonte else {})},
                    _fail("leitura_falhou", rota=route_id)))
                continue
            _remember_route(actor_folder, route_id, nome)
            item = {"rota": route_id, "nome": nome, "renovou": False,
                    "trecho": citado.get(route_id, "")}
            if fonte:
                item["fonte"] = fonte
            applied.append(item)
    return applied, rejected, sem_resp


def _apply_hearsay_ops(character_id: str, actor_folder: Path, resolution: dict,
                       rolls: list | None = None) -> tuple[list[dict], list[dict]]:
    """Ouvir um episódio de outro e formar memória de reconto (spec 017).

    Molde do `_apply_learn_ops`: portão por fonte (uma rolagem), citação conferida
    contra o que foi surfaçado no turno (`lido`), e a gravação pelo Motor. O que
    muda é o alvo — uma memória de `acontecimento`, não uma rota — e o grau.
    """
    applied, rejected = [], []
    ops = [o for o in (resolution.get("hearsay_ops") or []) if isinstance(o, dict)]
    if not ops:
        return applied, rejected
    fontes_lido = [f for f in (resolution.get("lido") or [])
                   if isinstance(f, str) and f]
    try:
        actor_folder = find_character_folder(character_id)
    except MotorError:
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or fisica.is_cooking(actor_fm):  # spec 031/048: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    portoes: dict[str, bool] = {}
    for op in ops:
        fonte = op.get("fonte")
        sobre = op.get("sobre")
        trecho = (op.get("trecho") or "").strip()
        base = {"fonte": fonte, "sobre": sobre}
        # a fonte precisa existir e estar em condições
        try:
            fonte_folder = find_character_folder(fonte)
        except MotorError:
            fonte_folder = None
        if fonte_folder is None:
            rejected.append(_rejection(base, _fail("informante_indisponivel",
                                                  informante=fonte)))
            continue
        fonte_fm_char, _ = read_doc(fonte_folder / "character.md")
        cond = ((fonte_fm_char.get("status") or {}).get("conditions") or [])
        if set(cond) & set(DOWN_CONDITIONS):
            rejected.append(_rejection(base, _fail("informante_indisponivel",
                                                  informante=fonte)))
            continue
        # PORTÃO da confidência: uma vez por fonte por turno
        if fonte not in portoes:
            portoes[fonte] = roll_confidencia(character_id, actor_fm, fonte,
                                              op.get("disposicao") or 0, rolls)[0]
        if not portoes[fonte]:
            rejected.append(_rejection(
                {**base, "atitude": op.get("atitude") or ""},
                _fail("nao_confiou", informante=fonte,
                      atitude=op.get("atitude") or "")))
            # spec 043: sondar alguém que não se abre cobra de quem sondou.
            fisica.spend_fatigue(character_id, fisica.CUSTO_TENTATIVA_SOCIAL)
            continue
        # ITEM 52 — O RECONTO É UM Z, DE N FONTES.
        #
        # A defesa de CITAÇÃO (014/015) não cabe mais aqui, e é preciso dizer por quê:
        # ela existia para impedir que o Árbitro inventasse um trecho e o passasse por
        # lembrança alheia — o trecho tinha de conferir LETRA A LETRA com o que a fonte
        # guardava. O Z é o oposto disso por DESENHO: é o informante recontando com as
        # próprias palavras, e distorcer ordem, motivo e ênfase é o comportamento
        # pedido (decisão do mantenedor: "nem sempre quando você pede informação a
        # alguém, ele conta exatamente o que aconteceu").
        #
        # O que substitui a defesa: as FONTES. `fontes_reconto` é a lista real de
        # lembranças vivas da fonte sobre o assunto, colhida pela declaração — e é dela
        # que saem `involved`, valência, intensidade e grau. O texto pode torcer; o
        # esqueleto que costura o mundo continua ancorado no que existe.
        # SEM LASTRO -> `citacao_nao_confere`, a MESMA regra (e o mesmo sentido) da
        # defesa 014/015 que existia aqui: um reconto que não se ancora em lembrança
        # real da fonte não passa. O que mudou é COMO se prova o lastro — antes era o
        # trecho conferido letra a letra; agora são as fontes que a declaração colheu.
        # Uma op forjada de fora não tem `fontes_reconto` e cai aqui, que é o ataque
        # que a Fase 20 exercita.
        fontes_mem = [f for f in (op.get("fontes_reconto") or []) if isinstance(f, dict)]
        if not fontes_mem:
            rejected.append(_rejection({**base, "trecho": trecho},
                                       _fail("citacao_nao_confere", informante=fonte)))
            continue
        mem_id = _record_hearsay(actor_folder, fontes_mem, sobre, trecho, fonte)
        applied.append({"fonte": fonte, "sobre": sobre, "id": mem_id,
                        "z": trecho})     # o Z sobe para o outro lado gravar o mesmo
    return applied, rejected


@registro.handler("learn_ops")
def _h_learn(cid, af, res, rolls):
    applied, rejected, sem_resp = _apply_learn_ops(cid, af, res, rolls)
    # item 52.6: a pergunta que não rendeu deixa memória nos DOIS lados. Reusa o
    # canal `unanswered_ops` — é a mesma coisa que o `ask_about` já grava, com outro
    # motivo. Um canal, três motivos; não três escritores.
    _, _, created = _apply_unanswered_ops(cid, af, {"unanswered_ops": sem_resp})
    return applied, rejected, created


@registro.handler("hearsay_ops")
def _h_hearsay(cid, af, res, rolls):
    applied, rejected = _apply_hearsay_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)


def _texto_sem_resposta(motivo: str, assunto: str, rota: str | None):
    """As duas frases da pergunta que não rendeu — a de QUEM PERGUNTOU e a de QUEM
    RESPONDEU (item 52.2/52.6).

    A assimetria não é estilo, é preparo para a MENTIRA (decisão do mantenedor: "no
    futuro a mentira seria algo dentro de não querer dizer — ele poderia mentir dizendo
    que não sabia"). Por isso:

      · quem PERGUNTOU registra O QUE OUVIU  ("disse que não sabia");
      · quem RESPONDEU registra O QUE FEZ    ("não quis dizer").

    Hoje as duas coincidem porque ninguém mente. Quando a mentira existir, só o lado do
    informante muda ("menti que não sabia") — e a memória de quem perguntou continua
    fiel ao que ele de fato ouviu, que é o único jeito de o boato falso se propagar
    sem o mundo trapacear na cabeça de quem escuta.
    """
    onde = f"o caminho de {rota}" if rota else (f"sobre {assunto}" if assunto else "algo")
    if motivo == "nao_quis":
        return (f"Perguntei {onde} a {{quem}} — disse que não queria falar disso.",
                f"{{quem}} me perguntou {onde} — não quis dizer.")
    if motivo == "nao_sabe":
        return (f"Perguntei {onde} a {{quem}} — disse que não conhece.",
                f"{{quem}} me perguntou {onde} — eu não conheço esse caminho.")
    return (f"Perguntei {onde} a {{quem}} — não soube dizer.",
            f"{{quem}} me perguntou {onde} — eu não soube dizer.")


def _apply_unanswered_ops(character_id: str, actor_folder: Path, resolution: dict,
                          rolls: list | None = None) -> tuple[list, list, list]:
    """A PERGUNTA QUE NÃO RENDEU, gravada nos DOIS lados (item 52.2).

    Decisão do mantenedor (2026-08-13): memória em ambos, intensidade MÍNIMA, e o
    texto o mais legível possível — não genérico — para que os dois possam consultar
    de forma eficiente.

    Por que nos dois: perguntar É um ato social, e ele acontece com duas pessoas. Quem
    perguntou precisa saber que já perguntou (era o que faltava — 23 repetições da
    mesma pergunta); quem foi perguntado sabe que foi procurado sobre aquilo, e isso é
    matéria de relação, não ruído.

    Por que `small`: nada mudou no mundo. A memória existe para não repetir e para
    tingir a relação, não para pesar em régua — e o relógio da 013 a apaga primeiro,
    que é o desejável para um não-evento.

    Por que os DOIS ids em `involved`: é o que faz `remembered_about(A, B)` achar
    isto quando um pensar no outro. E o ASSUNTO entra no TEXTO (não em `involved`),
    porque em geral ele não é entidade nenhuma — era justamente o caso da Nerissa.
    """
    from .declaracao import _assunto_legivel        # a prosa mora com a declaração
    applied, created = [], []
    for op in resolution.get("unanswered_ops") or []:
        if not isinstance(op, dict):
            continue
        informante, sobre = op.get("informante"), op.get("sobre")
        if not informante:
            continue
        assunto = _assunto_legivel(sobre) if sobre else ""
        rota = name_of(op.get("rota")) if op.get("rota") else None
        motivo = op.get("motivo") or "nao_soube"
        t_perguntou, t_respondeu = _texto_sem_resposta(motivo, assunto, rota)
        envolvidos = [character_id, informante]
        # UMA memória por assunto, renovada — não uma por vez que se pergunta.
        # Perguntar de novo o mesmo a mesma pessoa não é um fato novo: é o MESMO
        # fato, mais insistente. Ver `_remember_recurring` para o estrago que a
        # duplicação fez (35 das 40 memórias vivas do Tobias eram esta recusa, e
        # eram elas que o faziam perguntar de novo).
        chave = f"{informante}\u0000{assunto or rota or ''}"
        _rec_unico(created, character_id,
                   t_perguntou.format(quem=name_of(informante)),
                   "unanswered", envolvidos, about=f"perguntei\u0000{chave}")
        _rec_unico(created, informante,
                   t_respondeu.format(quem=name_of(character_id)),
                   "unanswered", envolvidos,
                   about=f"perguntaram\u0000{character_id}\u0000{assunto or rota or ''}")
        applied.append({"informante": informante, "sobre": sobre,
                        "motivo": motivo, "rota": op.get("rota")})
    return applied, [], created


@registro.handler("unanswered_ops")
def _h_unanswered(cid, af, res, rolls):
    applied, rejected, created = _apply_unanswered_ops(cid, af, res, rolls)
    return applied, rejected, created
