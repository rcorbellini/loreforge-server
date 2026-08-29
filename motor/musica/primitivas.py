"""O Motor / musica — PRIMITIVAS (item 31 §3: DDD por domínio; spec 058).

Funções puras: a rolagem de desfecho, os degraus de decaimento por banda, o
bônus de instrumento e o registro de tom por intensidade. Sem turno/LLM. Ver
executores.py para a escrita (que precisa de I/O — ler a plateia, gravar
memória).
"""
from __future__ import annotations

from .. import rolagem

# spec 058 (research M2): DC FIXA, NÃO `persuade_dc`. Cantar não tem régua de
# admissão — não há nota de CENA a alimentar aquela curva (medido: pedida essa
# nota, a LLM inverte a ordem dos feitos — banal=5, médio=10, grande=10). O
# talento decide a QUALIDADE da noite contra uma dificuldade fixa, como
# qualquer prova de perícia. Calibrável — não é balanceamento final (a spec
# marca 12 como proposta), fica pra quando o mundo real testar.
DC_SING = 12


def bonus_instrumento(nota: int) -> float:
    """O quanto o instrumento NA MÃO soma na rolagem — 0.0 sem instrumento
    (`nota` já vem 0 do juízo quando não há), NUNCA negativo (spec 058, US4:
    decisão deliberada — um instrumento ruim pontua baixo, não penaliza; o
    vocabulário do juízo é 0-10 sem sinal, e inventar uma escala com sinal só
    para esta tool duplicaria vocabulário de julgamento). Faixa 0.0-5.0."""
    return max(0, min(10, int(nota))) / 2.0


def roll_sing_check(actor_fm: dict, nota_instrumento: int = 0,
                    nivel_musica: float = 0.0,
                    rolls: list | None = None) -> tuple[str, dict]:
    """Devolve (desfecho, roll_info). desfecho ∈ {'otimo','comum','ruim','fracasso'}.

    SEM extremo determinista e SEM gate: cantar sempre rola — é a diferença
    central desta tool em relação às sete irmãs de ofício (spec 058: "cantar
    não é cozinhar", decisão do mantenedor — ele abre a boca e canta, o que
    varia é o desfecho, nunca SE algo acontece).

    `d20 + mod(CHA) + nivel_musica + bonus_instrumento` vs `DC_SING` (fixa) →
    quatro faixas por distância à DC, mesmo molde de três-faixas que `steal`
    já usa, estendido a quatro porque aqui não há extremo determinista
    absorvendo a ponta.

    `nivel_musica` vem de `memoria.proficiencies_for(ator)["musica"]` — NUNCA
    de `character.skills` (revogado nesta mesma spec, US6).

    Nota/DC nunca saem do `roll_info` (segredo do mundo, Princípio IX)."""
    bonus = bonus_instrumento(nota_instrumento)
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("CHA", 10))
    total = d20 + mod + float(nivel_musica) + bonus
    dc = DC_SING
    if total >= dc + 5:
        desfecho = "otimo"
    elif total >= dc:
        desfecho = "comum"
    elif total >= dc - 5:
        desfecho = "ruim"
    else:
        desfecho = "fracasso"
    # tendência: sem nota de cena para comparar (não há régua de admissão),
    # a expectativa é o resultado MÉDIO do dado (d20=10) contra a MESMA DC —
    # é o que dá sentido a "virada" aqui: a noite saiu melhor ou pior do que
    # o talento/instrumento do próprio cantor já prometiam.
    esperado_bom = (10 + mod + float(nivel_musica) + bonus) >= dc
    saiu_bom = desfecho in ("otimo", "comum")
    info = {
        "tipo": "musica", "resultado": desfecho,
        "virada": esperado_bom != saiu_bom,
        "critico": (d20 == 20) or (d20 == 1) or None,
        "rolagem": {"d20": d20, "mod": mod,
                    "nivel_musica": round(float(nivel_musica), 2),
                    "bonus_instrumento": bonus, "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return desfecho, info


# spec 058: quantos degraus de INTENSIDADE o reconto perde em relação à fonte,
# por desfecho — o efeito que o mantenedor pediu ("melhor proficiência = a
# canção resiste mais ao decaimento de grau"). `fracasso` não gera reconto
# nenhum (None é o sinal para o executor pular o laço de `_record_hearsay`).
_DEGRAUS_POR_DESFECHO = {"otimo": 0, "comum": 1, "ruim": 2, "fracasso": None}


def degraus_por_desfecho(desfecho: str) -> int | None:
    return _DEGRAUS_POR_DESFECHO.get(desfecho, 1)


# spec 058 (data-model, "O registro"): a intensidade da FONTE entra no prompt
# como TOM, nunca como número a julgar — medido (research M6): com o registro,
# a letra de um feito miúdo caiu de 50 para 29 palavras e a cópia literal de
# 24,4% para 7,3%. `medium` não tem frase (o caso comum não precisa de
# instrução extra).
_REGISTRO_POR_INTENSIDADE = {
    "giant": ("Esta lembrança MARCOU FUNDO quem a viveu — é matéria de canção "
             "grande. Cante à altura dela."),
    "large": ("Esta lembrança MARCOU FUNDO quem a viveu — é matéria de canção "
             "grande. Cante à altura dela."),
    "small": ("Esta lembrança é MIÚDA — um dia comum, que quase ninguém "
             "guardaria. Não force grandeza que ela não tem; cante o que ela é."),
}


def registro_de_intensidade(intensity: str | None) -> str:
    return _REGISTRO_POR_INTENSIDADE.get(intensity or "", "")
