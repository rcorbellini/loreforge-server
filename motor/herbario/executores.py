"""O Motor / herbario — EXECUTORES (item 31 §3: DDD por domínio; spec 054).

`_apply_forage_ops` (valida contra os arquivos, rola, aplica) + o
`@registro.handler` `_h_forage`. A ÚNICA decisão não-determinística é a rolagem
de RIQUEZA (`roll_colher_check`) — o Árbitro julgou o alvo, o Motor decide a
banda. Síncrono (research R6, alinhamento deliberado com `butcher`): as porções
nascem no MESMO turno, sem peça em processo, sem `is_busy`.

A ASSIMETRIA que dá forma à spec vive inteira aqui, no fim do laço: quando `onde`
resolve para um `object`, o corpo dele é reescrito para o estado colhido e ganha
um bloco `trabalho` de PRAZO cujo `resultado` guarda o NOME e o CORPO ANTIGOS —
sentido invertido do que `cook`/`forge_*` fazem (eles gravam o resultado NOVO). A
rebrota é `trabalho.resolver_vencidas()`, sem nenhum código próprio além da frase
em `_FATO_POR_TOOL`. Quando `onde` resolve para o LUGAR, NADA é escrito — nem
campo, nem prazo (FR-013): é `location` que não é tocada."""
from __future__ import annotations

import time
from pathlib import Path

from .. import fisica, io, memoria, registro, trabalho
from ..io import _fail, _rejection, name_of, read_doc, write_doc

from .primitivas import porcoes_de_erva, rebrota_s, roll_colher_check


def _apply_forage_ops(character_id: str, actor_folder: Path, resolution: dict,
                      rolls: list | None = None) -> tuple[list, list]:
    """Colher (spec 054). Os dois GATES (herbabilidade, riqueza) rejeitam — COM
    memória embutida (`op["memory"]`, small/negativa, recorrente por `onde`,
    mesmo padrão de `cook`) e NUNCA tocam o alvo (nada foi colhido, nada mudou).
    Passando os dois: rola RIQUEZA (com a proficiência em "herbalismo" somada
    DIRETO no total, mesmo papel que "cozinha"/"acougue" cumprem) -> banda ->
    escolhe o par nome/description correspondente -> deriva N porções
    (`porcoes_de_erva`, física determinística) -> cria N itens
    (`io.create_entity`, em loop) -> SE o alvo é `object`, reescreve o corpo dele
    e instala o prazo de rebrota."""
    applied, rejected = [], []
    if not resolution.get("forage_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):
        rejected.append(_fail("descansando"))
        return applied, rejected
    _, present_objects, _pi = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    place_id = None
    for fname in ("location.md", "route.md"):
        arquivo = actor_folder.parent / fname
        if arquivo.exists():
            place_fm, _ = read_doc(arquivo)
            place_id = place_fm.get("id")
            break

    for op in resolution.get("forage_ops") or []:
        onde = op.get("onde")
        base = {"onde": onde}
        # spec 054: mesmo universo cru de `cook_fonte`/`forge_fonte` — o alvo é
        # ou um `object` presente, ou o próprio LUGAR (alvo_folder fica None).
        alvo_folder = present_objects.get(onde)
        if alvo_folder is None and onde != place_id:
            rejected.append(_rejection(base, _fail("onde_inacessivel", onde=onde)))
            continue

        herbabilidade = int(op.get("herbabilidade") or 0)
        if herbabilidade <= 0:
            rejected.append({
                **base, "regra": "sem_vegetacao", "valores": {"onde": onde},
                "why": io._WHY_BY_REGRA["sem_vegetacao"],
                "memory": {
                    "content": f"Tentei colher em {name_of(onde)}, mas não havia "
                               "nada de verde ali.",
                    "intensity": "small", "involved": [onde],
                    "valence": {onde: memoria.NEGATIVA},
                    # UMA memória por ALVO, renovada (molde de
                    # `cozinhar\x00sem_calor\x00{fonte}`): insistir no convés do
                    # navio dez vezes é o MESMO fato mais insistente, não dez.
                    "about": f"colher\x00sem_vegetacao\x00{onde}",
                    "reincidencia": "tentei",
                    "event": "forage_refused_herbabilidade"}})
            continue
        riqueza = int(op.get("riqueza") or 0)
        if riqueza <= 0:
            rejected.append({
                **base, "regra": "nada_a_colher", "valores": {"onde": onde},
                "why": io._WHY_BY_REGRA["nada_a_colher"],
                "memory": {
                    "content": f"Vasculhei {name_of(onde)}, mas não sobrou nada "
                               "aproveitável.",
                    "intensity": "small", "involved": [onde],
                    "valence": {onde: memoria.NEGATIVA},
                    "about": f"colher\x00nada_a_colher\x00{onde}",
                    "reincidencia": "tentei",
                    "event": "forage_refused_riqueza"}})
            continue

        # spec 062, US2: A COLHEITA NÃO PODE SE CHAMAR COMO A FONTE. Recusa
        # DETERMINÍSTICA — não depende do juízo do Árbitro se comportar (a régua
        # é a primeira camada, esta é a que garante). Compara as TRÊS bandas de
        # uma vez, antes de saber qual rolou: o defeito medido (a Macieira da
        # Praça colhida virando "Macieira da Praça") pode sair em qualquer uma.
        #
        # MESMO NÚCLEO (prefixo até a fronteira de palavra), não substring
        # qualquer — medido (specs/062-.../medicoes/regua-colher.md) E pego ao
        # vivo pela própria suíte: substring pura rejeitava "Ervas" colhido de
        # "Canteiro de Ervas" (selftest_phase55.py), que é nome LEGÍTIMO — o
        # canteiro se chama pelo que ele CONTÉM, o produto vem no FIM do nome da
        # fonte, não no início. O bug real é o oposto: "Macieira" é PREFIXO de
        # "Macieira da Praça" — o produto reusa o NÚCLEO da fonte, só acrescenta
        # qualificador. Prefixo (nos dois sentidos) mais igualdade captura o
        # padrão observado sem punir o padrão "recipiente-de-produto".
        fonte_nome = name_of(onde)
        fonte_slug = io._slugify(fonte_nome)

        def _colide_com_fonte(nome: str) -> bool:
            s = io._slugify(nome or "")
            if not s:
                return False
            return (s == fonte_slug
                    or fonte_slug.startswith(s + "-")
                    or s.startswith(fonte_slug + "-"))

        colidiu = any(_colide_com_fonte(op.get(campo))
                      for campo in ("nome_mato", "nome_util", "nome_seleta"))
        if colidiu:
            rejected.append({
                **base, "regra": "colheita_nomeia_fonte", "valores": {"onde": onde},
                "why": io._WHY_BY_REGRA["colheita_nomeia_fonte"]})
            continue

        nivel_herbalismo = memoria.proficiencies_for(character_id).get("herbalismo", 0.0)
        banda, roll_info = roll_colher_check(actor_fm, riqueza, nivel_herbalismo, rolls)

        par = {
            "mato": (op.get("nome_mato"), op.get("descricao_mato")),
            "util": (op.get("nome_util"), op.get("descricao_util")),
            "seleta": (op.get("nome_seleta"), op.get("descricao_seleta")),
        }[banda]
        nome = (par[0] or "").strip() or "Matéria vegetal"
        descricao = (par[1] or "").strip() or "Um punhado de matéria vegetal colhida."

        criados = []
        for peso in porcoes_de_erva(banda):
            item_id = io.new_id("erva")
            io.create_entity(actor_folder.parent, item_id, "item.md", {
                "type": "item", "id": item_id, "name": nome,
                "weight_kg": peso, "origin": "emergente",
            }, descricao)
            criados.append(item_id)

        # FR-013a — só quando o alvo É um `object`; `location` (alvo_folder None)
        # sai da ação byte por byte como entrou (FR-013).
        if alvo_folder is not None:
            arquivo_alvo = alvo_folder / "object.md"
            fm_alvo, corpo_original = read_doc(arquivo_alvo)
            descricao_colhida = (op.get("descricao_colhida") or "").strip() \
                or corpo_original
            fm_alvo[trabalho.BLOCO] = {
                "tool": "forage",
                "pronto_ts": time.time() + rebrota_s(),
                # o resultado guarda o ANTIGO, não o novo (sentido invertido de
                # `cook`/`forge_*`) — é isso que a rebrota devolve, sem código
                # próprio, via `trabalho.resolver_vencidas()`.
                "resultado": {"nome": fm_alvo.get("name") or name_of(onde),
                              "description": corpo_original},
            }
            write_doc(arquivo_alvo, fm_alvo, descricao_colhida)

        extremo_bom = banda == "seleta"
        ruim = banda == "mato"
        intensity = "medium" if extremo_bom else "small"
        onde_nome = name_of(onde)
        content = (f"Colhi {nome} em {onde_nome} — rendeu bem."
                   if extremo_bom else
                   f"Colhi {nome} em {onde_nome}, mas não prestava para muita "
                   "coisa." if ruim else
                   f"Colhi {nome} em {onde_nome}.")
        applied.append({
            "onde": onde, "itens": criados, "banda": banda,
            "virada": bool(roll_info.get("virada")),
            # SEM `about`: cada colheita bem-sucedida é fato PRÓPRIO (mesma
            # decisão de `kindle_fire` — com `about` toda colheita da vida viraria
            # um arquivo de peso fixo, e a proficiência congelaria).
            "memory": {"content": content, "intensity": intensity, "involved": [],
                       "valence": None,
                       "event": "forage_seleta" if extremo_bom else
                                "forage_mato" if ruim else "forage_util",
                       "domain": "herbalismo"}})
    return applied, rejected


@registro.handler("forage_ops")
def _h_forage(cid, af, res, rolls):
    applied, rejected = _apply_forage_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory
