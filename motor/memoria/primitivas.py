"""O Motor / memoria — PRIMITIVAS (item 31 §3: DDD por domínio).

Funções puras (validação, rolagem, helpers). Sem turno/LLM. Ver executores.py.
"""
from __future__ import annotations

import math
import os
import random
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from .. import fisica, io, registro, rolagem
from ..io import (
    find_character_folder,
    name_of,
    new_id,
    read_doc,
    write_doc,
)


_MEMORY_INTENSITIES = {"small", "medium", "large", "giant"}


# Domínio de memória (spec 029, item 9/16/18 do backlog): fonte ÚNICA em
# `validator.DOMAINS` — mesmo padrão que SIZES/SLOTS já seguem ("a régua é
# compartilhada... o Motor importa daqui", validator.py:25). O enum de
# `create_memory` (arbiter.py) e a tabela de retrofit (_DOMAIN_BY_EVENT,
# abaixo) leem `validator.DOMAINS`, nunca uma cópia local — evita duas
# listas divergentes. Ao contrário de `evento` (spec 028, campo aberto),
# este é FECHADO por decisão desta spec: o valor alimenta um cálculo
# (proficiência) que precisa ser estável entre consultas.
DOMAINS = validator.DOMAINS


_DEFAULT_TTL_SECONDS = 3600


ACONTECIMENTO = "acontecimento"


ROTA = "rota"


_TTL_BY_INTENSITY = {
    "small": 2 * 86400,
    "medium": 14 * 86400,
    "large": 90 * 86400,
    "giant": 365 * 86400,
}


_TTL_ROTA = 180 * 86400


# TTL POR EVENTO — vence a tabela por intensidade quando o evento é registro de
# ESTADO, não vivência (decisão do mantenedor, 2026-08-13: "expirar mais rápido").
#
# O `mutate` era 898 memórias, UM TERÇO de tudo que o mundo lembra, com texto de
# campo ("Mudou em mim: action — ..."). E a `action` de um personagem muda a CADA
# turno, então cada uma virava lembrança permanente do que ele estava fazendo às
# 14h07 de uma terça. Medido: nasciam com 48h (`small`) e chegavam a 598 DIAS,
# porque a renovação por convívio somava meio TTL toda vez que ele agia de novo.
#
# 6h é o que basta para tingir a cena atual — "ela estava mexendo no alambique há
# pouco" — e some antes do dia seguinte, que é o comportamento certo para um
# registro de estado.
_TTL_BY_EVENTO = {"mutate": 6 * 3600}

# E o que expira rápido NÃO PODE SER RENOVADO, senão o prazo curto não vale nada:
# a renovação por convívio (spec 030) estende toda memória viva que envolve quem
# age, e era ela que empurrava o `mutate` para 598 dias.
_EVENTOS_SEM_RENOVACAO = frozenset({"mutate"})



_RASTRO_TTL_BASE = 43200      # 12h — teto curto da faixa baixa (bem < 48h)
_RASTRO_TTL_STEP = 14400      # 4h — quanto a rolagem desloca, prum lado ou outro
_RASTRO_TTL_MIN = 3600        # 1h — piso, nunca menos
_RASTRO_TTL_MAX = 172800      # 48h — teto absoluto (mesmo limite do validator)


_PERCENTUAL_BASE_POR_BANDA = {"media": 0.35, "alta": 0.15}
_PISO_PERCENTUAL_ESQUECIDO = 0.05


_INTENSITY_ORDER_DESC = {"giant": 0, "large": 1, "medium": 2, "small": 3}


POSITIVA, NEGATIVA = "positiva", "negativa"


# spec 038 (T016): as tabelas centrais `_RELEVANCE_BY_EVENT` e `_VALENCE_BY_EVENT`
# MORRERAM. A relevância (intensidade) e a valência (sinal) de cada ato agora
# viajam COM o ato — cada recordador (`_record_*`, hoje acionado pela reação
# `react_actor_memory`) as declara localmente (o default `small`/neutro cobre a
# maioria; o grave sobe a nota). Era o par de tabelas que uma tool nova tinha de
# lembrar de atualizar, ou a memória saía com a intensidade/valência erradas em
# silêncio — o anti-padrão que a spec 013 nomeou. Os consumidores (portão de
# trauma `has_trauma_from`, saliência) sempre leram do arquivo gravado, nunca da
# tabela; nada a mudar neles.


# Domínio de memória (spec 029): todo
# evento fora daqui cai em "nenhuma" pelo default de _write_memory, nunca
# erro. Deliberadamente ausentes: "equip", "lock", "mutate", "wield" (ações
# utilitárias, ninguém progride nelas) e "promise" (fora do escopo decidido
# nesta spec — fica pra quando o item 22 for revisitado sob este eixo).
_DOMAIN_BY_EVENT = {
    # combate
    "attack": "combate", "defeat": "combate", "assaulted": "combate",
    "weapon_hit": "combate", "weapon_miss": "combate",
    "witness_attack": "combate",
    # crime
    "theft": "crime", "stolen": "crime", "stolen_from": "crime",
    "witness_theft": "crime", "theft_twist": "crime",
    # comercio
    "trade": "comercio", "transfer": "comercio",
    "gift_received": "comercio", "gift_given": "comercio",
    "gift_reluctant": "comercio", "witness_trade": "comercio",
    "witness_transfer": "comercio", "witness_persuade_give": "comercio",
    "emprestimo": "comercio", "witness_emprestimo": "comercio",
    # social
    "persuade": "social", "accuse": "social", "accused": "social",
    "witness_accuse": "social", "hearsay": "social",
    "hearsay_reconto": "social",
    # deslocamento
    "travel": "deslocamento", "learn_route": "deslocamento",
    "carry": "deslocamento", "learn": "deslocamento",
    "inform": "deslocamento", "taught": "deslocamento",
    # spec 034: deslocamento testemunhado (chegada/partida) — mesmo domínio
    # que travel/learn_route/carry já ocupam.
    "witness_departure": "deslocamento", "witness_arrival": "deslocamento",
    # cura (spec 032) — primeiro domínio de fase 2
    "heal": "cura", "healed": "cura", "witness_heal": "cura",
    # cozinha (spec 048) — segundo domínio de fase 2. Só prato CRIADO
    # carimba (qualquer banda); as recusas de mérito (cook_refused_*) ficam
    # DE FORA de propósito — não alimentam a proficiência.
    "cook": "cozinha", "cook_otimo": "cozinha", "cook_ruim": "cozinha",
    # acougue (spec 050) — terceiro domínio de fase 2. Só carne CRIADA
    # carimba (qualquer banda); as recusas de mérito (butcher_refused_*)
    # ficam DE FORA de propósito — não alimentam a proficiência.
    "butcher_farto": "acougue", "butcher_medio": "acougue",
    "butcher_fraco": "acougue",
    # ferraria / armaria (spec 052) — quarto e quinto domínios de fase 2, e os
    # primeiros a serem DOIS de uma vez: praticar armadura não faz ninguém melhor
    # forjando espada. Só peça CONCLUÍDA carimba — abrir trabalho, retomar, ser
    # rebaixado pela catraca e as recusas de mérito ficam DE FORA de propósito
    # (FR-034): o que ensina o ofício é a peça terminada, não a tentativa.
    "forge_weapon": "ferraria", "forge_weapon_falha": "ferraria",
    "forge_weapon_excepcional": "ferraria",
    "forge_armor": "armaria", "forge_armor_falha": "armaria",
    "forge_armor_excepcional": "armaria",
}


_DONO_EVENTOS = {"transfer", "emprestimo", "witness_transfer", "witness_emprestimo"}


_PUBLICO = "publico"   # ruído de ato ostensivo: visto por todos os presentes


_APEGO_VITIMA_FORTE = 4.0


_LIMIAR_SONO_QUALIDADE = 0.5


_INTENSITY_ORDER = {"giant": 0, "large": 1, "medium": 2, "small": 3}


_DAY = 86400


_VIVID_WINDOW = {
    "small": 2 * _DAY,
    "medium": 14 * _DAY,
    "large": 60 * _DAY,
    "giant": 180 * _DAY,
}


_MEMORY_CONTEXT_CAP = 40


_MEMORY_WEIGHT = {"small": 1.0, "medium": 2.0, "large": 4.0, "giant": 8.0}


_FAMILIARIDADE_PISO = 0.5


_FADIGA_CORTES = (0.25, 0.5, 0.75, 1.0)
_FADIGA_PENALIDADES = (0, 1, 2, 4)


# Curva ASSINTÓTICA de proficiência (spec 048, research R12 — substitui a antiga
# tabela de degraus, nível inteiro 0-5 com teto duro em peso>=64). Sem teto de
# PESO de entrada: o personagem pode acumular peso infinito, e cada unidade nova
# vale cada vez MENOS (derivada decrescente) — nunca zero, nunca trava. Retrofit
# de `cura` (spec 032, já em produção): os dois pontos que ela consome o valor já
# clampam o resultado (`_recovery_fraction`/`_forgotten_percent`), então nenhuma
# linha muda lá — só a FORMA da curva compartilhada.
_PROFICIENCY_TETO = 10.0   # nunca alcançado, só aproximado
_PROFICIENCY_K = 16.0      # peso no qual o fator atinge metade do teto (calibrável)


def memory_kind(fm: dict) -> str:
    """Classe da memória. Ausente ⇒ acontecimento (compatibilidade, FR-002)."""
    kind = fm.get("kind")
    return kind if kind in (ACONTECIMENTO, ROTA) else ACONTECIMENTO


def memory_involved(fm: dict) -> list[str]:
    """Quem participou. Ausente ⇒ lista vazia — nunca None, para o chamador não checar."""
    involved = fm.get("involved")
    if not isinstance(involved, list):
        return []
    return [x for x in involved if isinstance(x, str)]


def memory_about(fm: dict) -> str | None:
    """Referente da memória de conhecimento (o id da rota). None em acontecimento."""
    about = fm.get("about")
    return about if isinstance(about, str) else None


def ttl_for(kind: str, intensity: str, evento: str | None = None) -> int:
    if kind == ROTA:
        return _TTL_ROTA
    if evento in _TTL_BY_EVENTO:
        return _TTL_BY_EVENTO[evento]
    return _TTL_BY_INTENSITY.get(intensity, _TTL_BY_INTENSITY["medium"])


def _create_memories(present: dict, resolution: dict) -> list[dict]:
    """Cria memórias de 1ª classe ancoradas aos personagens afetados (FR-025).

    Cada memória vira um `memories/<id>.md` sob a pasta do personagem-alvo, com
    timestamp_start/end reais e intensity decididos pelo Árbitro. `present` mapeia
    id -> pasta dos personagens elegíveis (os presentes na cena).
    """
    created = []
    for mem in resolution.get("memories") or []:
        target = mem.get("target")
        content = (mem.get("content") or "").strip()
        if target not in present or not content:
            continue
        intensity = mem.get("intensity")
        if intensity not in _MEMORY_INTENSITIES:
            intensity = "medium"
        # spec 029: domain já validado na fronteira da tool (arbiter.py); o
        # default aqui é só defesa em profundidade, mesmo espírito do fallback
        # de intensity acima — nunca deixa a memória sair sem o campo.
        domain = mem.get("domain")
        if domain not in DOMAINS:
            domain = "nenhuma"
        try:
            ttl = int(mem.get("ttl_seconds"))
        except (TypeError, ValueError):
            ttl = _DEFAULT_TTL_SECONDS
        ttl = max(1, ttl)
        now = int(time.time())
        mem_id = new_id("mem")
        summary = (mem.get("summary") or "").strip() or _short_summary(content)
        fm = {
            "type": "memory", "id": mem_id,
            "timestamp_start": now, "timestamp_end": now + ttl,
            "intensity": intensity, "state": "active", "summary": summary,
            "domain": domain,
            # ERA AQUI QUE O CAMPO SUMIA. Este é o canal do `create_memory` — a caneta
            # do mundo —, e ele montava o frontmatter sem `evento`: 743 memórias
            # nascidas em runtime (28% de todo o acervo) ficaram sem etiqueta, com
            # texto bom e invisíveis ao casamento por TEMA do `recall` e a qualquer
            # régua que leia `evento`. Quem chama informa (a tool sabe que fato é);
            # "registro" é o piso honesto quando ninguém disse.
            "evento": (mem.get("evento") or "").strip() or "registro",
        }
        write_doc(present[target] / "memories" / f"{mem_id}.md", fm, content)
        created.append({"target": target, "id": mem_id, "intensity": intensity})
    return created


def _write_memory(folder: Path, content: str, *, kind: str = ACONTECIMENTO,
                  intensity: str = "medium", involved: list[str] | None = None,
                  about: str | None = None, summary: str = "",
                  valence: dict[str, str] | None = None,
                  ouvido_de: str | None = None,
                  evento: str | None = None,
                  domain: str | None = None,
                  seq: int = 0) -> str:
    """Grava uma memória na pasta de quem lembra. Ponto único de escrita.

    `evento` (item 19/20 do backlog, spec 028): o rótulo do ato — até a spec 038
    (T016) ele calibrava intensidade/valência por tabela central; hoje essas notas
    viajam COM o ato (o recordador as passa a `remember`/`_rec`), e `evento` fica só
    como carimbo persistido (proveniência/domínio).
    Carimbo por CONSTRUÇÃO (o Motor já sabe o evento no momento em que
    escreve; não é interpretação de prosa), campo ABERTO, sem enum em
    `validator.py` — o vocabulário já cresce organicamente por spec, e
    persistir só espelha no arquivo o que o código já decide. Ausente
    (`None`) = sem categoria, comportamento idêntico ao de antes desta
    spec; nenhum consumidor lê isto ainda (item 19 decide o uso depois).

    `domain` (spec 029, item 9/16/18 do backlog): AO CONTRÁRIO de `evento`,
    este é FECHADO (`validator.DOMAINS`) e SEMPRE persistido — nunca
    omitido, porque alimenta um cálculo (proficiência) que trata ausência
    e "nenhuma" da mesma forma, mas ser explícito documenta a decisão. Se
    não informado, resolve por `_DOMAIN_BY_EVENT.get(evento, "nenhuma")` —
    carimbo automático pelos ~20 call sites que já passam `evento`; quem
    precisa decidir ativamente (`create_memory`, o canal livre do Árbitro)
    passa `domain` explícito, já validado na fronteira da tool."""
    now = int(time.time())
    # o sufixo aleatório não é enfeite: sem ele, duas memórias criadas no mesmo
    # milissegundo recebem o mesmo id e uma sobrescreve a outra silenciosamente.
    # Aconteceu ao aprender várias rotas de um mapa só — seis viraram uma.
    mem_id = new_id("mem")
    fm = {
        "type": "memory", "id": mem_id, "kind": kind,
        "involved": list(involved or []),
        "timestamp_start": now,
        "timestamp_end": now + ttl_for(kind, intensity, evento),
        "intensity": intensity, "state": "active",
        "summary": summary.strip() or _short_summary(content),
        "domain": domain or _DOMAIN_BY_EVENT.get(evento, "nenhuma"),
    }
    if evento:
        fm["evento"] = evento
    if about is not None:
        fm["about"] = about
    # PROVENIÊNCIA de boato (spec 017): de quem ESTE personagem ouviu o reconto.
    # SEGREDO ATÉ DO ÁRBITRO — o terceiro nível de sigilo do projeto. Serve ao
    # Motor (presença = é boato, define o grau do próximo reconto) e ao mantenedor
    # (rastrear a cadeia). NUNCA é surfaçado: nenhuma função de leitura o inclui.
    if ouvido_de:
        fm["ouvido_de"] = ouvido_de
    # valência DIRIGIDA (spec 016): sinal por alvo, derivado do evento pelo Motor,
    # nunca declarado pelo autor. Só grava o que tem sinal — ausência = neutro, e
    # neutro NÃO ocupa espaço no frontmatter (a maioria das memórias é neutra).
    if valence:
        limpo = {k: v for k, v in valence.items() if v in ("positiva", "negativa")}
        if limpo:
            fm["valence"] = limpo
    write_doc(folder / "memories" / f"{mem_id}.md", fm, content)
    return mem_id


def _insistencia(vezes: int) -> str:
    """Como o personagem LEMBRA de ter repetido — em linguagem de mundo, nunca um
    número de sistema (Princípio V). O que ele sabe é a INSISTÊNCIA, não a contagem.

    Escala de propósito: a partir da terceira vez a lembrança passa a dizer que foi
    em vão. Não é o mundo concluindo por ele (isso seria juízo, e juízo não é do
    Motor) — é o FATO de que insistiu e não rendeu, que é dele e ele viveu."""
    if vezes <= 1:
        return ""
    if vezes == 2:
        return " E não foi a primeira vez que perguntei."
    if vezes <= 5:
        return " Já insisti algumas vezes, sempre em vão."
    return " Já insisti muitas vezes, e nunca rendeu nada."


def _reincidencia(vezes: int, frag: str) -> str:
    """A mesma escala de `_insistencia`, com o VERBO de quem chama.

    `_insistencia` fala de PERGUNTA ("já insisti"), e por isso o mecanismo ficou
    preso a um consumidor só: o `sanea_mundo.py` já registrava que "a mesma frase
    serviria a 'Vi X acusar Y', onde 'insisti' é o verbo errado". O que muda entre
    os casos é uma palavra, não a escala — então a palavra vem de fora e a escala
    fica aqui, num lugar só. `frag` é a 1ª pessoa do passado ("tentei", "o acusei
    disso", "os vi nisso").

    Continua sem número (Princípio V): o personagem sabe que repetiu, não quantas.
    """
    if vezes <= 1:
        return ""
    if vezes == 2:
        return f" E não foi a primeira vez que {frag}."
    if vezes <= 5:
        return f" Já {frag} algumas vezes, sempre no mesmo."
    return f" Já {frag} muitas vezes, e nunca mudou nada."


def _remember_recurring(character_folder: Path, texto: str, *, evento: str,
                        about: str, involved: list[str],
                        intensity: str = "small", summary: str = "",
                        frag: str = "",
                        valence: dict[str, str] | None = None
                        ) -> tuple[str | None, int]:
    """UMA memória por assunto que SE REPETE — renovada, nunca duplicada.

    Generaliza o desenho que só `_remember_route` tinha (spec 013, FR-008: "criar OU
    renovar, nunca duplicar"), porque o mesmo problema reapareceu com força num
    lugar que ninguém previu.

    O CASO QUE A CRIOU (2026-08-13). O Irmão Tobias perguntou o caminho à Nerissa
    por três horas. Cada pergunta gravava um arquivo novo, e ele chegou a **35 das
    40 memórias VIVAS dele sendo a MESMA recusa**. Três efeitos, todos ruins:

      · a vida dele sumiu — 7 transferências, 6 caminhos e 5 informes soterrados
        sob 35 repetições de um não-evento;
      · o contexto DOBROU (9.128 → 20.631 tokens de entrada) e o turno passou de
        68s para 260s, batendo em timeout em 34% das vezes;
      · e, o pior, virou COMBUSTÍVEL: sem intenção e sem urgência biológica, a
        memória era a única bússola do tick autônomo — e ela apontava, 35 vezes,
        para o assunto malresolvido. Ele perguntava porque lembrava de ter
        perguntado.

    Registrar o não-evento estava certo; registrá-lo N vezes é que o transformou no
    fato mais importante da vida do personagem. Aqui a repetição RENOVA e ADENSA: o
    prazo empurra para frente e o texto passa a dizer que se insistiu em vão — o
    que é a informação que faltava, agora em uma memória só.

    Devolve (id, vezes).
    """
    mem_dir = character_folder / "memories"
    now = int(time.time())
    if mem_dir.is_dir():
        for path in sorted(mem_dir.glob("*.md")):
            fm, _ = read_doc(path)
            if fm.get("evento") != evento or memory_about(fm) != about:
                continue
            vezes = int(fm.get("vezes") or 1) + 1
            fm["vezes"] = vezes
            fm["timestamp_end"] = now + ttl_for(memory_kind(fm), intensity, evento)
            fm["state"] = "active"       # revive a vencida: aconteceu de novo
            # `involved` pode CRESCER: a mesma insistência com mais gente envolvida
            # não deve perder vínculo (é o que costura o mundo).
            juntos = list(dict.fromkeys(list(fm.get("involved") or []) + list(involved)))
            fm["involved"] = juntos
            # A VALÊNCIA TAMBÉM SOBREVIVE À RENOVAÇÃO. Sem isto, transformar uma
            # memória em recorrente APAGA o afeto — e o afeto é o que faz o
            # personagem passar a desgostar do item que já o frustrou. A suíte
            # pegou exatamente isso (fases 48 e 49). Cresce como `involved`: a
            # mesma frustração com mais alvos não perde os anteriores.
            if valence:
                limpo = {k: v for k, v in valence.items()
                         if v in ("positiva", "negativa")}
                if limpo:
                    fm["valence"] = {**(fm.get("valence") or {}), **limpo}
            # `frag` vazio = o consumidor histórico (`unanswered`), cuja prosa
            # de insistência é afinada para pergunta e está travada em teste.
            cauda = _reincidencia(vezes, frag) if frag else _insistencia(vezes)
            corpo = texto + cauda
            fm["summary"] = (summary.strip() or _short_summary(corpo)) + cauda
            write_doc(path, fm, corpo)
            return fm.get("id"), vezes
    return _write_memory(character_folder, texto, intensity=intensity,
                         involved=involved, about=about, summary=summary,
                         evento=evento, valence=valence), 1


def _remember_route(character_folder: Path, route_id: str,
                    route_name: str = "") -> str | None:
    """Cria OU renova a memória de rota — nunca duplica (spec 013, FR-008).

    Esta é a metade "usar renova" do desenho: percorrer o caminho empurra o
    prazo para frente, e uma rota vencida REVIVE ao ser percorrida de novo.
    Sem isso, a classe de rota ou seria imortal ou se perderia sozinha.
    """
    mem_dir = character_folder / "memories"
    now = int(time.time())
    if mem_dir.is_dir():
        for path in sorted(mem_dir.glob("*.md")):
            fm, body = read_doc(path)
            if memory_kind(fm) != ROTA or memory_about(fm) != route_id:
                continue
            fm["timestamp_end"] = now + _TTL_ROTA
            fm["state"] = "active"  # revive a vencida: refez o caminho, lembrou
            write_doc(path, fm, body)
            return fm.get("id")
    nome = route_name or route_id
    return _write_memory(
        character_folder,
        f"Sei o caminho: {nome}. Já o percorri, e os pés lembram por onde vai.",
        kind=ROTA, about=route_id, intensity="medium",
        # o SUMMARY é o que o personagem lê ao lembrar (`recall` mostra ele, não o
        # corpo). "o caminho: Rua do Portão" não é uma frase — é um rótulo de campo,
        # e chegava assim ao jogador. O corpo já era bom; o resumo é que não era.
        summary=f"Sei o caminho: {nome}.", evento="learn_route",
    )


# --------------------------------------------------------------------------- #
# Rastro (spec 034, US4) — marca FÍSICA de deslocamento, mora no LUGAR, não
# numa mente. Primitivas de nível 0, irmãs de `_write_memory`/`_remember_route`
# — administrar um registro que decai por tempo/intensidade é o job deste
# módulo; `deslocamento.py` (nível 1) só CHAMA, nunca duplica a mecânica.
# --------------------------------------------------------------------------- #

def _roll_trace_d20() -> int:
    """Dado PRÓPRIO da marca física — deliberadamente SEPARADO de
    `rolagem._roll_d20` (o dado partilhado que ações arbitradas usam).

    Motivo: `_leave_trace` roda incondicionalmente em TODO deslocamento —
    inclusive o que resulta de um `persuade`/`carry` cuja régua está no
    extremo determinista (nota 0/10, SEM dado nenhum por desenho). Vários
    testes já existentes monkeypatcham `rolagem._roll_d20` para AFIRMAR que
    nenhum dado rola nesses extremos; usar o mesmo símbolo aqui quebraria
    essa garantia por um motivo que não tem nada a ver com ela — a marca
    física é uma variação de SABOR, não uma decisão arbitrada. Canal próprio,
    injetável nos testes desta spec sem tocar o dado compartilhado.
    """
    return random.randint(1, 20)


def _leave_trace(location_folder: Path, quem: str, direcao: str, evento: str) -> str:
    """Cria a marca física de PARTIDA/CHEGADA no lugar (spec 034, US4).

    `quem`/`direcao` são GROUND-TRUTH do Motor — secretos até uma futura ação
    de investigar (item 14-γ) os revelar; nenhuma tool desta spec os expõe.
    Decai por RELÓGIO (`criado_em` + `ttl_seconds`), nunca por uso — ao
    contrário de `memory.md` (renovação-por-uso, spec 013): uma pegada não
    fica mais funda por alguém pisar nela de novo. Nasce SEMPRE, com ou sem
    testemunha — quem chama decide QUANDO (os dois hooks de
    `deslocamento.py`), esta função só sabe COMO.

    A rolagem (DEX de quem se moveu) desloca prazo/intensidade um degrau pra
    cima ou pra baixo — nunca sai da faixa baixa/curta (research.md §3).
    """
    now = int(time.time())
    ttl = _RASTRO_TTL_BASE
    intensity = "small"
    try:
        actor_fm, _ = read_doc(find_character_folder(quem) / "character.md")
        mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("DEX", 10))
    except io.MotorError:
        mod = 0
    total = _roll_trace_d20() + mod
    if total >= 15:
        ttl = min(_RASTRO_TTL_MAX, ttl + _RASTRO_TTL_STEP)
    elif total <= 5:
        ttl = max(_RASTRO_TTL_MIN, ttl - _RASTRO_TTL_STEP)
    rastro_id = new_id("rastro")
    folder = location_folder / rastro_id
    fm = {
        "type": "rastro", "id": rastro_id, "quem": quem, "direcao": direcao,
        "evento": evento, "criado_em": now, "ttl_seconds": ttl,
        "intensity": intensity,
    }
    write_doc(folder / "rastro.md", fm, "Uma marca recente de passagem.")
    return rastro_id


def _is_trace_active(fm: dict, now: float | None = None) -> bool:
    """Decaimento FÍSICO da marca (spec 034) — avaliação preguiçosa, nunca
    processo de fundo. Nenhum consumidor nesta spec; existe para quem um dia
    ler `rastro` (item 14-γ)."""
    if now is None:
        now = time.time()
    criado_em = fm.get("criado_em") or 0
    ttl = fm.get("ttl_seconds") or 0
    return (now - criado_em) < ttl


def _raise_intensity(tier: str) -> str:
    """Uma faixa de intensidade ACIMA (spec 030) — inverso de `_lower_intensity`.
    Teto `giant`: um compromisso não pode pesar mais que o máximo da escala."""
    escada = {"small": "medium", "medium": "large", "large": "giant",
             "giant": "giant"}
    return escada.get(tier, "medium")


# spec 032 (Frente de custo de `curar`): base por banda — média pesa mais
# que alta (US1); piso garante que ALGUMA perda sempre acontece (SC-006),
# mesmo no melhor caso (nível de proficiência máximo).
def _forgotten_percent(banda: str, nivel_cura: int, wis_curador: int,
                          con_curado: int) -> float:
    """Percentual das memórias ativas do curado a marcar `esquecida`
    (research.md §3). `nivel_cura` (proficiência do socorrista no domínio
    `cura`, 0-5) é o fator PREDOMINANTE — cada nível reduz bem mais que o
    ajuste fino de WIS do socorrista/CON do curado. Nunca chega a zero
    (piso `_PISO_PERCENTUAL_ESQUECIDO`) — reerguer sempre custa algo."""
    base = _PERCENTUAL_BASE_POR_BANDA.get(banda, 0.0)
    if base <= 0:
        return 0.0
    reducao_nivel = 0.05 * nivel_cura
    reducao_wis = 0.01 * rolagem.attr_modifier(wis_curador)
    reducao_con = 0.01 * rolagem.attr_modifier(con_curado)
    percentual = base - reducao_nivel - reducao_wis - reducao_con
    return max(_PISO_PERCENTUAL_ESQUECIDO, percentual)


def _forget_memories(character_folder: Path, percentual: float) -> list[str]:
    """O custo de `curar` (spec 032): entre as memórias ATIVAS do dono da
    pasta, marca as MAIS VÍVIDAS primeiro (giant→large→medium→small —
    "perde memórias VIVAS" é sobre o que mais pesava) como
    `state: esquecida`. N = arredondado pra CIMA (`math.ceil`), mínimo 1
    se houver ao menos uma ativa (SC-006 — nunca um resultado de graça).
    NUNCA remove o arquivo (Princípio IV) — só marca; `_is_alive` já trata
    `esquecida` como não-viva, e `_weigh_memories`/`proficiencies_for` já
    pesam ZERO, e `_renew_memory` já nunca revive (as três mudanças desta
    mesma spec)."""
    mem_dir = character_folder / "memories"
    if not mem_dir.is_dir():
        return []
    ativas = []
    for path in sorted(mem_dir.glob("*.md")):
        fm, body = read_doc(path)
        if fm.get("type") != "memory" or memory_kind(fm) != ACONTECIMENTO:
            continue
        if not _is_alive(fm):
            continue
        ativas.append((path, fm, body))
    if not ativas:
        return []
    ativas.sort(key=lambda pfb: _INTENSITY_ORDER_DESC.get(pfb[1].get("intensity"), 2))
    n = max(1, math.ceil(percentual * len(ativas)))
    tocadas: list[str] = []
    for path, fm, body in ativas[:n]:
        fm["state"] = "esquecida"
        write_doc(path, fm, body)
        tocadas.append(fm.get("id"))
    return tocadas


def _renew_memory(character_folder: Path, entity_id: str | None = None,
                  memoria_id: str | None = None, *, modo: str = "prazo") -> list[str]:
    """Generaliza a renovação que só `_remember_route` tinha (spec 030).

    Modo `prazo` (Frente C — US3): toda memória `acontecimento` VIVA (ou
    vencida — revive) que envolve `entity_id` ganha uma EXTENSÃO fracionária
    de prazo — metade do TTL-base da PRÓPRIA intensidade dela, nunca um
    reset pleno (isso continua exclusivo de rota, `_remember_route`, campo
    `about` em vez de `involved` — mecanismos deliberadamente separados,
    research.md). O baseline é o MAIOR entre "agora" e o prazo atual —
    renovar NUNCA encurta uma memória que já vencia tarde.

    Modo `intensidade` (Frente D — US4): só a memória `memoria_id`
    específica sobe um degrau (`_raise_intensity`, teto `giant`) e ganha o
    TTL-base do NOVO degrau, reiniciado a partir de agora (mesmo espírito
    do reset de rota — um compromisso relembrado é renovado por inteiro).

    spec 032: memória `esquecida` NUNCA é tocada aqui, nos dois modos —
    é o que torna esse estado mais definitivo que `expired` (que ainda
    revive por este mesmo mecanismo). O `continue` abaixo vem ANTES de
    qualquer outra checagem, de propósito.
    """
    mem_dir = character_folder / "memories"
    if not mem_dir.is_dir():
        return []
    now = int(time.time())
    tocadas: list[str] = []
    for path in sorted(mem_dir.glob("*.md")):
        fm, body = read_doc(path)
        if fm.get("type") != "memory" or memory_kind(fm) != ACONTECIMENTO:
            continue
        if fm.get("state") == "esquecida":
            continue
        if modo == "intensidade":
            if fm.get("id") != memoria_id:
                continue
            nova_intensidade = _raise_intensity(fm.get("intensity"))
            fm["intensity"] = nova_intensidade
            fm["timestamp_end"] = now + _TTL_BY_INTENSITY.get(
                nova_intensidade, _TTL_BY_INTENSITY["medium"])
        else:
            if not entity_id or entity_id not in memory_involved(fm):
                continue
            if fm.get("evento") in _EVENTOS_SEM_RENOVACAO:
                continue          # registro de estado não se renova (ver _TTL_BY_EVENTO)
            extensao = _TTL_BY_INTENSITY.get(
                fm.get("intensity"), _TTL_BY_INTENSITY["medium"]) // 2
            fm["timestamp_end"] = max(fm.get("timestamp_end") or now, now) + extensao
        fm["state"] = "active"  # revive a vencida: foi revista, lembrada de novo
        write_doc(path, fm, body)
        tocadas.append(fm.get("id"))
    return tocadas


def _record_hearsay(ouvinte_folder: Path, fontes_fm: list | dict, sobre: str,
                    trecho: str, narrador_id: str) -> str | None:
    """Grava no ouvinte a memória de RECONTO — UMA, do conjunto das fontes (spec 017,
    generalizada no item 52).

    `fontes_fm` é a LISTA das lembranças que o narrador tinha sobre o assunto, e
    `trecho` é o Z: o que ele CONTOU, em uma peça só, escrito pela Mente do mundo. Um
    dict solto ainda é aceito (é o caso de uma fonte só) para não quebrar chamador.

    Antes era uma memória POR EPISÓDIO: perguntar da Hulda à Mira gravava 18 arquivos
    num turno, e é o que fez a Mira acumular 913 memórias. Agora é uma, e as medidas do
    conjunto entram assim:

      - GRAU: se QUALQUER fonte já era boato, o reconto inteiro é 3º grau e ANÔNIMO
        ("dizem por aí"). Basta uma para a cadeia estar contaminada — decisão do
        mantenedor; o contrário deixaria um boato passar por testemunho.
      - PESO: a MAIOR intensidade entre as fontes, uma faixa abaixo (piso small). O que
        marca é o que se conta com mais força; e a reputação segue pesando menos que a
        vivência, que é a regra original.
      - SUJEITOS: a união dos envolvidos de TODAS as fontes, menos os narradores delas.
        Sai das FONTES, nunca do texto do Z — o Z pode distorcer à vontade (é reconto
        humano, e distorcer é o comportamento pedido), mas `involved` é o que costura o
        mundo: derivá-lo do texto deixaria referência solta e vínculo de relação
        nascido de frase que ninguém disse.
      - VALÊNCIA: a união das valências das fontes. O Árbitro não reavalia.
      - `ouvido_de`: o narrador imediato, secreto. No 3º grau ele não entra em
        `involved` — a defesa do sigilo na origem.
    """
    fontes = [fontes_fm] if isinstance(fontes_fm, dict) else list(fontes_fm or [])
    if not fontes:
        return None
    boato = any(memory_ouvido_de(f) is not None for f in fontes)
    intensidade = _lower_intensity(min(
        (f.get("intensity") or "medium" for f in fontes),
        key=lambda i: _INTENSITY_ORDER.get(i, 99)))
    narradores_das_fontes = {memory_ouvido_de(f) for f in fontes} - {None}
    sujeitos, valence = [], {}
    for f in fontes:
        for x in memory_involved(f):
            if x not in narradores_das_fontes and x not in sujeitos:
                sujeitos.append(x)
        valence.update(memory_valence(f))
    if boato:
        involved = list(sujeitos)               # 3º grau: origem anônima
        corpo = f"Dizem por aí: {trecho}"
    else:
        involved = sujeitos + [narrador_id]     # 2º grau: narrador nomeado (público)
        corpo = f"{name_of(narrador_id)} me contou: {trecho}"
    return _write_memory(
        ouvinte_folder, corpo,
        intensity=intensidade, involved=involved, valence=valence or None,
        ouvido_de=narrador_id, evento="hearsay_reconto",
        summary=(f"dizem de {name_of(sobre)}" if boato
                 else f"{name_of(narrador_id)} contou de {name_of(sobre)}"),
    )


def memory_valence(fm: dict) -> dict[str, str]:
    """O mapa {alvo: sinal} de uma memória. Ausente ⇒ vazio (memória neutra)."""
    val = fm.get("valence")
    if not isinstance(val, dict):
        return {}
    return {k: v for k, v in val.items()
            if isinstance(k, str) and v in (POSITIVA, NEGATIVA)}


def memory_ouvido_de(fm: dict) -> str | None:
    """De quem se ouviu este reconto (spec 017). None = memória de 1º grau (vivida).

    SEGREDO ATÉ DO ÁRBITRO: NENHUMA função surfaçadora (`remembered_about`,
    `prose_of`, `_context_for_prompt`, `_character_summary`, handlers de /api)
    pode chamar este acessor — só o Motor (para o grau do próximo reconto) e as
    ferramentas de rastreabilidade/teste. É o terceiro nível de sigilo do projeto.
    """
    fonte = fm.get("ouvido_de")
    return fonte if isinstance(fonte, str) and fonte else None


def _lower_intensity(tier: str) -> str:
    """Uma faixa de intensidade abaixo (spec 017): boato pesa menos a cada grau.

    Piso `small` — um episódio já trivial não decai, e trivialidade ninguém
    reconta. Reusa a ordem de `_INTENSITY_ORDER`; o peso menor faz
    `familiarity_with`/`sentiment_toward` pesarem o reconto de leve, sem campo novo.
    """
    escada = {"giant": "large", "large": "medium", "medium": "small",
              "small": "small"}
    return escada.get(tier, "small")


def remember_recurring(target: str, content: str, *, about: str, evento: str,
                       involved: list[str] | None = None, intensity: str = "small",
                       summary: str = "", frag: str = "",
                       valence: dict[str, str] | None = None
                       ) -> tuple[str | None, int]:
    """SINK do fato que SE REPETE — irmão de `remember`, mesma fronteira.

    `remember` grava um arquivo por vez que o fato acontece. Quando o fato é O
    MESMO insistido (a recusa que se re-tenta, a acusação repetida), isso o
    transforma no assunto mais importante da vida do personagem e vira combustível
    do tick autônomo — ver `_remember_recurring` para o caso que criou a regra.

    Aqui a repetição RENOVA e ADENSA, em uma memória só. Devolve (id, vezes)."""
    try:
        folder = find_character_folder(target)
    except Exception:
        return None, 0
    if folder is None or not (folder / "character.md").exists():
        return None, 0
    return _remember_recurring(folder, content, evento=evento, about=about,
                               involved=involved or [], intensity=intensity,
                               summary=summary, frag=frag, valence=valence)


def remember(target: str, content: str, *, kind: str = ACONTECIMENTO,
             intensity: str = "medium", involved: list[str] | None = None,
             about: str | None = None, summary: str = "",
             valence: dict[str, str] | None = None,
             evento: str | None = None, domain: str | None = None) -> str | None:
    """SINK puro de memória (spec 038, R7): recebe TUDO pronto — a intensidade e a
    valência já vêm DECIDIDAS pelo ato (viajam no fato, não numa tabela central) —,
    resolve a pasta do `target`, valida o frontmatter e grava. Não deriva nada de
    evento (DIP: quem sabe o afeto do ato é o ato). Devolve o id, ou None se
    `target` não tem pasta. É o ponto por onde a memória do ATOR e a da TESTEMUNHA
    passam — a mesma escrita, sem a tool presente."""
    try:
        folder = find_character_folder(target)
    except Exception:
        return None
    if folder is None or not (folder / "character.md").exists():
        return None
    return _write_memory(
        folder, content, kind=kind, intensity=intensity,
        involved=list(involved or []), about=about, summary=summary,
        valence=valence, evento=evento, domain=domain)


def record_event(quem: str, texto: str, evento: str, involved: list[str],
                 valence: dict[str, str] | None = None,
                 lugar_sinal: str | None = None, seq: int = 0,
                 about: str | None = None, intensity: str = "small") -> str | None:
    """Funil ÚNICO de escrita de memória de ato (spec 020, extraído do `lembrar`
    de `_record_events`). Toda tool mutadora registra o que fez por aqui.

    Resolve a pasta ATUAL de `quem` (find_character_folder — pós-aplicação, então
    vê deslocamentos deste turno); acrescenta SEMPRE o lugar ao `involved` (apego
    por convívio) e o SINAL do lugar só quando o evento tem carga (`lugar_sinal`).
    A gravação em si é do SINK `remember` (spec 038); aqui mora só a orquestração
    (lugar + renovação). Devolve o id da memória, ou None se `quem` não tem pasta.

    `intensity` (spec 038, T016): a RELEVÂNCIA agora viaja COM o ato — cada
    recordador a declara (o default `small` cobre a maioria; o ato mais grave sobe
    a nota). Morreu a tabela central `_RELEVANCE_BY_EVENT`, que uma tool nova tinha
    de lembrar de atualizar (o anti-padrão que a spec 013 nomeou).
    """
    try:
        folder = find_character_folder(quem)
    except Exception:
        return None
    if folder is None or not (folder / "character.md").exists():
        return None
    inv = [x for x in involved if x != quem]
    val = {k: v for k, v in (valence or {}).items()
           if k != quem and v in (POSITIVA, NEGATIVA)}
    loc_file = folder.parent / "location.md"
    lugar = None
    if loc_file.exists():
        lfm, _ = read_doc(loc_file)
        lugar = lfm.get("id")
    if lugar and lugar != quem:
        if lugar not in inv:
            inv.append(lugar)            # apego por convívio, sempre
        if lugar_sinal in (POSITIVA, NEGATIVA):
            val[lugar] = lugar_sinal     # afeto pelo lugar, só quando há carga
    # spec 030 (Frente C): rever/interagir com alguém RENOVA as memórias já
    # existentes sobre essa entidade — antes de escrever a memória NOVA deste
    # evento (senão ela mesma seria "renovada" no ato de nascer). Extensão
    # fracionária (_renew_memory), não reset pleno.
    for envolvido in inv:
        _renew_memory(folder, entity_id=envolvido, modo="prazo")
    return remember(
        quem, texto, intensity=intensity,
        involved=inv, valence=val or None, evento=evento, about=about)


def _char_name(cid: str) -> str:
    try:
        folder = find_character_folder(cid)
    except Exception:
        return cid
    if folder is None or not (folder / "character.md").exists():
        return cid
    fm, _ = read_doc(folder / "character.md")
    return fm.get("name") or cid


def _rec(created: list, quem: str, texto: str, evento: str, involved: list,
         valence: dict | None = None, lugar_sinal: str | None = None,
         about: str | None = None, intensity: str = "small") -> None:
    mem_id = record_event(quem, texto, evento, involved,
                          valence=valence, lugar_sinal=lugar_sinal, about=about,
                          intensity=intensity)
    if mem_id is not None:
        created.append({"target": quem, "id": mem_id, "event": evento})


def _rec_unico(created: list, quem: str, texto: str, evento: str, involved: list,
               *, about: str, intensity: str = "small") -> None:
    """Como `_rec`, mas para o fato que SE REPETE: renova em vez de duplicar.

    A chave é o `about` — quem chama decide o que conta como "o mesmo assunto"
    (o par informante+assunto, no caso da pergunta que não rendeu). Ver
    `_remember_recurring` para o porquê de isto existir."""
    try:
        folder = find_character_folder(quem)
    except MotorError:
        return
    mem_id, vezes = _remember_recurring(folder, texto, evento=evento, about=about,
                                        involved=involved, intensity=intensity)
    if mem_id is not None:
        created.append({"target": quem, "id": mem_id, "event": evento,
                        "vezes": vezes})


def _record_arma(created: list, quem: str, arma: str, acertou: bool) -> None:
    """Memória de USO da arma (spec 016 §3a) — à parte do golpe, e `small`."""
    nm = name_of(arma)
    if acertou:
        _rec(created, quem, f"{nm} cravou fundo.", "wield", [arma],
             valence={arma: POSITIVA})  # arma que acertou (ex-weapon_hit)
    else:
        _rec(created, quem, f"{nm} passou ao largo.", "wield", [arma],
             valence={arma: NEGATIVA})  # arma que errou (ex-weapon_miss)


def _record_attack(character_id: str, attacks_applied: list, rejected: list) -> list:
    created: list = []
    eu = _char_name(character_id)
    for op in attacks_applied or []:
        alvo = op.get("alvo") or op.get("target")
        if not alvo:
            continue
        caiu = bool(op.get("derrota"))
        ev = "defeat" if caiu else "attack"
        intens = "giant" if caiu else "large"  # ex-_RELEVANCE_BY_EVENT[defeat/attack]
        par = [character_id, alvo]
        arma = op.get("arma")
        com = f" com {name_of(arma)}" if arma else ""
        _rec(created, character_id,
             f"Golpeei {_char_name(alvo)}{com}." + (" Caiu." if caiu else ""), ev, par,
             intensity=intens)
        _rec(created, alvo, f"{eu} me golpeou." + (" Caí." if caiu else ""), ev, par,
             valence={character_id: NEGATIVA}, lugar_sinal=NEGATIVA, intensity=intens)
        if arma:
            _record_arma(created, character_id, arma, acertou=True)
    # o ERRO não é op aplicada — é REJEIÇÃO; lê-la grava a (des)confiança pela arma
    for r in rejected or []:
        if not isinstance(r, dict):
            continue
        regra = r.get("regra")
        if regra not in ("ataque_errou", "golpe_absorvido"):
            continue
        arma = r.get("arma") or (r.get("valores") or {}).get("arma")
        if arma:
            _record_arma(created, character_id, arma,
                         acertou=(regra == "golpe_absorvido"))
    return created


def _record_cura(character_id: str, cura_applied: list) -> list:
    """Memória nova nos DOIS lados de um resgate bem-sucedido (spec 032) —
    além do rebaixamento de memórias antigas pra `esquecida`, que já
    aconteceu dentro do próprio executor (`cura._apply_cura_ops`), antes
    deste registro rodar. A banda BAIXA (não curou) não gera memória
    nenhuma aqui — só o esforço, que é fadiga, não lembrança.
    Deliberadamente NÃO cria nenhuma intenção
    (`[[server-never-owns-character-agency]]`, FR-010 do spec.md) — o
    gancho pro curado "sentir dívida" é só esta memória; quem decide se
    ele declara isso como intenção é o próprio personagem, do lado do
    client (`deriveWhisper`, spec 026)."""
    created: list = []
    eu = _char_name(character_id)
    for op in cura_applied or []:
        if not op.get("curou"):
            continue
        alvo = op.get("alvo")
        if not alvo:
            continue
        par = [character_id, alvo]
        _rec(created, character_id, f"Socorri {_char_name(alvo)}.", "heal", par,
             intensity="large")
        _rec(created, alvo, f"{eu} me socorreu.", "healed", par,
             valence={character_id: POSITIVA}, intensity="large")  # ex-healed_by
    return created


def _record_carry(character_id: str, carries_applied: list) -> list:
    created: list = []
    eu = _char_name(character_id)
    for op in carries_applied or []:
        alvo = op.get("alvo") or op.get("target")
        if not alvo:
            continue
        par = [character_id, alvo]
        _rec(created, character_id, f"Levei {_char_name(alvo)} comigo.", "carry", par,
             intensity="medium")
        _rec(created, alvo, f"{eu} me levou consigo.", "carry", par, intensity="medium")
    return created


def _record_persuade(character_id: str, persuades_applied: list) -> list:
    created: list = []
    eu = _char_name(character_id)
    for op in persuades_applied or []:
        alvo = op.get("personagem") or op.get("alvo")
        if not alvo:
            continue
        par = [character_id, alvo]
        _rec(created, character_id, f"Convenci {_char_name(alvo)} a partir.", "persuade", par,
             intensity="medium")
        _rec(created, alvo, f"{eu} me convenceu a partir.", "persuade", par,
             intensity="medium")
    return created


def _record_trade(character_id: str, trades_applied: list) -> list:
    created: list = []
    eu = _char_name(character_id)
    for op in trades_applied or []:
        parceiro = op.get("parceiro") or op.get("partner")
        if not parceiro:
            continue
        par = [character_id, parceiro]
        _rec(created, character_id, f"Negociei com {_char_name(parceiro)}.", "trade", par)
        _rec(created, parceiro, f"{eu} negociou comigo.", "trade", par)
    return created


# Eventos que uma memória precisa ter para participar de `dono` (spec 036) —
# o conjunto é FECHADO e determinístico (Princípio XI): `witness_theft` (e
# qualquer evento de furto) fica de fora DE PROPÓSITO — furto muda posse,
# nunca dono, e não pode sobrescrever uma reivindicação de dono já conhecida
# por algo mais antigo (ex.: quem só testemunhou um empréstimo antes).
def dono(entidade_id: str, personagem_id: str) -> str | None:
    """Quem `personagem_id` acha que é dono de `entidade_id` — uma RELAÇÃO,
    não um conjunto (spec 036): lê a memória mais RECENTE e ATIVA de
    `personagem_id` sobre `entidade_id`, com `evento` em `_DONO_EVENTOS`, e
    devolve o alvo que ELA aponta (campo `about` — o mesmo em qualquer cópia
    do fato, vivida ou testemunhada). Sem memória reconhecida, cai no
    fallback de posse física (`fisica.carried_item_ids`). Sem nenhum dos dois,
    indefinido (None). `personagem_id` sempre "tem" a si mesmo, sem precisar
    de memória — é a base que deixa a própria estrutura sempre andável.

    Vive em `memoria.py`, não em `percepcao.py`: é a única leitura desta
    família que `_record_witness` (aqui mesmo) precisa fazer por-testemunha,
    e `percepcao.py` já importa `memoria` — o caminho inverso seria ciclo."""
    if entidade_id == personagem_id:
        return personagem_id
    # As memórias em `_DONO_EVENTOS` (transfer/emprestimo) sempre envolvem DOIS
    # personagens (o de fora e o emprestador/doador) além do item — `involved`
    # cita os três. Sem isto, `entidade_id in memory_involved(fm)` casaria
    # também com o OUTRO personagem (ele não é o item, mas está lá como
    # participante) — achado testando o caso do empréstimo (2026-08-01):
    # perguntar "quem é dono de Torvin" batia na memória do casaco. `about`
    # (spec 036) só reivindica dono de ITEM nestes eventos — nunca de
    # personagem (item 8 não existe, ninguém escreve esse tipo de memória
    # hoje); a checagem abaixo é precisão de leitura, não uma restrição nova
    # de "quem pode ser dono" — se um evento de posse-de-personagem nascer um
    # dia, ele desambiguará do próprio jeito, sem tocar aqui.
    try:
        find_character_folder(entidade_id)
        return None  # entidade_id é personagem: nenhum evento hoje reivindica isso
    except io.MotorError:
        pass
    try:
        folder = find_character_folder(personagem_id)
    except io.MotorError:
        return None
    mem_dir = folder / "memories"
    melhor_ts, melhor_alvo = None, None
    if mem_dir.is_dir():
        _expire_memories(folder)
        now = time.time()
        for path in sorted(mem_dir.glob("*.md")):
            fm, _ = read_doc(path)
            if fm.get("type") != "memory" or fm.get("evento") not in _DONO_EVENTOS:
                continue
            if not _is_alive(fm, now):
                continue
            if entidade_id not in memory_involved(fm):
                continue
            ts = fm.get("timestamp_start") or 0
            if melhor_ts is None or ts > melhor_ts:
                melhor_ts, melhor_alvo = ts, fm.get("about")
    if melhor_alvo:
        return melhor_alvo
    if entidade_id in fisica.carried_item_ids(personagem_id):
        return personagem_id
    return None


def _record_transfer(character_id: str, transfers_applied: list, present_chars: dict) -> list:
    created: list = []
    eu = _char_name(character_id)
    for op in transfers_applied or []:
        item_id = op.get("item")
        item = name_of(item_id)
        destino = op.get("to") or op.get("destino")
        if destino in present_chars and destino != character_id and op.get("emprestimo"):
            # EMPRÉSTIMO (spec 036, US2): posse muda, dono não — `about`
            # aponta o EMPRESTADOR (character_id) nas DUAS cópias, ao
            # contrário da doação (que aponta o receptor). Sem valência de
            # doação — não é presente, é confiança temporária.
            _rec(created, character_id, f"Emprestei {item} a {_char_name(destino)}.",
                 "emprestimo", [character_id, destino, item_id], about=character_id)
            _rec(created, destino, f"{eu} me emprestou {item}.",
                 "emprestimo", [character_id, destino, item_id], about=character_id)
        elif destino in present_chars and destino != character_id:
            # doação real (spec 036): `about` aponta o RECEPTOR nas DUAS
            # cópias — é o mesmo fato, lido igual por quem deu e por quem
            # recebeu. `dono` (memoria.py) passa a reconhecer isso.
            _rec(created, character_id, f"Entreguei {item} a {_char_name(destino)}.",
                 "transfer", [character_id, destino, item_id],
                 valence={destino: POSITIVA}, lugar_sinal=POSITIVA,  # ex-gift_given
                 about=destino)
            _rec(created, destino, f"{eu} me entregou {item}.",
                 "transfer", [character_id, destino, item_id],
                 valence={character_id: POSITIVA,
                          item_id: POSITIVA}, lugar_sinal=POSITIVA,  # ex-gift_received
                 about=destino)
        elif destino == character_id:
            # PEGUEI para mim (do chão/contêiner/outro): é AQUISIÇÃO, e a lembrança
            # tem de dizer o VERBO ("peguei") — não um "passou por minhas mãos"
            # ambíguo que o rastreio de intenção confunde com LARGAR (o personagem
            # não sabe se já cumpriu o passo "pegar X"; medição da fatia C, item 38).
            _rec(created, character_id, f"Peguei {item}.",
                 "transfer", [character_id, item_id], about=character_id)
        else:
            # LARGUEI/depositei em local/object/contêiner: soltei da mão, mas retenho
            # a reivindicação — `about` aponta o PRÓPRIO character_id (spec 036). Verbo
            # explícito ("larguei") para não colidir com o "peguei" acima.
            _rec(created, character_id, f"Larguei {item}.",
                 "transfer", [character_id, item_id], about=character_id)
    return created


def _record_persuade_give(character_id: str, actor_folder, applied: list,
                          present_chars: dict) -> list:
    """Persuadir a dar (spec 023): quem DOOU foi o ALVO, não o ator que persuadiu.

    Reusa `_record_transfer` NA PERSPECTIVA DO ALVO — assim o afeto positivo
    (`gift_received`) recai sobre o ALVO em quem recebeu (o "fecha o laço do cão").
    O present map é o da vista do alvo: o ator entra como presente, o alvo sai.
    """
    created: list = []
    for op in applied or []:
        alvo = op.get("alvo")
        para = op.get("para")
        item_id = op.get("item")
        present_from_alvo = dict(present_chars or {})
        present_from_alvo[character_id] = actor_folder
        created += _record_transfer(alvo, [{"item": item_id, "to": para}],
                                    present_from_alvo)
        # item 8 da skill loreforge-arbitrated-action: a VIRADA (o dado que fez ceder
        # o que o juízo negava) merece ficar mais viva que a doação rotineira. O DONO
        # guarda uma lembrança `medium` de ter cedido contra a própria vontade.
        if op.get("virada"):
            _rec(created, alvo,
                 f"Entreguei {name_of(item_id)} — e até hoje não sei o que me deu.",
                 "gift_reluctant", [alvo, character_id, item_id], intensity="medium")
    return created


def _record_stolen(character_id: str, applied: list) -> list:
    """Furto (spec 023): o FLAGRANTE deixa no DONO memória NEGATIVA `large` dirigida
    ao ladrão — dispara o portão de trauma (has_trauma_from: tão grave quanto um
    golpe). O furto LIMPO NÃO deixa memória no dono (ele não soube). O ladrão guarda
    uma lembrança tênue (`small`) do próprio furto, tenha levado ou não."""
    created: list = []
    ladrao = _char_name(character_id)
    for op in applied or []:
        dono = op.get("de")
        item_id = op.get("item")
        item = name_of(item_id)
        if op.get("flagrado"):
            texto = (f"{ladrao} me roubou {item} diante dos meus olhos."
                     if op.get("levou") else
                     f"{ladrao} tentou me roubar {item} — eu o peguei em flagrante.")
            _rec(created, dono, texto, "stolen", [dono, character_id, item_id],
                 valence={character_id: NEGATIVA}, intensity="large")  # ex-stolen_from/stolen
        if op.get("levou"):
            _rec(created, character_id, f"Surrupiei {item} de {_char_name(dono)}.",
                 "theft", [character_id, dono, item_id])
        # item 8 da skill: a VIRADA fica no LADRÃO — o golpe de sorte ou o azar que
        # o traiu merece ser mais que a nota `small` do furto rotineiro.
        if op.get("virada"):
            if op.get("levou") and not op.get("flagrado"):
                txt = f"Tirei {item} de {_char_name(dono)} à vista de todos, e ninguém viu."
            else:
                # faltava o VERBO: "Fui flagrado tentando Moeda de Prata de X" não é
                # português. O que se tenta é o furto, não o objeto.
                txt = (f"Fui flagrado tentando furtar {item} de "
                       f"{_char_name(dono)} — logo eu.")
            _rec(created, character_id, txt, "theft_twist", [character_id, dono, item_id],
                 intensity="medium")
    return created


# --------------------------------------------------------------------------- #
# Memória de testemunha (spec 024): a cena tem PLATEIA. O Motor espalha memória
# FACTUAL pelos presentes que PERCEBEM um ato — DETERMINÍSTICO, zero LLM por
# testemunha. Ator e alvo já têm memória de participante; aqui vão os DEMAIS.
# --------------------------------------------------------------------------- #

def _perceive_dc(exposicao) -> int:
    """DC de percepção de uma testemunha para um ato FURTIVO (spec 024).

    Inverte a leitura do steal: lá, exposição ALTA = muita cobertura = furto
    LIMPO (DC baixa para o LADRÃO). Para quem OLHA, é o oposto — quanto mais
    cobertura teve o furto, mais difícil notá-lo. DC = 2*exposição: furto às
    claras (exposição baixa) → DC baixa, quase todos veem; encoberto (alta) → DC
    alta, só o mais atento. Não é cálculo novo de furtividade (FR-012): consome a
    MESMA exposição que o steal já produz.
    """
    return max(0, min(20, 2 * int(exposicao)))


# O afeto positivo à VÍTIMA que faz a testemunha "levar a mal" um degrau acima
# (spec 024, item E8 do exploratório): ver o que amo ser roubado/ferido dói mais.
def _witness_intensity(observador_id: str, base: str,
                       involved: list[str], vitima: str | None = None) -> str | None:
    """Intensidade da memória de testemunha, modulada pelo AFETO/FAMILIARIDADE
    (spec 016) do observador com os envolvidos. None = NÃO gravar (piso, FR-006).

    - ato CARREGADO (base `medium`+): sempre memorável, a qualquer um (FR-007).
    - ato BANAL (`small`): só fica se o observador tem vivência com algum envolvido.
    GRADUAÇÃO do carregado (spec 024, refino do mantenedor 2026-07-23): o furto
    flagrado e o golpe que só fere marcam `medium` — ABAIXO do portão de trauma
    (`has_trauma_from` exige large+): a testemunha fica de pé-atrás, mas coopera.
    Já DERRUBAR alguém (derrota) é momentoso: `large`, e CRUZA o portão de propósito
    — quem vê outro ser derrubado às claras passa a temer quem o derrubou. Nunca
    `giant` (essa vivacidade é só da VÍTIMA; a testemunha fica um degrau abaixo).

    E8 (mantenedor 2026-07-23): a raiva não é plana. Quem AMA a vítima leva o ato
    carregado um degrau acima — reusa `sentiment_toward` (016). Ver o próprio ente
    querido ser roubado/ferido sobe `medium`→`large`, cruzando o portão de trauma:
    quem rouba na frente de quem ama a vítima faz um inimigo, não só um desafeto.
    """
    if base in ("medium", "large", "giant"):
        tier = "large" if base in ("large", "giant") else "medium"
        if tier == "medium" and vitima \
                and sentiment_toward(observador_id, vitima) >= _APEGO_VITIMA_FORTE:
            tier = "large"          # amo a vítima: levo a mal de verdade (E8)
        return tier
    laco = max((familiarity_with(observador_id, x) for x in involved if x),
               default=0.0)
    return base if laco > _FAMILIARIDADE_PISO else None


def _witness_facts(character_id: str, outcome: dict) -> list[dict]:
    """Traduz o outcome nas cenas testemunháveis (spec 024). Cada fato:
    envolvidos (a excluir da plateia), texto factual, base de intensidade,
    valência dirigida ao ator (ou None), e ruído (exposição furtiva ou _PUBLICO)."""
    ator = _char_name(character_id)
    fatos: list[dict] = []
    # P1 — FURTO: só o FLAGRADO deixa testemunha; o LIMPO não (nem a vítima soube — SC-002)
    # `furto_dono` (spec 036): o texto/alvo de CADA testemunha pode ser
    # personalizado por `dono(item, testemunha)` em `_record_witness` — o
    # texto/vítima aqui embaixo é só o enquadramento PADRÃO (comportamento
    # de sempre), usado quando a testemunha não sabe de nada melhor.
    for op in outcome.get("steal_ops_applied") or []:
        if not op.get("flagrado"):
            continue
        vitima, item_id = op.get("de"), op.get("item")
        fatos.append({"envolvidos": [character_id, vitima, item_id], "vitima": vitima,
                      "item_furtado": item_id, "furto_dono": True,
                      "texto": f"Vi {ator} furtar {name_of(item_id)} de {_char_name(vitima)}.",
                      "base": "medium", "val_ator": NEGATIVA,
                      "ruido": op.get("exposicao"), "evento": "witness_theft"})
    # NOVO (spec 036, US1) — pegar algo PRA SI (item_transfers, destino é o
    # próprio ator): hoje não gera fato nenhum (o branch abaixo, P2, exclui
    # justamente `destino == character_id`). Aqui não há vítima estrutural
    # — a tool não é `steal`, ninguém chamou de furto. Só vira memória de
    # furto para quem, individualmente, já sabe (via `dono`) que o item não
    # é do tomador — sem fallback: sem essa memória prévia, nada acontece
    # (`furto_dono_obrigatorio`, checado em `_record_witness`).
    for op in outcome.get("item_transfers_applied") or []:
        destino = op.get("to") or op.get("destino")
        item_id = op.get("item")
        if destino == character_id and item_id:
            fatos.append({"envolvidos": [character_id, item_id], "vitima": None,
                          "item_furtado": item_id, "furto_dono": True,
                          "furto_dono_obrigatorio": True,
                          "texto": None,  # nunca usado sem dono resolvido
                          "base": "medium", "val_ator": NEGATIVA,
                          "ruido": _PUBLICO, "evento": "witness_theft"})
    # EXPULSÃO (spec 041) — ato PÚBLICO, valência RELATIVA AO OBSERVADOR: a
    # testemunha sente o expulsor conforme o afeto DELA pelo expulso (derivado em
    # `_record_witness`, `depende_observador`), não um sinal fixo. Referente = o
    # expulso; polaridade = hostil.
    for op in outcome.get("expel_ops_applied") or []:
        alvo = op.get("alvo") or op.get("target")
        if not alvo:
            continue
        fatos.append({"envolvidos": [character_id, alvo],
                      "texto": f"Vi {ator} pôr {_char_name(alvo)} para fora à força.",
                      "base": "medium", "val_ator": None,
                      "depende_observador": True, "referente": alvo,
                      "ruido": _PUBLICO, "evento": "witness_expel"})
    # P2 — GOLPE (carregado, valência- no agressor)
    for op in outcome.get("attack_ops_applied") or []:
        alvo = op.get("alvo") or op.get("target")
        if not alvo:
            continue
        caiu = bool(op.get("derrota"))
        # DERRUBAR é momentoso: memória de impacto (large → portão de trauma na
        # testemunha). Só ferir marca medium. Ataque não tem stealth: ruído público,
        # todos os presentes veem (não passa despercebido — refino 2026-07-23).
        fatos.append({"envolvidos": [character_id, alvo], "vitima": alvo,
                      "texto": (f"Vi {ator} derrubar {_char_name(alvo)}." if caiu
                                else f"Vi {ator} golpear {_char_name(alvo)}."),
                      "base": "large" if caiu else "medium",
                      "val_ator": NEGATIVA, "ruido": _PUBLICO,
                      "evento": "witness_attack"})
    # P2 — SOCORRO (spec 032): só as bandas que CURAM viram fato
    # testemunhável — a banda baixa não deixou nada além de esforço, que
    # é fadiga do socorrista, não memória de terceiros. Público (curar
    # não é furtivo — ninguém esconde estar reerguendo alguém); valência
    # POSITIVA no socorrista, ao contrário do golpe.
    for op in outcome.get("cura_ops_applied") or []:
        if not op.get("curou"):
            continue
        alvo = op.get("alvo")
        if not alvo:
            continue
        fatos.append({"envolvidos": [character_id, alvo], "vitima": None,
                      "texto": f"Vi {ator} socorrer {_char_name(alvo)}.",
                      "base": "medium", "val_ator": POSITIVA, "ruido": _PUBLICO,
                      "evento": "witness_heal"})
    # P2 — negócio / entrega / doação (banal, neutro)
    for op in outcome.get("trade_ops_applied") or []:
        parc = op.get("parceiro") or op.get("partner")
        if parc:
            fatos.append({"envolvidos": [character_id, parc],
                          "texto": f"Vi {ator} negociar com {_char_name(parc)}.",
                          "base": "small", "val_ator": None, "ruido": _PUBLICO,
                          "evento": "witness_trade"})
    for op in outcome.get("item_transfers_applied") or []:
        destino = op.get("to") or op.get("destino")
        item_id = op.get("item")
        if destino and destino != character_id:
            if op.get("emprestimo"):
                # spec 036 (US2): marca DISTINTA de doação — é o que permite
                # quem só testemunhou o empréstimo participar de `dono`
                # depois (posse mudou, dono não; ver _DONO_EVENTOS).
                fatos.append({"envolvidos": [character_id, destino, item_id],
                              "texto": f"Vi {ator} emprestar {name_of(item_id)} a {_char_name(destino)}.",
                              "base": "small", "val_ator": None, "ruido": _PUBLICO,
                              "evento": "witness_emprestimo", "about": character_id})
            else:
                fatos.append({"envolvidos": [character_id, destino, item_id],
                              "texto": f"Vi {ator} entregar {name_of(item_id)} a {_char_name(destino)}.",
                              "base": "small", "val_ator": None, "ruido": _PUBLICO,
                              "evento": "witness_transfer"})
    for op in outcome.get("persuade_give_ops_applied") or []:
        doador, para, item_id = op.get("alvo"), op.get("para"), op.get("item")
        if doador and para:
            fatos.append({"envolvidos": [character_id, doador, para, item_id],
                          "texto": f"Vi {_char_name(doador)} dar {name_of(item_id)} a {_char_name(para)}.",
                          "base": "small", "val_ator": None, "ruido": _PUBLICO,
                          "evento": "witness_persuade_give"})
    # P3 — ACUSAÇÃO (spec 028): sempre pública (não tem furtividade — acusar
    # em voz alta não é discreto), sem valência automática ao ator (o mundo
    # não julga se a acusação é justa, só registra que aconteceu — Decisão 4,
    # research.md da 028).
    for op in outcome.get("accuse_ops_applied") or []:
        alvo = op.get("alvo")
        if alvo:
            fatos.append({"envolvidos": [character_id, alvo],
                          "texto": f"Vi {ator} acusar {_char_name(alvo)}.",
                          "base": "medium", "val_ator": None, "ruido": _PUBLICO,
                          # A plateia também não presencia N brigas quando é a
                          # MESMA brigada de novo. `recorrente` é a chave; `about`
                          # aqui já tem outro dono (o enquadramento de posse do
                          # furto), então não dá para reusar aquele campo.
                          "recorrente": f"acusacao\x00{character_id}\x00{alvo}",
                          "reincidencia": "os vi nisso",
                          "evento": "witness_accuse"})
    return fatos


def _record_witness(character_id: str, actor_folder: Path,
                    present_chars: dict, outcome: dict) -> list[dict]:
    """O LEQUE (spec 024): espalha memória factual pelos presentes que PERCEBEM.

    Roda ao lado de `_record_events`, com o outcome COMPLETO. Determinístico:
    percepção pública passa trivial; a furtiva rola `d20 + mod(WIS)` vs. a
    exposição. ZERO chamada de modelo. Ator e alvo ficam de fora (já têm memória
    de participante — paridade, FR-011). NÃO acrescenta nada ao outcome do ator:
    o relato acontece do lado da TESTEMUNHA, quando ela jogar (D7)."""
    created: list[dict] = []
    for fato in _witness_facts(character_id, outcome):
        involved = [x for x in fato["envolvidos"] if x]
        excluir = set(involved) | {character_id}
        for wid, wfolder in (present_chars or {}).items():
            if wid in excluir:
                continue
            wfm, _ = read_doc(wfolder / "character.md")
            if not wfm or fisica.is_down(wfm):
                continue   # caído não testemunha (G2)
            # PERCEPÇÃO: público = todos veem; furtivo = rolagem por testemunha
            if fato["ruido"] != _PUBLICO:
                dc = _perceive_dc(fato["ruido"])
                # spec 030 (Frente B): fadiga de quem testemunha desconta do
                # mod(WIS) — o refino "percepção modulada por estado" que a
                # spec 024 tinha deixado adiado (achado do bêbado Doncel).
                w_fadiga, w_teto = fisica.ensure_fatigue(wfm)
                total = (rolagem._roll_d20()
                         + rolagem.attr_modifier((wfm.get("attributes") or {}).get("WIS", 10))
                         - fatigue_penalty(w_fadiga, w_teto))
                if total < dc:
                    continue
            # `furto_dono` (spec 036, US1): a memória de furto depende do que
            # ESTA testemunha, individualmente, sabe — `dono(item, wid)`, não
            # de um enquadramento único pra todo mundo. Sem fallback
            # estrutural (`furto_dono_obrigatorio`, pegar-pra-si): sem
            # reivindicação própria, esta testemunha não ganha memória
            # NENHUMA sobre este ato (FR-014) — nem o fato neutro, porque
            # não existe fato neutro pra pegar-pra-si (nunca existiu).
            texto = fato["texto"]
            # `about` estático do fato (ex.: witness_emprestimo já sabe o
            # alvo de cara) é o default; `furto_dono` abaixo pode substituir
            # por um alvo resolvido individualmente, por-testemunha.
            alvo_dono = fato.get("about")
            if fato.get("furto_dono"):
                alvo_dono = dono(fato["item_furtado"], wid)
                obrigatorio = fato.get("furto_dono_obrigatorio")
                if obrigatorio and (alvo_dono is None or alvo_dono == character_id):
                    continue
                if obrigatorio or (alvo_dono is not None and alvo_dono != fato.get("vitima")):
                    # ou não há enquadramento padrão (pegar-pra-si), ou a
                    # testemunha sabe MAIS do que ele (ex.: item emprestado,
                    # não da "vítima" do furto) — nos dois casos, o texto
                    # reflete o alvo REAL, não o genérico.
                    texto = (f"Vi {_char_name(character_id)} furtar "
                             f"{name_of(fato['item_furtado'])}, que "
                             + ("era meu." if alvo_dono == wid
                                else f"era de {_char_name(alvo_dono)}."))
                # senão: mantém o texto/enquadramento padrão de sempre
                # (comportamento-preservante, SC-005) — a testemunha não
                # sabe de nada além do que já era óbvio no ato.
            # INTENSIDADE modulada + piso de saliência (+ afeto à vítima, E8)
            intens = _witness_intensity(wid, fato["base"], involved, fato.get("vitima"))
            if intens is None:
                continue
            inv = [x for x in involved if x != wid]
            if alvo_dono and alvo_dono != wid and alvo_dono not in inv:
                inv.append(alvo_dono)
            loc_file = wfolder.parent / "location.md"
            if loc_file.exists():
                lfm, _ = read_doc(loc_file)
                loc_id = lfm.get("id")
                if loc_id and loc_id != wid and loc_id not in inv:
                    inv.append(loc_id)            # apego por convívio (como record_event)
            # spec 041: `depende_observador` — a valência sobre o AUTOR é DERIVADA
            # do afeto DESTA testemunha pelo REFERENTE (o expulso), não um sinal
            # fixo. É o que dá dente mecânico à reputação (o afeto muda de verdade).
            if fato.get("depende_observador"):
                va = _derive_observer_valence(
                    sentiment_toward(wid, fato["referente"]),
                    fato.get("polaridade", "hostil"))
                val = {character_id: va} if va else None
            else:
                val = {character_id: fato["val_ator"]} if fato["val_ator"] else None
            if fato.get("recorrente"):
                # o mesmo ato repetido não vira N lembranças na plateia
                mem_id, _ = _remember_recurring(
                    wfolder, texto, evento=fato.get("evento"),
                    about=fato["recorrente"], involved=inv, intensity=intens,
                    frag=fato.get("reincidencia", ""))
            else:
                mem_id = _write_memory(wfolder, texto, kind=ACONTECIMENTO,
                                       intensity=intens, involved=inv, valence=val,
                                       evento=fato.get("evento"), about=alvo_dono)
            created.append({"target": wid, "id": mem_id, "event": "witness"})
    return created


# --------------------------------------------------------------------------- #
# Acusar (spec 028) — a memória vira alavanca social. Determinístico: sem
# régua, sem rolagem (research.md, "por que os 4 ingredientes não se
# aplicam") — só compõe memória já existente (percepcao.remembered_about
# grounda o alvo no manifest) com o leque de testemunha que a spec 024 já
# tem (_witness_facts, entrada "witness_accuse" acima).
# --------------------------------------------------------------------------- #

def _intensify_commitments(actor_id: str, actor_folder: Path) -> list[str]:
    """Frente D (US4): para cada intenção ATIVA do PRÓPRIO ator que referencia
    um compromisso (`memoria_id`, gravado por `prometer`, spec 027), a
    memória original sobe um degrau de intensidade (`_renew_memory`, modo
    `intensidade` — teto `giant`). Só o PRÓPRIO ator
    (`[[server-never-owns-character-agency]]`) — nunca intensifica
    compromisso alheio. Intenção sem `memoria_id` (criada fora de
    `prometer`) é ignorada — não é um compromisso rastreável."""
    tocadas: list[str] = []
    int_dir = actor_folder / "intentions"
    if not int_dir.is_dir():
        return tocadas
    for path in sorted(int_dir.glob("*.md")):
        fm, _ = read_doc(path)
        if fm.get("status") != "ativa":
            continue
        memoria_id = fm.get("memoria_id")
        if not memoria_id:
            continue
        tocadas.extend(_renew_memory(actor_folder, memoria_id=memoria_id,
                                     modo="intensidade"))
    return tocadas


def _record_equip(character_id: str, equips_applied: list) -> list:
    created: list = []
    for op in equips_applied or []:
        item_id = op.get("item")
        item = name_of(item_id)
        if op.get("op") == "unequip":
            destino = op.get("to")
            if destino and destino != character_id:
                texto = f"Tirei {item} e deixei em {name_of(destino)}."
            else:
                texto = f"Tirei {item} do corpo."
        else:
            texto = f"Vesti {item}."
        _rec(created, character_id, texto, "equip", [character_id, item_id])
    return created


def _record_lock(character_id: str, locks_applied: list) -> list:
    created: list = []
    for op in locks_applied or []:
        if op.get("noop"):
            continue
        alvo = name_of(op.get("target") or op.get("alvo"))
        acao = "Fechei" if op.get("op") == "close" else "Abri"
        _rec(created, character_id, f"{acao} {alvo}.", "lock", [character_id])
    return created


def _record_travel(character_id: str, travels_applied: list) -> list:
    created: list = []
    for op in travels_applied or []:
        destino = name_of(op.get("destino_final"))
        _rec(created, character_id, f"Parti rumo a {destino}.", "travel", [character_id])
    return created


def _record_learn(character_id: str, learns_applied: list) -> list:
    created: list = []
    eu = _char_name(character_id)
    for op in learns_applied or []:
        nome_rota = op.get("nome") or op.get("rota")
        if op.get("renovou"):
            continue
        fonte = op.get("fonte")
        if not fonte:
            _rec(created, character_id, f"Decifrei o caminho: {nome_rota}.", "learn",
                 [character_id], intensity="medium")
            continue
        _rec(created, character_id, f"{_char_name(fonte)} me ensinou o caminho: {nome_rota}.",
             "inform", [character_id, fonte],
             valence={fonte: POSITIVA}, lugar_sinal=POSITIVA)  # ex-taught
        _rec(created, fonte, f"{eu} me perguntou o caminho, e eu indiquei.",
             "inform", [fonte, character_id])
    return created


def _record_hearsay_narrator(character_id: str, hearsay_applied: list) -> list:
    """O outro lado do reconto: o que QUEM CONTOU guarda de ter contado.

    Item 52: passa a guardar o Z — o que ele de fato disse —, não só que houve
    conversa. Era "Contei a X sobre Y."; agora "Contei a X: <Z>". Sem isso os dois
    lados guardavam coisas de valor muito diferente: um ficava com o relato, o outro
    com um recibo. `small` porque contar não é viver o episódio; a intensidade do
    conteúdo já mora na memória de quem OUVIU.
    """
    created: list = []
    eu = _char_name(character_id)
    for op in hearsay_applied or []:
        fonte = op.get("fonte")
        sobre = op.get("sobre")
        if not fonte:
            continue
        z = " ".join((op.get("z") or "").split())
        texto = (f"Contei a {eu}: {z}" if z
                 else f"Contei a {eu} sobre {name_of(sobre)}.")
        _rec(created, fonte, texto, "hearsay", [fonte, character_id])
    return created


def _texto_da_mudanca(alvo: str, campo: str, valor, character_id: str) -> str:
    """A mudança de estado EM LINGUAGEM DE MUNDO (item 52.6).

    Era `f"Mudou em mim: {campo} — {valor}."` — nome de campo e valor cru na cara do
    jogador, em 898 memórias (um terço do acervo). E o mais absurdo: o `value` de
    `action` JÁ É uma frase de mundo escrita pela Mente ("Hulda senta ao lado de
    Petrila"), então o prefixo era ruído embrulhando conteúdo bom.

    A regra é essa: quando o valor já se lê como frase, ele É a memória. Quando é dado
    (um humor, um marcador), o mundo o veste. Nada de `campo — valor`.
    """
    quem = "" if alvo == character_id else f"{name_of(alvo)}: "
    if campo == "action" and isinstance(valor, str) and valor.strip():
        # já é prosa de cena, e nomeia o sujeito quando é outro
        return valor.strip() if not quem else f"{name_of(alvo)} — {valor.strip()}"
    if campo == "mood" and valor:
        return (f"Fiquei {valor}." if not quem else f"{name_of(alvo)} ficou {valor}.")
    if campo == "descansando_desde":
        return "Deitei para dormir." if not quem else f"{name_of(alvo)} foi dormir."
    return f"{quem}{campo}: {valor}."


def _record_mutations(character_id: str, applied: list) -> list:
    created: list = []
    for mut in applied or []:
        if not isinstance(mut, dict):
            continue
        if "FR-014" in (mut.get("reason") or ""):
            continue
        alvo = mut.get("target")
        campo = (mut.get("path") or "").split(".")[-1]
        valor = mut.get("value")
        texto = _texto_da_mudanca(alvo, campo, valor, character_id)
        _rec(created, character_id, texto, "mutate",
             [alvo] if alvo != character_id else [character_id])
    return created


def _record_events(character_id: str, actor_folder: Path,
                   present_chars: dict, outcome: dict) -> list[dict]:
    """Encadeia os recordadores por-família na MESMA ordem de antes (spec 013/020).

    NOTA (spec 020): a derivação de cada família virou um recordador próprio
    (`_record_attack`, `_record_carry`, ...), que os executores de fase única
    chamam por-op. Este ponto-no-fim é o driver de registro do modelo de LOTE (o
    `apply_resolution` fino) — apenas os encadeia, então o lote é idêntico.
    """
    created: list[dict] = []
    created += _record_attack(character_id, outcome.get("attack_ops_applied"),
                              outcome.get("rejected"))
    created += _record_carry(character_id, outcome.get("carry_ops_applied"))
    created += _record_persuade(character_id, outcome.get("persuade_ops_applied"))
    created += _record_trade(character_id, outcome.get("trade_ops_applied"))
    created += _record_transfer(character_id, outcome.get("item_transfers_applied"),
                                present_chars)
    created += _record_persuade_give(character_id, actor_folder,
                                     outcome.get("persuade_give_ops_applied"),
                                     present_chars)
    created += _record_stolen(character_id, outcome.get("steal_ops_applied"))
    created += _record_equip(character_id, outcome.get("equip_ops_applied"))
    created += _record_lock(character_id, outcome.get("lock_ops_applied"))
    created += _record_travel(character_id, outcome.get("travel_ops_applied"))
    created += _record_learn(character_id, outcome.get("learn_ops_applied"))
    created += _record_hearsay_narrator(character_id, outcome.get("hearsay_ops_applied"))
    created += _record_mutations(character_id, outcome.get("applied"))
    return created


def has_trauma_from(quem_id: str, agressor_id: str | None) -> bool:
    """`quem_id` guarda um TRAUMA GRAVE vivo às mãos de `agressor_id`?

    O portão é GENÉRICO por assinatura, não por tipo de evento (spec 023): memória
    viva, `large`/`giant`, envolvendo o outro, com valência NEGATIVA dirigida a ele.
    Cabe a AGRESSÃO (spec 008/016) E o FURTO FLAGRADO (spec 023) — ser pego roubando
    é tão grave quanto bater. É o gatilho DETERMINÍSTICO do portão de confiança
    ("quem sofreu um trauma não coopera com quem o causou": não indica caminho, não
    conta, não cede, não se deixa mover), imposto pelo MOTOR sobre o estado ATUAL —
    que, no turno de fase única (spec 020), já inclui um golpe/furto desferido ANTES
    neste mesmo turno. Não depende do juízo do Árbitro.
    """
    if not agressor_id or quem_id == agressor_id:
        return False
    for m in _iter_memories(quem_id):
        if not _is_alive(m):
            continue
        if agressor_id not in memory_involved(m):
            continue
        if m.get("intensity") in ("large", "giant") \
                and memory_valence(m).get(agressor_id) == NEGATIVA:
            return True
    return False


def _recency_label(age: float) -> str:
    if age < 120:
        return "agora mesmo"
    if age < 3600:
        return "há pouco"
    if age < _DAY:
        return "hoje"
    if age < 7 * _DAY:
        return "há dias"
    if age < 30 * _DAY:
        return "há semanas"
    if age < 365 * _DAY:
        return "há meses"
    return "há anos"


def _memory_salience(intensity: str, age: float) -> str:
    """'vivida' (recente e/ou forte, sempre presente) ou 'latente' (adormecida)."""
    window = _VIVID_WINDOW.get(intensity, _VIVID_WINDOW["medium"])
    return "vivida" if age <= window else "latente"


def _short_summary(text: str, limit: int = 60) -> str:
    """Resumo curto de fallback quando a memória não traz 'summary' no frontmatter."""
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0] + "…"


def get_active_memories(entity_folder: Path,
                        evoked_by: set[str] | None = None) -> list[dict]:
    """Memórias que a Mente recebe para narrar — vivas, evocadas e com teto.

    Cada memória traz `salience` (vivida|latente) e `recency`, derivados do relógio
    real e da intensidade, para a Mente decidir QUANDO pesá-las (memória análoga à
    humana: o recente-e-forte volta sozinho; o antigo só volta se o contexto evoca).

    O corte (spec 013) segue uma ordem que é REQUISITO, não detalhe:
      1. fora as de `kind: rota` — maquinaria de viagem, não narrativa
      2. fora as expiradas (por estado ou por prazo — defensivo)
      3. EVOCAÇÃO: fica o que envolve alguém presente ou o lugar atual, mais o
         que está vívido por si
      4. TETO por saliência

    Inverter 3 e 4 descartaria o relevante para caber o recente — o oposto do
    que a memória humana faz. E vale repetir: este corte é de NARRAÇÃO. O que o
    mundo SABE continua inteiro em `knows_route`/`familiarity_with`.
    """
    mem_dir = entity_folder / "memories"
    if not mem_dir.exists():
        return []
    _expire_memories(entity_folder)  # preguiçoso, no escopo de quem está sendo lido
    evoked_by = evoked_by or set()
    now = time.time()
    memories = []
    for path in sorted(mem_dir.glob("*.md")):
        fm, body = read_doc(path)
        if memory_kind(fm) == ROTA:
            continue
        # spec 032: reusa _is_alive (não reimplementa) — antes disto, este
        # laço checava "expired"/timestamp_end na mão, e nunca soube que
        # "esquecida" existia: uma memória marcada esquecida por `curar`
        # continuava sendo entregue à Mente pra narração, o oposto do que
        # o custo deveria fazer. Achado ao vivo, contra o servidor real.
        if not _is_alive(fm, now):
            continue
        intensity = fm.get("intensity")
        ts_start = fm.get("timestamp_start") or now
        age = max(0.0, now - ts_start)
        salience = _memory_salience(intensity, age)
        involved = memory_involved(fm)
        # evocada pela cena, ou vívida por si — nunca só recente
        if evoked_by and salience != "vivida" \
                and not (set(involved) & evoked_by):
            continue
        memories.append({
            "id": fm.get("id"),
            "intensity": intensity,
            "involved": involved,
            "summary": (fm.get("summary") or "").strip() or _short_summary(body),
            "content": body,
            "timestamp_start": ts_start,
            "timestamp_end": fm.get("timestamp_end"),
            "recency": _recency_label(age),
            "salience": _memory_salience(intensity, age),
        })
    memories.sort(key=lambda m: (
        0 if m.get("salience") == "vivida" else 1,
        _INTENSITY_ORDER.get(m.get("intensity"), 99),
        -(m.get("timestamp_start") or 0),
    ))
    return memories[:_MEMORY_CONTEXT_CAP]


def _expire_memories(entity_folder: Path) -> None:
    """Marca como expiradas as memórias VENCIDAS de um personagem (FR-028).

    O arquivo permanece como histórico; só o `state` muda para 'expired'. Uma
    memória de quem ninguém consulta fica com `state: active` vencido no disco
    até alguém olhar — e isso nunca produz resposta errada, porque todas as
    leituras descartam por prazo além de por estado.
    """
    mem_dir = entity_folder / "memories"
    if not mem_dir.is_dir():
        return
    now = time.time()
    for path in mem_dir.glob("*.md"):
        fm, body = read_doc(path)
        if fm.get("type") != "memory":
            continue
        if fm.get("state") == "active" and now >= (fm.get("timestamp_end") or 0):
            fm["state"] = "expired"
            write_doc(path, fm, body)


def _iter_memories_in(folder: Path) -> list[dict]:
    """Frontmatter das memórias de uma PASTA qualquer, vivas e vencidas.

    Genérica por pasta desde a spec 052, porque personagem deixou de ser a única
    coisa que lembra: uma peça forjada guarda a própria procedência (quem a
    trabalhou, quando), no mesmo formato. `_expire_memories` já era genérica assim
    — esta só foi alinhada.

    Isso NÃO significa que a procedência de um item apareça na cena: ela se guarda
    e não se distribui (spec 052, FR-037). `get_context` não lê esta pasta; só uma
    capacidade futura de examinar um objeto vai lê-la. Se a procedência descesse de
    graça na percepção, não sobraria nada para investigar.
    """
    mem_dir = folder / "memories"
    if not mem_dir.is_dir():
        return []
    out = []
    for path in sorted(mem_dir.glob("*.md")):
        fm, _ = read_doc(path)
        if fm.get("type") == "memory":
            out.append(fm)
    return out


def _iter_memories(character_id: str) -> list[dict]:
    """Frontmatter de todas as memórias de um personagem, vivas e vencidas."""
    try:
        folder = find_character_folder(character_id)
    except Exception:
        return []
    return _iter_memories_in(folder)


def _is_alive(fm: dict, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    # spec 032: "esquecida" é tratada como não-viva aqui, IGUAL "expired" —
    # some do contexto/narração do mesmo jeito. A diferença entre as duas
    # (peso zero vs ¼; nunca revive vs revive) mora em _weigh_memories/
    # proficiencies_for/_renew_memory, nunca aqui.
    if fm.get("state") in ("expired", "esquecida"):
        return False
    return now < (fm.get("timestamp_end") or float("inf"))


def _weigh_memories(character_id: str, target_id: str, signed: bool) -> float:
    """Soma as memórias de `character_id` que envolvem `target_id`.

    `signed=False` → APEGO (módulo, o `familiarity_with` de sempre): conta tudo,
    inclusive o neutro. `signed=True` → AFETO: cada parcela leva o sinal que a
    memória gravou para aquele alvo; o neutro (sem sinal) não pende. Mesma tabela
    de peso, mesmo desconto de vencida (¼) nos dois — é o que faz "conhecer" e
    "estimar" serem a mesma varredura (spec 016).

    spec 032: "esquecida" NUNCA soma (peso zero) — diferente de "expired",
    que continua pesando ¼ como sempre. É a distinção que faz o custo de
    `curar` genuinamente mais definitivo que uma expiração natural.
    """
    total = 0.0
    for fm in _iter_memories(character_id):
        if memory_kind(fm) != ACONTECIMENTO:
            continue
        if target_id not in memory_involved(fm):
            continue
        if fm.get("state") == "esquecida":
            continue
        p = _MEMORY_WEIGHT.get(fm.get("intensity"), 2.0)
        if not _is_alive(fm):
            p *= 0.25
        if signed:
            sinal = memory_valence(fm).get(target_id)
            if sinal == POSITIVA:
                total += p
            elif sinal == NEGATIVA:
                total -= p
            # sem sinal: neutro, não move o afeto
        else:
            total += p
    return total


def familiarity_with(character_id: str, other_id: str) -> float:
    """APEGO: quanto algo/alguém importa, pelo VOLUME de lembranças que o envolvem.

    Não existe contador de intimidade: o próprio volume é a medida. Muitas
    pequenas fazem um conhecido; uma única enorme faz alguém inesquecível.
    Vencidas pesam menos, mas pesam. Conta memória NEUTRA — usar algo todo dia
    apega sem que nada emocionante aconteça (spec 016). Agnóstica ao tipo do
    alvo: pessoa, item ou lugar.
    """
    return _weigh_memories(character_id, other_id, signed=False)


def sentiment_toward(character_id: str, target_id: str) -> float:
    """AFETO: para que lado a relação pende — a mesma soma de `familiarity_with`,
    agora COM SINAL (spec 016).

    Apego é o módulo; afeto é o rumo. `> 0` pende a favor, `< 0` contra, `0`
    neutro ou sem história. A ferida fresca (viva) pende inteira; a cicatriz
    antiga (vencida) pende a ¼ — conta, mas menos.
    """
    return _weigh_memories(character_id, target_id, signed=True)


def sentiment_label(saldo: float) -> str:
    """O afeto em LINGUAGEM, para a régua — o número morre no server (spec 016).

    Faixas em unidades de peso: 1 = um `small`, 4 = um `large`. Calibráveis; o
    contrato é que o NÚMERO nunca sai daqui.
    """
    if saldo <= -6:
        return "guarda forte ressentimento"
    if saldo <= -2:
        return "guarda mágoa"
    if saldo < 0:
        return "guarda um leve incômodo"
    if saldo < 2:
        return "sem história que pese num sentido ou noutro"
    if saldo < 6:
        return "nutre alguma simpatia"
    return "nutre forte estima"


def _derive_observer_valence(saldo: float, polaridade: str = "hostil") -> str | None:
    """VALÊNCIA RELATIVA AO OBSERVADOR (spec 041): como uma testemunha passa a
    sentir o AUTOR de um ato, DERIVADO do afeto dela pelo REFERENTE (a quem o ato
    foi feito) + a polaridade do ato. Reusa as MESMAS bandas do `sentiment_label`
    (mágoa ≤ -2, simpatia ≥ 2), sem limiar novo:
    - ato HOSTIL (expulsar): odiava o referente → aprova o autor (positiva);
      prezava o referente → reprova (negativa); banda neutra → None.
    - ato BENEVOLENTE: o sinal se mantém (prezava → positiva; odiava → negativa).
    None = sem valência estampada (a testemunha guarda o fato, sem mudar o afeto)."""
    if -2 < saldo < 2:
        return None
    gostava = saldo >= 2
    aprova = (not gostava) if polaridade == "hostil" else gostava
    return POSITIVA if aprova else NEGATIVA


def familiarity_label(valor: float) -> str:
    """A MAGNITUDE da vivência em LINGUAGEM — o número morre no server (spec 018).

    Irmã do `sentiment_label`, mas para o peso (não o sinal). Faixas calibráveis; o
    contrato é que o número NUNCA sai daqui — nem para A Mente. Só o rótulo, e os
    episódios (que dão o porquê), tecem o reconhecimento.
    """
    if valor <= 0.5:
        return "desconhecido"
    if valor < 2:
        return "visto de passagem"
    if valor < 6:
        return "conhecido"
    if valor < 12:
        return "de longa data"
    return "presença constante na vida dele"


# Cortes da fração de fadiga (spec 030) — os MESMOS quatro degraus que
# fatigue_label usa pra narrar são consumidos pela Frente B (rolagens
# moduladas) como penalidade numérica. Um lugar só decide os limiares.
def fatigue_penalty(fadiga: int, fatigue_max: int) -> int:
    """A penalidade determinística que a fração de fadiga aplica a uma
    rolagem (0/1/2/4) — mesmos cortes de `fatigue_label`, nunca régua/
    LLM (spec 030, Frente B)."""
    fracao = fadiga / fatigue_max if fatigue_max else 0.0
    penalidade = 0
    for corte, pena in zip(_FADIGA_CORTES, _FADIGA_PENALIDADES):
        if fracao >= corte:
            penalidade = pena
    return penalidade


def fatigue_label(fadiga: int, fatigue_max: int) -> str:
    """A fração de fadiga em LINGUAGEM — o número morre no server
    (Princípio V), espelhando `sentiment_label`/`familiarity_label`.
    NUNCA vira barra no client (memória `narrative-over-ui`)."""
    fracao = fadiga / fatigue_max if fatigue_max else 0.0
    if fracao < _FADIGA_CORTES[0]:
        return "descansado"
    if fracao < _FADIGA_CORTES[1]:
        return "um pouco cansado"
    if fracao < _FADIGA_CORTES[2]:
        return "cansado"
    if fracao < _FADIGA_CORTES[3]:
        return "muito cansado"
    return "exausto"


# Proficiência por domínio (spec 029, item 9/16/18 do backlog; curva assintótica
# desde spec 048, R12): converte peso acumulado num FATOR contínuo 0 -> TETO,
# nunca um nível inteiro travado. Calibrável — não é balanceamento final
# (research.md §4 da 029; R12 da 048); fica pra quando specs de consumo (`cura`,
# `cozinha`, `forjar`) puderem testar contra jogo real.
def _proficiency_factor(peso: float) -> float:
    if peso <= 0:
        return 0.0
    return _PROFICIENCY_TETO * peso / (peso + _PROFICIENCY_K)


def proficiencies_for(character_id: str) -> dict[str, float]:
    """Fator de proficiência por domínio — consulta de CLIENT (Princípio IX).

    Não é persistido: recalculado sob demanda, mesmo espírito de
    `familiarity_with`/`sentiment_toward` (spec 016). Reusa a MESMA fórmula
    de peso (`_MEMORY_WEIGHT`, viva peso cheio / vencida a ¼), filtrando por
    `domain` em vez de por `involved`/alvo. Sempre devolve as chaves de
    domínio (FR-008) — nunca omite um domínio por falta de memória; `domain:
    nenhuma`/ausente nunca entra em soma nenhuma.

    spec 032: "esquecida" NUNCA soma (peso zero) — mesma distinção de
    `_weigh_memories`. `expired` continua pesando ¼, como sempre.

    Personagem inexistente propaga `MotorError` (mesmo padrão de
    `known_routes`) — ao contrário de `_iter_memories` (que engole a
    exceção porque seus outros chamadores, `familiarity_with`/
    `sentiment_toward`, consultam sobre um TERCEIRO que pode não ter pasta
    própria), aqui o `character_id` é sempre o PRÓPRIO sujeito da consulta:
    inexistente é erro, não zero silencioso.
    """
    find_character_folder(character_id)
    pesos = {d: 0.0 for d in DOMAINS if d != "nenhuma"}
    for fm in _iter_memories(character_id):
        if memory_kind(fm) != ACONTECIMENTO:
            continue
        dominio = fm.get("domain")
        if dominio not in pesos:
            continue
        if fm.get("state") == "esquecida":
            continue
        p = _MEMORY_WEIGHT.get(fm.get("intensity"), 2.0)
        if not _is_alive(fm):
            p *= 0.25
        pesos[dominio] += p
    return {d: _proficiency_factor(p) for d, p in pesos.items()}
