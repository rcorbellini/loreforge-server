"""O Motor / botica — EXECUTORES (item 31 §3: DDD por domínio; spec 055).

`_apply_botica_ops` (valida contra os arquivos, rola, aplica) + o
`@registro.handler` `_h_botica`. A ÚNICA decisão não-determinística é a
rolagem de FAVORABILIDADE (`roll_preparar_check`) — o Árbitro julgou a cena,
o Motor decide a banda. Os ingredientes são consumidos NO ATO (mesma exceção
escopada do Princípio IV que `cook` já usa, estendida para uma LISTA); o
remédio só passa a EXISTIR na materialização preguiçosa
(`trabalho.resolver_vencidas`, chamada de `get_context`) — mesmo relógio que
`cook`/`kindle_fire`/`forage` já compartilham, sem alteração nenhuma.

O RECIPIENTE nunca é escrito, nunca trava — divergência deliberada de
`forage` (que reescreve um `object` colhido porque há PROSA AUTORAL a
proteger): aqui não há nada do tipo, e `cook` já decidiu que exclusividade de
equipamento não vale o mecanismo (um fogão serve várias panelas ao mesmo
tempo hoje)."""
from __future__ import annotations

import time
from pathlib import Path

from .. import fisica, io, memoria, registro, trabalho
from ..io import _fail, _rejection, read_doc

from .primitivas import duracao_segundos_preparo, roll_preparar_check


def _apply_botica_ops(character_id: str, actor_folder: Path, resolution: dict,
                      rolls: list | None = None) -> tuple[list, list]:
    """Preparar (spec 055). Os dois GATES de admissão (recipiente, preparabilidade)
    rejeitam — COM memória embutida (`op["memory"]`, small/negativa, renovada por
    `about`, mesmo padrão de `cook`). Passando os dois: rola FAVORABILIDADE (com a
    proficiência em "botica" somada DIRETO no total) -> banda -> escolhe a
    description candidata correspondente -> consome os ingredientes
    (`io.remove_entity`, em loop) -> instancia a PEÇA EM PROCESSO
    (`trabalho.criar_peca`, molde da panela no fogo) -> materializa quando o
    tempo real se cumprir."""
    applied, rejected = [], []
    if not resolution.get("botica_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if trabalho.is_busy(actor_folder):
        rejected.append(_fail("ja_preparando"))
        return applied, rejected
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    _, present_objects, present_items = io._scene_entities(actor_folder.parent)  # cena fresca
    place_id = None
    for fname in ("location.md", "route.md"):
        place_file = actor_folder.parent / fname
        if place_file.exists():
            place_fm, _ = read_doc(place_file)
            place_id = place_fm.get("id")
            break

    for op in resolution.get("botica_ops") or []:
        ingredientes = list(op.get("ingredientes") or [])
        recipiente = op.get("recipiente")
        base = {"preparar": ingredientes, "recipiente": recipiente}
        # spec 055: o recipiente pode ser um object OU o próprio LUGAR — mesmo
        # universo cru que cook_fonte/forage_onde já usam. A pasta não é usada
        # para mais nada aqui; importa só que ela EXISTA na cena.
        recipiente_folder = present_objects.get(recipiente)
        if recipiente_folder is None and recipiente != place_id:
            rejected.append(_rejection(base, _fail("recipiente_inacessivel",
                                                    recipiente=recipiente)))
            continue
        ingrediente_folders: list[tuple[str, Path]] = []
        faltando = None
        for iid in ingredientes:
            folder = present_items.get(iid)
            if folder is None:
                faltando = iid
                break
            ingrediente_folders.append((iid, folder))
        if faltando is not None:
            rejected.append(_rejection(base, _fail("ingrediente_inacessivel", item=faltando)))
            continue

        if int(op.get("recipiente_adequado") or 0) <= 0:
            rejected.append({
                **base, "regra": "sem_recipiente", "valores": {"recipiente": recipiente},
                "why": io._WHY_BY_REGRA["sem_recipiente"],
                "memory": {
                    "content": "Tentei preparar algo, mas aquilo não servia de "
                               "recipiente nenhum.",
                    "intensity": "small", "involved": [recipiente],
                    "valence": {recipiente: memoria.NEGATIVA},
                    # UMA memória por recipiente, renovada: mesmo molde de
                    # `cozinhar\x00sem_calor\x00{fonte}`.
                    "about": f"preparar\x00sem_recipiente\x00{recipiente}",
                    "reincidencia": "tentei",
                    "event": "brew_refused_recipiente"}})
            continue
        if int(op.get("preparabilidade") or 0) <= 0:
            rejected.append({
                **base, "regra": "nao_combina", "valores": {"ingredientes": ingredientes},
                "why": io._WHY_BY_REGRA["nao_combina"],
                "memory": {
                    "content": "Tentei preparar, mas aquilo não formava preparo "
                               "nenhum junto.",
                    "intensity": "small", "involved": list(ingredientes),
                    "valence": {i: memoria.NEGATIVA for i in ingredientes},
                    "about": "preparar\x00nao_combina", "reincidencia": "tentei",
                    "event": "brew_refused_combo"}})
            continue

        favorabilidade = int(op.get("favorabilidade") or 5)
        nivel_botica = memoria.proficiencies_for(character_id).get("botica", 0.0)
        banda, roll_info = roll_preparar_check(actor_fm, favorabilidade, nivel_botica, rolls)
        descricao = {
            "ruim": op.get("descricao_ruim"), "media": op.get("descricao_media"),
            "otima": op.get("descricao_otima"),
        }.get(banda) or "Um preparo de resultado incerto."
        nome = (op.get("nome") or "").strip() or "Preparo"

        peso_kg = 0.0
        for _iid, folder in ingrediente_folders:
            item_fm, _ = read_doc(folder / "item.md")
            try:
                peso_kg += float(item_fm.get("weight_kg") or 0)
            except (TypeError, ValueError):
                pass
        for _iid, folder in ingrediente_folders:
            io.remove_entity(folder)  # consumo total — exceção escopada do Princípio IV

        duracao_nota = int(op.get("duracao") or 0)
        # spec 055: nasce um CALDO NO RECIPIENTE — entidade real na cena, visível
        # para todos, que qualquer um pode pegar ou roubar. Molde EXATO da panela
        # no fogo (spec 052) — o recipiente que INSPIROU o ato segue intocado; a
        # peça em processo nasce ONDE O ATO ACONTECEU, não presa ao recipiente.
        corpo_peca = (f"{nome}, ainda descansando no recipiente — o cheiro já se "
                     "sente, mas ainda não está pronto.")
        _peca_id, peca = trabalho.criar_peca(
            actor_folder.parent, corpo_peca,
            {"tool": "brew", "ator": character_id,
             "pronto_ts": time.time() + duracao_segundos_preparo(duracao_nota),
             "resultado": {"nome": nome, "description": descricao}},
            name=f"{nome} (preparando)", weight_kg=round(peso_kg, 3) or 0.3)

        extremo_bom = banda == "otima"
        ruim = banda == "ruim"
        intensity = "medium" if extremo_bom else "small"
        content = (f"Preparei {nome} e ficou ótimo." if extremo_bom else
                   f"Preparei {nome}, mas não ficou bom." if ruim else
                   f"Preparei {nome}.")
        applied.append({
            "ingredientes": ingredientes, "recipiente": recipiente, "banda": banda,
            "virada": bool(roll_info.get("virada")),
            "memory": {"content": content, "intensity": intensity, "involved": [],
                       "valence": None,
                       "event": "brew_otimo" if extremo_bom else
                                "brew_ruim" if ruim else "brew",
                       "domain": "botica"}})
    return applied, rejected


@registro.handler("botica_ops")
def _h_botica(cid, af, res, rolls):
    applied, rejected = _apply_botica_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory
