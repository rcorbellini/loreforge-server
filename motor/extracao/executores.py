"""O Motor / extracao — EXECUTORES (item 31 §3: DDD por domínio; specs 054/071).

UM executor para as TRÊS capacidades (`mine`, `chop`, `forage`). Valida contra os
arquivos, rola, aplica — e a única coisa que a capacidade decide aqui é o domínio
de maestria, o atributo da rolagem e o prefixo do id. Todo o resto é comum.

O CAMINHO, quando passa:
  gates (alvo, ferramenta, rendimento) -> rolagem de RENDIMENTO com a maestria da
  PRÓPRIA capacidade somada direto -> banda -> par nome/description da banda ->
  N porções (`porcoes_de_erva`) com peso derivado do PORTE julgado -> N itens
  (`io.create_entity`, em loop) -> SE o alvo é `object`, reescreve o corpo dele e
  instala (ou NÃO) o prazo de renovação.

**O que a spec 071 acrescentou, e por que cada um importa:**

- **A nota de FERRAMENTA**, para `mine`/`chop`. Gate `min(alvo, ferramenta)`: os
  dois eixos são independentes, e qualquer um em 0 recusa. Medido: com uma nota
  composta só, as cláusulas competem pelo mesmo número e a saliente vence — uma
  picareta boa fazia uma moita de amora pontuar 8 para minério.
- **A nota de RENOVAÇÃO**, que decide se o alvo volta. `renovacao_s()` devolve
  `None` para 0, e aí **nenhum bloco de prazo é instalado**: é a AUSÊNCIA de
  promessa de volta que significa esgotado para sempre. Não existe campo
  "esgotado" (Princípio XI).
- **O PORTE julgado** no lugar dos 0,2 kg fixos da 054. É o que faz um tronco
  passar da capacidade de carga, cair no chão e precisar de `shove` — fechando o
  percurso árvore -> abrigo sem nenhum verbo novo.
- **A perecibilidade virou prosa**: `prazo.carimbar_se_houver` só carimba se o
  Árbitro tiver escrito `descricao_vencida`, e a régua manda escrevê-la só para o
  que apodrece sozinho. Pedra e madeira estocam sem uma linha de código.
"""
from __future__ import annotations

import time

from .. import fisica, io, memoria, prazo, registro, trabalho
from ..io import _fail, _rejection, name_of, read_doc, write_doc

from .primitivas import (
    MATERIAS, peso_da_porcao, porcoes_de_erva, renovacao_s, roll_colher_check,
    sanear_tamanho,
)

# Quanto o extraído perecível dura antes de murchar. Doze horas: o bastante para
# atravessar uma sessão e voltar, curto o bastante para estocar erva fresca não ser
# de graça. Só se aplica ao que a régua marcou como perecível — pedra e madeira não
# recebem prazo nenhum. CALIBRAGEM: o número certo se descobre jogando.
_DURA_PERECIVEL_S = 12 * 3600


def _memoria_recusa(evento: str, verbo: str, onde: str, content: str) -> dict:
    """UMA memória por ALVO, renovada — insistir no convés do navio dez vezes é o
    MESMO fato mais insistente, não dez fatos (molde de `cozinhar\x00sem_calor`)."""
    return {"content": content, "intensity": "small", "involved": [onde],
            "valence": {onde: memoria.NEGATIVA},
            "about": f"{verbo}\x00{evento}\x00{onde}",
            "reincidencia": "tentei", "event": f"extracao_refused_{evento}"}


def _apply_extracao_ops(character_id: str, actor_folder, resolution: dict,
                        rolls: list | None = None) -> tuple[list, list]:
    applied, rejected = [], []
    if not resolution.get("extracao_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):
        rejected.append(_fail("descansando"))
        return applied, rejected
    _, present_objects, present_items = io._scene_entities(actor_folder.parent)
    place_id = None
    for fname in ("location.md", "route.md"):
        arquivo = actor_folder.parent / fname
        if arquivo.exists():
            place_fm, _ = read_doc(arquivo)
            place_id = place_fm.get("id")
            break

    for op in resolution.get("extracao_ops") or []:
        nome_cap = op.get("capacidade") or "forage"
        materia = MATERIAS.get(nome_cap) or MATERIAS["forage"]
        onde = op.get("onde")
        base = {"onde": onde, "capacidade": nome_cap}

        # o alvo é ou um `object` presente, ou o próprio LUGAR (alvo_folder None)
        alvo_folder = present_objects.get(onde)
        if alvo_folder is None and onde != place_id:
            rejected.append(_rejection(base, _fail("onde_inacessivel", onde=onde)))
            continue

        # a ferramenta é revalidada contra os ARQUIVOS, não contra o que o Árbitro
        # disse ter visto (guichê único: a proposta é palpite até o Motor conferir)
        if materia["exige_ferramenta"]:
            ferramenta = op.get("ferramenta")
            if not ferramenta or ferramenta not in present_items:
                rejected.append(_rejection(base, _fail("ferramenta_inacessivel",
                                                      item=ferramenta or "")))
                continue

        onde_nome = name_of(onde)
        if int(op.get("alvo") or 0) <= 0:
            rejected.append({
                **base, "regra": "sem_materia", "valores": {"onde": onde},
                "why": io._WHY_BY_REGRA["sem_materia"],
                "memory": _memoria_recusa(
                    "sem_materia", nome_cap, onde,
                    f"Procurei em {onde_nome}, mas não era disso que aquilo é feito.")})
            continue
        if materia["exige_ferramenta"] and int(op.get("ferramenta_nota") or 0) <= 0:
            rejected.append({
                **base, "regra": "ferramenta_impropria",
                "valores": {"onde": onde, "item": op.get("ferramenta")},
                "why": io._WHY_BY_REGRA["ferramenta_impropria"],
                "memory": _memoria_recusa(
                    "ferramenta_impropria", nome_cap, onde,
                    f"Tentei em {onde_nome} com o que tinha na mão, e não era "
                    "ferramenta para aquilo.")})
            continue
        rendimento = int(op.get("rendimento") or 0)
        if rendimento <= 0:
            rejected.append({
                **base, "regra": "nada_a_extrair", "valores": {"onde": onde},
                "why": io._WHY_BY_REGRA["nada_a_extrair"],
                "memory": _memoria_recusa(
                    "nada_a_extrair", nome_cap, onde,
                    f"Vasculhei {onde_nome}, mas não sobrou nada aproveitável.")})
            continue

        # A EXTRAÇÃO NÃO PODE SE CHAMAR COMO A FONTE (spec 062, US2). Recusa
        # DETERMINÍSTICA — não depende do juízo do Árbitro se comportar. Compara as
        # TRÊS bandas de uma vez, antes de saber qual rolou: o defeito medido (a
        # Macieira da Praça colhida virando "Macieira da Praça") sai em qualquer uma.
        #
        # MESMO NÚCLEO (prefixo até a fronteira de palavra), não substring qualquer:
        # substring pura rejeitava "Ervas" colhido de "Canteiro de Ervas", que é nome
        # LEGÍTIMO — o canteiro se chama pelo que CONTÉM, o produto vem no FIM do
        # nome da fonte. O bug real é o oposto: "Macieira" é PREFIXO de "Macieira da
        # Praça" — o produto reusa o NÚCLEO e só acrescenta qualificador.
        fonte_slug = io._slugify(onde_nome)

        def _colide_com_fonte(nome: str) -> bool:
            s = io._slugify(nome or "")
            if not s:
                return False
            return (s == fonte_slug or fonte_slug.startswith(s + "-")
                    or s.startswith(fonte_slug + "-"))

        if any(_colide_com_fonte(op.get(c))
               for c in ("nome_pobre", "nome_comum", "nome_rica")):
            rejected.append({
                **base, "regra": "extracao_nomeia_fonte", "valores": {"onde": onde},
                "why": io._WHY_BY_REGRA["extracao_nomeia_fonte"]})
            continue

        # cada capacidade alimenta a SUA maestria: praticar mineração não faz
        # herbalismo crescer (spec 071, FR-018)
        nivel = memoria.proficiencies_for(character_id).get(materia["dominio"], 0.0)
        banda, roll_info = roll_colher_check(
            actor_fm, rendimento, nivel, rolls,
            atributo=materia["atributo"], dominio=materia["dominio"])

        par = {
            "mato": (op.get("nome_pobre"), op.get("descricao_pobre")),
            "util": (op.get("nome_comum"), op.get("descricao_comum")),
            "seleta": (op.get("nome_rica"), op.get("descricao_rica")),
        }[banda]
        nome = (par[0] or "").strip() or materia["generico"]
        descricao = (par[1] or "").strip() or f"{materia['generico']}, recém-extraída."

        tamanho = sanear_tamanho(op.get("tamanho"))
        peso = peso_da_porcao(tamanho)

        criados = []
        for _ in porcoes_de_erva(banda):
            item_id = io.new_id(materia["prefixo_id"])
            io.create_entity(actor_folder.parent, item_id, "item.md", {
                "type": "item", "id": item_id, "name": nome,
                "weight_kg": peso, "size": tamanho, "origin": "emergente",
            }, descricao)
            # A PERECIBILIDADE É PROSA: só carimba se o Árbitro escreveu a descrição
            # pós-vencimento, e a régua manda escrevê-la só para o que apodrece
            # sozinho. É isto — e nenhuma linha a mais — que faz pedra e madeira
            # ESTOCAREM, e portanto que a construção de um abrigo seja possível.
            prazo.carimbar_se_houver(actor_folder.parent / item_id, op,
                                     _DURA_PERECIVEL_S)
            criados.append(item_id)

        # SÓ quando o alvo É um `object`. `location.md` NUNCA é escrita (FR-013 da
        # 054, preservado): extrair do lugar não o esgota.
        if alvo_folder is not None:
            arquivo_alvo = alvo_folder / "object.md"
            fm_alvo, corpo_original = read_doc(arquivo_alvo)
            extraida = (op.get("descricao_extraida") or "").strip() or corpo_original
            volta_em = renovacao_s(int(op.get("renovacao") or 0))
            if volta_em is not None:
                fm_alvo[trabalho.BLOCO] = {
                    "tool": nome_cap,
                    "pronto_ts": time.time() + volta_em,
                    # o resultado guarda o ANTIGO, não o novo (sentido invertido de
                    # `cook`/`forge_*`) — é isso que a renovação devolve, sem código
                    # próprio, via `trabalho.resolver_vencidas()`.
                    "resultado": {"nome": fm_alvo.get("name") or onde_nome,
                                  "description": corpo_original},
                }
            # renovacao 0: NENHUM bloco. O alvo fica como ficou, para sempre, e é a
            # ausência de promessa de volta que o diz — nunca um campo.
            write_doc(arquivo_alvo, fm_alvo, extraida)

        extremo_bom = banda == "seleta"
        ruim = banda == "mato"
        verbo = {"mine": "Arranquei", "chop": "Tirei"}.get(nome_cap, "Colhi")
        content = (f"{verbo} {nome} em {onde_nome} — rendeu bem." if extremo_bom else
                   f"{verbo} {nome} em {onde_nome}, mas não prestava para muita coisa."
                   if ruim else f"{verbo} {nome} em {onde_nome}.")
        applied.append({
            "onde": onde, "capacidade": nome_cap, "itens": criados, "banda": banda,
            "virada": bool(roll_info.get("virada")),
            # SEM `about`: cada extração bem-sucedida é fato PRÓPRIO (mesma decisão
            # de `kindle_fire` — com `about`, toda colheita da vida viraria um
            # arquivo de peso fixo e a proficiência congelaria).
            "memory": {"content": content,
                       "intensity": "medium" if extremo_bom else "small",
                       "involved": [], "valence": None,
                       "event": f"{nome_cap}_seleta" if extremo_bom else
                                f"{nome_cap}_mato" if ruim else f"{nome_cap}_util",
                       "domain": materia["dominio"]}})
    return applied, rejected


@registro.handler("extracao_ops")
def _h_extracao(cid, af, res, rolls):
    applied, rejected = _apply_extracao_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory
