"""O Motor / rolagem (spec 021 — extraído de __init__).

Parte do pacote em níveis. Ver research.md (T001) para o grafo de dependências.
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

from . import io
from .io import (
    _sinal,
)


def _roll_d20() -> int:
    """Rolagem injetável para testes (spec 006, FR-006): monkeypatch aqui."""
    return random.randint(1, 20)


def attr_modifier(value) -> int:
    """Modificador D&D: floor((valor - 10) / 2) — convenção da constituição."""
    try:
        return (int(value) - 10) // 2
    except (TypeError, ValueError):
        return 0


def push_dc(peso_item: float, capacidade: float) -> int:
    """Dificuldade do teste de força: DC 10 no limite natural, +1 por ~10% acima."""
    ratio = peso_item / capacidade if capacidade else float("inf")
    return 10 + round(10 * (ratio - 1))


IMPROVISED_DAMAGE = 1


IMPROVISED_ATTRIBUTE = "STR"


NEUTRAL_ADVANTAGE = 5


_APEGO_DC_TETO = 4


_AFETO_DC_TETO = 4


def _attachment_dc_share(apego: float) -> int:
    """Quanto o apego sobe a DC — curva RAIZ, não linear (spec 016, calibragem).

    Linear saturava rápido demais: com `round(apego)`, o teto 4 vinha com apego 4
    = 4 memórias `small` = dois usos. Pegar algo duas vezes travava a troca. A
    raiz estica isso: o teto agora exige apego 16, e o uso casual mal registra
    (apego 2 → 1, apego 4 → 2, apego 9 → 3, apego 16 → 4). Ainda monótona (raiz é
    não-decrescente) e ainda 0 em 0 (piso da spec 011 intacto).
    """
    return min(_APEGO_DC_TETO, round((max(0.0, apego)) ** 0.5))


def trade_dc(necessidade: int, razao_valor: float, apego: float = 0.0,
             afeto_parceiro: float = 0.0) -> int:
    """Dificuldade da troca: decresce na NECESSIDADE e na RAZÃO DE VALOR (spec 011),
    CRESCE no APEGO ao que se entrega, e desloca com o AFETO do parceiro por quem
    propõe (spec 016).

    Base `20 − 2×necessidade` é a curva do `persuade_dc`. A razão desloca ±4:
    oferecer o dobro vale ~2 pontos de necessidade (não-crescente na razão).

    APEGO (spec 016): o parceiro custa mais a se desfazer do que lhe importa —
    `_attachment_dc_share`, com teto, curva raiz. Dificulta, não proíbe: preço alto
    ainda move item amado. `apego=0` reproduz a DC da spec 011 EXATA (piso).

    AFETO (spec 016): o parceiro cobra mais caro de quem detesta e mais barato de
    quem estima — o "não vendo PRA VOCÊ" que faltava. Afeto negativo SOBE a DC,
    positivo DESCE, com teto simétrico e curva raiz. `afeto=0` não muda nada. Não
    é portão: hostilidade extrema torna a troca improvável, nunca categoricamente
    impossível (o portão duro continua sendo necessidade 0).
    """
    base = 20 - 2 * int(necessidade)
    ajuste = max(-4, min(4, round(4 * (razao_valor - 1))))
    parcela_apego = _attachment_dc_share(apego)
    # afeto NEGATIVO (detesta) sobe a DC; POSITIVO (estima) desce. Curva raiz,
    # teto simétrico. O sinal invertido: mais afeto = menos dificuldade.
    mag = min(_AFETO_DC_TETO, round(abs(afeto_parceiro) ** 0.5))
    parcela_afeto = -_sinal(afeto_parceiro) * mag
    return base - ajuste + parcela_apego + parcela_afeto


def resist_dc(alvo_fm: dict) -> int:
    """Dificuldade de levar quem se firma: a força do ALVO é o que resiste.

    Mesma forma da defesa do ataque (spec 008) — base 10 + modificador.
    """
    return 10 + attr_modifier((alvo_fm.get("attributes") or {}).get("STR", 10))


def defense_of(char_fm: dict) -> int:
    """Defesa do alvo: agilidade do corpo. A armadura age no dano, não aqui —
    contá-la duas vezes tornaria aço pesado quase invulnerável."""
    return 10 + attr_modifier((char_fm.get("attributes") or {}).get("DEX", 10))


def attack_tendencia(vantagem: int) -> str:
    """Tendência que a CENA dá ao golpe: base da virada (espelho da vontade)."""
    v = int(vantagem)
    if v >= 6:
        return "acertar"
    if v <= 4:
        return "errar"
    return "neutra"


def persuade_dc(vontade: int) -> int:
    """Dificuldade do teste de persuasão (spec 007): monotônica na vontade do alvo.
    Vontade 5 (indiferente) = DC 10; 9 (quase decidido) = DC 2; 1 (contrário) = 18."""
    return 20 - 2 * int(vontade)


def toxin_dc(toxicidade: int) -> int:
    """Dificuldade do teste de resistência a um item arriscado (spec 046, `eat`):
    monotônica na TOXICIDADE do item — inclinação INVERSA de `persuade_dc`, porque o
    significado da nota é o oposto (aqui, nota ALTA = mais perigoso = mais difícil
    resistir, não mais fácil). Toxicidade 5 (moderado) = DC 10; 9 (quase certo) = DC
    18; 1 (risco mínimo) = DC 2. Não reusa `persuade_dc` — a mesma fórmula aplicada
    aqui inverteria o risco (item mais tóxico ficaria mais fácil de resistir)."""
    return 2 * int(toxicidade)


def persuade_tendencia(vontade: int) -> str:
    """Tendência natural do alvo: base da VIRADA social (clarificação Q1 da spec)."""
    v = int(vontade)
    if 6 <= v <= 9:
        return "ir"
    if 1 <= v <= 4:
        return "ficar"
    return "neutra"


LEARN_ROUTE_DC = 12


def learn_dc_from(informante_fm: dict) -> int:
    """A DC de aprender com uma PESSOA: quem explica bem ensina bem (spec 015).

    A spec 014 exigiu DC fixa porque a variação devia vir de quem lê, não do que
    se lê — e um pergaminho não tem cabeça. Uma pessoa tem. O deslocamento sai de
    ATRIBUTO do mundo; pedir ao Árbitro uma nota de didática seria pedir que o
    modelo avaliasse a própria clareza, e ele se acharia claro.

    O clamp não é enfeite. Sem teto, um informante de INT 3 (DC 16) vira parede
    que só sorte vence; sem piso, um erudito de INT 20 (DC 7) faz o ouvinte
    embotado nunca falhar. Os dois extremos apagariam a influência do INT de
    QUEM OUVE, que é o SC-006.

    Material lido continua em `LEARN_ROUTE_DC` puro — esta função só é chamada
    quando a op tem `fonte`, e é o que impede a spec 014 de regredir.
    """
    mod = attr_modifier((informante_fm.get("attributes") or {}).get("INT", 10))
    return max(8, min(16, LEARN_ROUTE_DC - mod))
