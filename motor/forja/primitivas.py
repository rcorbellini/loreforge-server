"""O Motor / forja — PRIMITIVAS (item 31 §3: DDD por domínio; spec 052).

Funções puras: as cinco bandas, os dois tetos, a rolagem, a catraca, a conversão
de nota em tempo real e a tradução de banda em números mecânicos. Sem turno, sem
LLM, sem arquivo. Ver executores.py.

O DESENHO EM UMA FRASE: o material diz o quanto a peça PODE chegar, a maestria diz
o quanto o ferreiro SUSTENTA, o dado diz o que saiu — e o extremo natural do dado
fica guardado ao lado da banda para ser pago só no fim.
"""
from __future__ import annotations

from .. import rolagem

# As cinco bandas, em ordem. `falha` é a única sem bloco mecânico nenhum: a peça
# nasce, mas vale como improvisada pelas regras que já existem (`fisica.weapon_of`)
# — a punição não inventa número novo (spec 052, FR-025).
BANDAS = ("falha", "comum", "incomum", "raro", "lendario")
_IDX = {b: i for i, b in enumerate(BANDAS)}


def indice(banda: str) -> int:
    return _IDX.get(banda, 0)


def desloca(banda: str, degraus: int, teto: str = "lendario") -> str:
    """Move a banda N degraus, com piso em `falha` e teto no que for passado."""
    alvo = max(0, min(indice(banda) + degraus, indice(teto)))
    return BANDAS[alvo]


def menor(a: str, b: str) -> str:
    return a if indice(a) <= indice(b) else b


def duracao_segundos_forja(nota: int) -> int:
    """Nota 0-10 de DURAÇÃO -> tempo real de trabalho: 5 a 60 minutos.

    Mesma FORMA linear de `cozinha.duracao_segundos` (`60 + 60×nota`), com
    constantes próprias e função própria — o mesmo padrão que `toxin_dc` adotou em
    relação a `persuade_dc`: a forma se reusa, o significado é outro e por isso a
    função é separada. Forjar demora cinco vezes o que cozinhar demora."""
    return 300 + 300 * max(0, min(10, int(nota)))


def teto_por_material(nota: int) -> str:
    """Nota 0-10 de QUALIDADE DO MATERIAL -> o teto que aquele metal permite.

    É a primeira das TRÊS condições independentes da banda máxima (FR-028): não
    existe peça lendária de sucata, por melhor que seja o ferreiro e por mais sorte
    que ele tenha. É isto que faz do material raro a moeda do jogo — sem este teto,
    a banda alta sairia de dado puro e minério bom não valeria nada."""
    nota = max(0, min(10, int(nota)))
    if nota <= 3:
        return "comum"
    if nota <= 6:
        return "incomum"
    if nota <= 8:
        return "raro"
    return "lendario"


def teto_por_maestria(fator: float) -> str:
    """Fator contínuo de proficiência -> o teto que aquelas mãos sustentam.

    O TERCEIRO papel que a proficiência cumpre no projeto, e é deliberado que sejam
    três diferentes: em `heal` ela ajusta a magnitude DEPOIS da banda decidida; em
    `cook`/`butcher` ela soma direto no total da rolagem, decidindo a própria banda;
    aqui ela é TETO — não empurra o resultado para cima, só impede que ele passe do
    que o ofício daquela pessoa sustenta.

    CALIBRAÇÃO (spec 052, FR-035): `proficiencies_for` é assintótica
    (`10·peso/(peso+16)`), e 10 nunca é alcançado — peso 16 dá 5,0, peso 64 dá 8,0,
    peso 144 dá 9,0. Por isso os cortes ficam BEM abaixo do teto teórico: o mais
    alto pede fator 6,0, que a curva alcança em peso 24 (~duas dúzias de peças
    concluídas). Um corte em 8 ou 9 tornaria a banda máxima inalcançável na prática,
    não rara."""
    if fator < 2.0:
        return "comum"
    if fator < 4.0:
        return "incomum"
    if fator < 6.0:
        return "raro"
    return "lendario"


def favorabilidade(qualidade_material: int, fogo_de_forja: int, ferramental: int) -> int:
    """As três notas de admissão viram UMA favorabilidade, no Motor.

    Elas fazem dupla função de propósito: cada uma é gate (0 recusa) E contribui
    para o quanto a cena favorece um bom resultado. Sem isso, uma oficina de mestre
    valeria exatamente o mesmo que uma capenga — a nota seria calculada e jogada
    fora, que é o desperdício que esta spec foi escrita para não cometer."""
    soma = int(qualidade_material) + int(fogo_de_forja) + int(ferramental)
    return max(0, min(10, soma // 3))


def roll_forge_check(actor_fm: dict, nota: int, atributo: str,
                     rolls: list | None = None) -> tuple[str, str | None, dict]:
    """Devolve (banda_rolada, extremo, roll_info). Rola UMA vez, na abertura.

    `d20 + mod(atributo)` vs `persuade_dc(favorabilidade)` — MESMA curva de
    `cook`/`cura`/`butcher`, reusada sem mudança. A proficiência NÃO entra aqui
    (divergência deliberada: ela é teto, não bônus — somar E limitar contaria a
    mesma coisa duas vezes).

    A banda por MARGEM chega no máximo a `raro`. `lendario` não é alcançável por
    margem nenhuma: só pelo degrau do extremo, pago na conclusão. É a forma
    mecânica exata de "nem o melhor ferreiro com o melhor material acerta sempre".

    O EXTREMO sai daqui congelado e SEPARADO da banda — a catraca só toca a banda,
    então a obra excepcional sobrevive a qualquer interrupção sem precisar de
    exceção nenhuma no rebaixamento. A sorte não mora na banda; mora ao lado dela.
    """
    nota = max(0, min(10, int(nota)))
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get(atributo, 10))
    dc = rolagem.persuade_dc(nota)
    margem = d20 + mod - dc
    if margem < 0:
        banda = "falha"
    elif margem <= 4:
        banda = "comum"
    elif margem <= 9:
        banda = "incomum"
    else:
        banda = "raro"
    extremo = "sucesso" if d20 == 20 else "falha" if d20 == 1 else None
    info = {
        "tipo": "forja", "resultado": banda,
        # virada: a cena prometia (nota alta) e saiu sofrível, ou não prometia nada
        # (nota baixa) e saiu notável.
        "virada": (nota >= 6 and banda in ("falha", "comum"))
                  or (nota <= 4 and banda in ("incomum", "raro")),
        "critico": extremo,
        "rolagem": {"d20": d20, "mod": mod, "atributo": atributo,
                    "total": d20 + mod, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return banda, extremo, info


def banda_final(banda: str, extremo: str | None, teto_material: str) -> str:
    """A banda que a peça leva para o mundo, calculada só na CONCLUSÃO.

    O degrau do extremo é pago aqui, DEPOIS de a catraca já ter feito o que tinha
    de fazer — e limitado sempre pelo teto do material. É o que torna a obra
    excepcional imune à interrupção: quem abriu a peça com sorte pode largá-la, ir
    embora, voltar dias depois, e o degrau continua lá."""
    if extremo == "sucesso":
        return desloca(banda, +1, teto=teto_material)
    if extremo == "falha":
        return desloca(banda, -1, teto=teto_material)
    return menor(banda, teto_material)


# Calibrado contra o que o mundo editorial já tem: armas de 2 a 8 de dano,
# armaduras de 3 a 4 de proteção. `lendario` fica ACIMA do melhor equipamento
# escrito à mão — que é o ponto — e `comum` fica no meio da faixa, não no fundo.
_DANO_POR_BANDA = {"comum": 3, "incomum": 5, "raro": 7, "lendario": 10}
_PROTECAO_POR_BANDA = {"comum": 2, "incomum": 3, "raro": 4, "lendario": 6}

# Acima disto a peça é pesada demais para o fio: o golpe sai da força, não da
# agilidade. Física determinística — nunca julgada pelo Árbitro.
_PESO_LIMITE_DEX_KG = 2.0


def bloco_mecanico(tipo: str, banda: str, peso_kg: float, slot: str | None) -> dict:
    """Banda -> os campos que tornam a peça utilizável. Banda `falha` devolve `{}`.

    A peça de banda `falha` nasce SEM bloco nenhum de propósito: um pedaço de metal
    torto que serve de porrete. `fisica.weapon_of` já trata item sem `weapon` como
    improvisado, então a punição do fracasso reusa um mecanismo que existe desde a
    spec 008, em vez de inventar um número novo para castigar."""
    if banda == "falha":
        return {}
    if tipo == "arma":
        atributo = "STR" if float(peso_kg or 0) > _PESO_LIMITE_DEX_KG else "DEX"
        return {"weapon": {"damage": _DANO_POR_BANDA[banda], "attribute": atributo}}
    return {"armor": {"protection": _PROTECAO_POR_BANDA[banda]},
            "wearable": {"slot": slot or "torso"}}
