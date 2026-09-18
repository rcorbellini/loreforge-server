"""Devolve o ÍNDICE às memórias que citam gente e não a indexam (item 91).

POR QUE EXISTE. `remembered_about` e `arquivos_envolvendo` casam por `involved` — é
por ali que o Árbitro descobre que o homem a quem se pergunta o caminho é o mesmo que
levou uma surra de quem pergunta (spec 015). Uma memória que NOMEIA alguém no texto e
tem `involved` vazio é invisível a essa consulta:

    "Sarga ameaçou Hulda com o machado na praça, diante de…"    involved: None

    remembered_about(mira, sarga) -> 3 memórias
       essa está entre elas?  NÃO

O Árbitro julga a relação mira<->sarga sem ver que ela presenciou aquilo. São **568
memórias** no acervo, 557 delas da primeira quinzena de agosto — o defeito é
HISTÓRICO (de setembro em diante são 2 em 562), e por isso isto é migração e não
conserto de produtor.

O QUE FAZ. Procura, no `summary` e no corpo, o nome dos personagens que o mundo
conhece, e acrescenta os ids encontrados ao `involved`. Nada mais: não reescreve texto,
não mexe em prazo, não cria nem apaga.

O QUE NÃO FAZ, e cada recusa tem motivo:

  · NÃO indexa o DONO da memória. A convenção do acervo não é uniforme (as
    `unanswered` incluem o dono, as `mutate` não), e quem consulta procura pelo OUTRO
    — `remembered_about(quem, sobre)` busca `sobre`. Acrescentar o dono não ajudaria
    ninguém e mexeria em contagens que esta migração não tem como verificar.

  · NÃO indexa LUGAR nem ITEM. "Praça do Mercado" aparece no texto de quase tudo, e o
    pool daquele lugar já é 555 de 809 — indexá-lo mais tornaria a consulta por lugar
    ainda mais inútil do que já é. Personagem é o que `remembered_about` serve.

  · NÃO resolve NOME AMBÍGUO pelo primeiro nome. "Torvin" é duas pessoas
    (`torvin-ferreiro` e `torvin-britador`): só casa se o nome COMPLETO estiver no
    texto. Indexar o Torvin errado faria o Árbitro julgar uma relação que não
    aconteceu — inventar vínculo é pior que não ter índice, e é o modo de falha que
    esta sessão inteira vem evitando.

  · NÃO toca memória `esquecida`. Ela é o que o custo da cura (spec 032) tornou
    definitivo; devolver-lhe índice seria devolvê-la ao alcance por uma porta lateral.

  · NÃO COMPLETA índice que já existe — e esta foi a recusa mais cara de descobrir. A
    primeira versão mexia em 1.249 memórias: 545 vazias e **704 que já tinham
    `involved`**. Olhando uma delas:

        involved: [draven-vigia]   + bramm-estivador-mor
        "Draven, o Vigia me acusou: Vi Verro, o Calado acusar Bramm"

    O Draven acusou o Verro DE TER ACUSADO o Bramm. O índice `[draven]` está certo:
    Bramm é o CONTEÚDO da acusação, não participante do ato. Acrescentá-lo faria
    `remembered_about(verro, bramm)` devolver uma memória em que o Bramm não fez nada.

    Quem escreveu aquele índice teve a informação estruturada em mãos (o executor sabe
    quem agiu sobre quem); esta migração só tem o TEXTO, que não distingue participante
    de citação. Onde o índice existe, ele é mais confiável do que eu — e criar vínculo
    do nada é pior que não ter índice.

`--dry-run` é o padrão. Uso:  python3 loreforge-server/migra_involved.py [--aplicar]
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import motor                                                    # noqa: E402


def _catalogo() -> tuple[dict, set]:
    """{nome procurável -> id} dos personagens, e o conjunto de nomes AMBÍGUOS.

    Procurável é o nome COMPLETO ("Elga, a Taverneira") e o primeiro nome ("Elga").
    O primeiro nome que pertence a mais de uma pessoa entra no conjunto de ambíguos e
    é descartado da busca — sobra só o completo daquela pessoa.
    """
    completos, primeiros = {}, collections.defaultdict(set)
    for p in motor.WORLD_DIR.rglob("character.md"):
        fm, _ = motor.read_doc(p)
        cid, nome = fm.get("id"), (fm.get("name") or "").strip()
        if not cid or not nome:
            continue
        completos[nome] = cid
        primeiros[nome.split(",")[0].strip()].add(cid)
    ambiguos = {n for n, ids in primeiros.items() if len(ids) > 1}
    catalogo = dict(completos)
    for n, ids in primeiros.items():
        if n not in ambiguos and len(n) >= 3:
            catalogo[n] = next(iter(ids))
    return catalogo, ambiguos


def _citados(texto: str, catalogo: dict) -> list[str]:
    """Os ids citados no texto, por NOME, com fronteira de palavra.

    Fronteira importa: sem ela "Ossa" casaria dentro de "Ossada", e um índice errado é
    pior que índice nenhum.
    """
    achados = []
    for nome, cid in catalogo.items():
        if cid in achados:
            continue
        if re.search(r"(?<!\w)" + re.escape(nome) + r"(?!\w)", texto):
            achados.append(cid)
    return achados


def main(aplicar: bool) -> int:
    catalogo, ambiguos = _catalogo()
    print(f"{len(catalogo)} nomes procuráveis; ambíguos descartados: "
          + (", ".join(sorted(ambiguos)) or "nenhum"))

    tocadas = vazias = parciais = ja_indexadas = 0
    por_dono: collections.Counter = collections.Counter()
    exemplos = []
    for path in motor.WORLD_DIR.rglob("memories/*.md"):
        fm, corpo = motor.read_doc(path)
        if fm.get("type") != "memory" or motor.memory_kind(fm) == motor.ROTA:
            continue
        if fm.get("state") == "esquecida":
            continue
        dono = next((a.name for a in path.parents
                     if (a / "character.md").exists()), None)
        atual = [i for i in (fm.get("involved") or []) if i]
        if atual:
            ja_indexadas += 1
            continue          # ver "NÃO COMPLETA índice que já existe", acima
        texto = f"{fm.get('summary') or ''} {corpo or ''}"
        novos = [c for c in _citados(texto, catalogo)
                 if c != dono and c not in atual]
        if not novos:
            continue
        tocadas += 1
        if atual:
            parciais += 1
        else:
            vazias += 1
        por_dono[dono] += 1
        if len(exemplos) < 6:
            exemplos.append((dono, atual, novos, texto.strip()[:56]))
        if aplicar:
            fm["involved"] = atual + novos
            motor.write_doc(path, fm, corpo)

    print(f"\n{tocadas} memórias ganhariam índice — todas com `involved` VAZIO")
    print(f"{ja_indexadas} tinham índice e citavam mais gente: NÃO tocadas "
          f"(ver a docstring)")
    print("\npor personagem (top 8):")
    for dono, n in por_dono.most_common(8):
        print(f"   {dono:32} {n:4}")
    print("\namostra:")
    for dono, atual, novos, txt in exemplos:
        print(f"   {dono:22} {atual} + {novos}\n      {txt}")
    print(f"\n{'APLICADO.' if aplicar else 'dry-run — rode com --aplicar para valer.'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv))
