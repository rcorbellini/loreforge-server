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
    na mesma resposta — spec 048 — 3 de 3 na sondagem real)."""
    campos_texto = texto_campos or {}
    resultado = dict(campos)
    resultado.update(campos_texto)
    bruto = (raw or "").strip()
    inicio, fim = bruto.find("{"), bruto.rfind("}")
    if inicio == -1 or fim <= inicio:
        return resultado
    try:
        obj = _json.loads(bruto[inicio:fim + 1])
    except ValueError:
        return resultado
    if not isinstance(obj, dict):
        return resultado
    for chave, default in campos.items():
        v = obj.get(chave)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            resultado[chave] = max(0, min(10, int(v)))
    for chave in campos_texto:
        v = obj.get(chave)
        if isinstance(v, str) and v.strip():
            resultado[chave] = v.strip()
    return resultado
