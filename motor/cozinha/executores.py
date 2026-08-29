"""O Motor / cozinha — EXECUTORES (item 31 §3: DDD por domínio; spec 048).

`_apply_cozinha_ops` (valida contra os arquivos, rola, aplica) + o
`@registro.handler` `_h_cozinha` (encadeia memória). A ÚNICA decisão não-
determinística é a rolagem de FAVORABILIDADE (`roll_cook_check`) — o Árbitro
julgou a cena, o Motor decide a banda. Os ingredientes são consumidos NO ATO
(mesma exceção escopada do Princípio IV que `eat` já usa, estendida aqui para
uma LISTA — R3 do plano); o prato só passa a EXISTIR na materialização
preguiçosa (`primitivas.lazy_evaluate`, chamada de `get_context`).
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import estado, fisica, io, memoria, registro, trabalho
from ..estado import _set_field
from ..io import _fail, _rejection, name_of, read_doc

from .primitivas import duracao_segundos, roll_cook_check


def _apply_cozinha_ops(character_id: str, actor_folder: Path, resolution: dict,
                       rolls: list | None = None) -> tuple[list, list]:
    """Cozinhar (spec 048). Os dois GATES de admissão (fonte de calor,
    cozinhabilidade) rejeitam — COM memória embutida (`op["memory"]`,
    small/negativa, mesmo padrão de `eat`/`drink`). Passando os dois: rola
    FAVORABILIDADE (com a proficiência em "cozinha" somada DIRETO no total —
    divergência deliberada de `cura`, spec 048 Eixo 3) -> banda -> escolhe a
    description candidata correspondente -> consome os ingredientes
    (`io.remove_entity`, em loop) -> agenda `status.cozinhando` (prato já
    decidido, materializa quando o tempo real se cumprir)."""
    applied, rejected = [], []
    if not resolution.get("cozinha_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    # spec 052: "está cozinhando" deixou de ser um campo no personagem e passou a
    # ser DERIVADO da panela no fogo — a entidade que o ato deixa na cena.
    if trabalho.is_busy(actor_folder):
        rejected.append(_fail("ja_cozinhando"))
        return applied, rejected
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    _, present_objects, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    place_id = None
    for fname in ("location.md", "route.md"):
        place_file = actor_folder.parent / fname
        if place_file.exists():
            place_fm, _ = read_doc(place_file)
            place_id = place_fm.get("id")
            break

    for op in resolution.get("cozinha_ops") or []:
        ingredientes = list(op.get("ingredientes") or [])
        fonte_calor = op.get("fonte_calor")
        base = {"cozinhar": ingredientes, "fonte_calor": fonte_calor}
        # spec 052: a fonte de calor pode ser um object OU o próprio LUGAR — a
        # lareira de uma cozinha costuma estar escrita na prosa do ambiente, não
        # instanciada. A pasta da fonte não é usada para mais nada aqui; o que
        # importa é que ela EXISTA na cena.
        fonte_folder = present_objects.get(fonte_calor)
        if fonte_folder is None and fonte_calor != place_id:
            rejected.append(_rejection(base, _fail("fonte_calor_inacessivel",
                                                    fonte_calor=fonte_calor)))
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

        if int(op.get("fonte_de_calor") or 0) <= 0:
            rejected.append({
                **base, "regra": "sem_calor", "valores": {"fonte_calor": fonte_calor},
                "why": io._WHY_BY_REGRA["sem_calor"],
                "memory": {
                    "content": f"Tentei cozinhar em {name_of(fonte_calor)}, mas não "
                               "tinha calor nenhum.",
                    "intensity": "small", "involved": [fonte_calor],
                    "valence": {fonte_calor: memoria.NEGATIVA},
                    # UMA memória por fonte fria, renovada: tentar cozinhar na
                    # mesma rua dez vezes é o MESMO fato mais insistente, não dez
                    # fatos. A Elga acumulou 9 cópias disto (2026-08-20) e eram
                    # elas que a mandavam tentar de novo.
                    "about": f"cozinhar\x00sem_calor\x00{fonte_calor}",
                    "reincidencia": "tentei",
                    "event": "cook_refused_fonte"}})
            continue
        if int(op.get("cozinhabilidade") or 0) <= 0:
            rejected.append({
                **base, "regra": "nao_cozinhavel", "valores": {"ingredientes": ingredientes},
                "why": io._WHY_BY_REGRA["nao_cozinhavel"],
                "memory": {
                    "content": "Tentei cozinhar, mas aquilo não formava prato nenhum.",
                    "intensity": "small", "involved": list(ingredientes),
                    "valence": {i: memoria.NEGATIVA for i in ingredientes},
                    "about": "cozinhar\x00nao_cozinhavel", "reincidencia": "tentei",
                    "event": "cook_refused_combo"}})
            continue

        favorabilidade = int(op.get("favorabilidade") or 5)
        nivel_cozinha = memoria.proficiencies_for(character_id).get("cozinha", 0.0)
        banda, roll_info = roll_cook_check(actor_fm, favorabilidade, nivel_cozinha, rolls)
        descricao = {
            "ruim": op.get("descricao_ruim"), "media": op.get("descricao_media"),
            "otima": op.get("descricao_otima"),
        }.get(banda) or "Um prato preparado, de resultado incerto."
        nome = (op.get("nome") or "").strip() or "Prato"

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
        # spec 052: nasce uma PANELA NO FOGO — entidade real na cena, visível para
        # todos, que qualquer um pode pegar ou roubar. Antes, os ingredientes sumiam
        # e NADA existia no mundo até o prato ficar pronto: o estado morava num campo
        # escondido do personagem, e o prato materializava no lugar onde o ato tinha
        # começado, mesmo que o cozinheiro já estivesse longe. Agora o prato nasce
        # ONDE A PANELA ESTIVER (spec 052, FR-046).
        corpo_panela = (f"{nome} no fogo, ainda no meio do preparo — o cheiro já "
                        "escapa, mas ainda não está pronto.")
        _peca_id, panela = trabalho.criar_peca(
            actor_folder.parent, corpo_panela,
            {"tool": "cook", "ator": character_id,
             "pronto_ts": time.time() + duracao_segundos(duracao_nota),
             # spec 053: `prato` era o nome específico de cook dentro de um bloco
             # genérico. Virou `resultado`, que qualquer domínio de prazo usa.
             "resultado": {"nome": nome, "description": descricao}},
            name=f"{nome} (no fogo)", weight_kg=round(peso_kg, 3) or 0.3)

        extremo_bom = banda == "otima"
        ruim = banda == "ruim"
        intensity = "medium" if extremo_bom else "small"
        content = (f"Cozinhei {nome} e ficou ótimo." if extremo_bom else
                   f"Cozinhei {nome}, mas não ficou bom." if ruim else
                   f"Cozinhei {nome}.")
        applied.append({
            "ingredientes": ingredientes, "fonte_calor": fonte_calor, "banda": banda,
            "peca_id": _peca_id,  # spec 057: exposto para o leque de testemunha
            "virada": bool(roll_info.get("virada")),
            "memory": {"content": content, "intensity": intensity, "involved": [],
                       "valence": None,
                       "event": "cook_otimo" if extremo_bom else
                                "cook_ruim" if ruim else "cook",
                       "domain": "cozinha"}})
    return applied, rejected


@registro.handler("cozinha_ops")
def _h_cozinha(cid, af, res, rolls):
    applied, rejected = _apply_cozinha_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory
