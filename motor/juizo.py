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

import re

# A frase canônica. Toda capacidade julgada compõe a SUA régua com esta — se cada uma
# inventasse a própria ("responda com número", "de 0 até 10", "apenas o número"), as
# taxas de parse divergiriam entre capacidades sem ninguém perceber.
NOTA_0_10 = "\n\nResponda APENAS com um número inteiro de 0 a 10, nada mais."

_PRIMEIRO_NUMERO = re.compile(r"-?\d+")

# spec 046 (`eat`, régua de CONSUMO): a ÚNICA régua do projeto que pede DUAS coisas
# na mesma resposta — a nota E o texto da nova descrição do item. Frase canônica
# própria (não reusa NOTA_0_10 sozinha) para o parse de duas linhas ser previsível.
NOTA_0_10_E_TEXTO = ("\n\nResponda em DUAS linhas: a primeira só com um número inteiro "
                     "de 0 a 10, nada mais; a segunda com o texto pedido, nada mais.")


def nota(raw: str, default: int) -> int:
    """A nota que o mundo leu, grampeada em 0-10.

    `default` é da CAPACIDADE, não desta primitiva: o neutro do golpe (combate limpo)
    não é o neutro da troca (o padrão é NÃO negociar). Quem sabe disso é a régua, e a
    régua mora com a tool.

    Resposta ilegível cai no default em vez de estourar: o turno já mexeu no mundo
    quando chega aqui, e derrubá-lo por um modelo que respondeu torto seria trocar o
    certo pelo cosmético. É o mesmo tratamento que `attack` já dava a uma nota
    inválida vinda do Árbitro.
    """
    achado = _PRIMEIRO_NUMERO.search(raw or "")
    if achado is None:
        return default
    try:
        return max(0, min(10, int(achado.group())))
    except ValueError:            # inteiro absurdamente grande
        return default


def nota_e_texto(raw: str, default_nota: int, default_texto: str = "") -> tuple[int, str]:
    """Como `nota`, mas para a régua que também pede um TEXTO (spec 046, `eat`): a
    1ª linha vira a nota (via `nota()`, mesmo grampeamento/default); o RESTO da
    resposta vira o texto, tal como veio — sem resumir. Resposta sem 2ª linha cai
    no `default_texto` (mesma disciplina de robustez do `nota()`)."""
    linhas = (raw or "").splitlines()
    primeira = linhas[0] if linhas else ""
    resto = "\n".join(linhas[1:]).strip()
    return nota(primeira, default_nota), (resto or default_texto)
