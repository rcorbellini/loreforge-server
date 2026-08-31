"""O Motor / musica — EXECUTORES (item 31 §3: DDD por domínio; spec 058).

`_apply_sing_ops` (revalida contra os arquivos, rola, aplica) + o
`@registro.handler` `_h_sing`. A ÚNICA decisão não-determinística é o
DESFECHO da rolagem (`roll_sing_check`) — não há gate de admissão: cantar
sempre acontece (spec 058, "cantar não é cozinhar"). A propagação para a
plateia reusa a PRIMITIVA `_record_hearsay` da spec 017 (Princípio XII —
`sing` NÃO chama `ask_about`); a memória do CANTOR sai pelo caminho GENÉRICO
de `react_actor_memory` (`op["memory"]` embutido), a da plateia SOBRE o
cantor pelo leque de testemunha (`react_witness`, ver `primitivas.py` do
domínio `memoria` — branch em `_witness_facts`).
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import fisica, io, itens, memoria, registro
from ..io import _fail, read_doc
from ..memoria import _char_name, _is_alive, _record_hearsay, memory_involved

from .primitivas import degraus_por_desfecho, roll_sing_check


def _apply_sing_ops(character_id: str, actor_folder: Path, resolution: dict,
                    rolls: list | None = None) -> tuple[list, list]:
    """Cantar (spec 058). Por op (`memoria_id`, `instrumento`, `letra`,
    `nota_instrumento`): revalida a memória-fonte sobre o ARQUIVO (existe,
    ainda viva), rola o DESFECHO, e propaga:

    - para cada ouvinte PRESENTE, vivo, de pé e acordado, que NÃO seja o
      cantor nem o sujeito do episódio: UM reconto (`_record_hearsay`),
      exceto em `fracasso` — o degrau que decai vem de `degraus_por_desfecho`;
    - para cada ouvinte PRESENTE (menos o cantor, o sujeito FICA — ele
      testemunha cantarem sobre ele): a memória de reputação do CANTOR, via
      `op["testemunhas"]` — o LEQUE (`react_witness`) é quem escreve, lendo
      `_witness_facts`/`musica_ops_applied`, não este executor.

    Lugar VAZIO (só o cantor): acontece, ninguém ganha memória em terceiros,
    e a memória do próprio cantor é gravada do mesmo jeito (spec 058, US5 —
    cantar sozinho é praticar)."""
    applied, rejected = [], []
    ops = [o for o in (resolution.get("musica_ops") or []) if isinstance(o, dict)]
    if not ops:
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    # spec 058: o único portão que sobra é o de ESTADO — dormindo (`is_resting`,
    # que É "descansando" neste projeto: ver `fisica.sleep_state`, "dorme até se
    # recuperar OU ser acordado") impede QUALQUER ação, `sing` incluído; mesmo
    # check que `brew`/`accuse`/`hearsay` já fazem. NÃO há checagem separada de
    # morto/caído aqui: nenhuma tool deste projeto checa o próprio estado-de-
    # combate do ATOR (só o de ALVOS) — um personagem caído/morto não chega a
    # ter turno, controlado em outra camada.
    if fisica.is_resting(actor_fm):
        rejected.append(_fail("descansando"))
        return applied, rejected
    now = time.time()
    present_chars, _present_objects, _present_items = io._scene_entities(
        actor_folder.parent)

    for op in ops:
        memoria_id = op.get("memoria_id")
        letra = (op.get("letra") or "").strip()
        instrumento = op.get("instrumento")
        try:
            nota_instrumento = int(op.get("instrumento_nota") or 0)
        except (TypeError, ValueError):
            nota_instrumento = 0
        # revalida: o instrumento apontado pela guarda ainda está NA MÃO agora —
        # a proposta do corpo é palpite até aqui (contracts/sing-tool.md). Some
        # entre a guarda e a aplicação (raríssimo, fase única): o bônus zera,
        # NUNCA recusa a canção — cantar não tem gate, só o que ele ganha muda.
        empunhou = None
        if instrumento is not None:
            # EMPUNHAR O QUE JÁ SE CARREGA (2026-08-30): o alaúde guardado na
            # bolsa deixava de valer bônus por não estar na mão. O Motor o traz
            # (`itens.bring_to_hand`, espelho do `_accommodate` do item 44). Se
            # nem assim couber na pega, o bônus zera — como já zerava —, e a
            # canção segue: cantar não tem gate, só o que ele ganha muda.
            empunhou, _rej_mao = itens.bring_to_hand(actor_folder, instrumento)
            instr_folder = actor_folder / instrumento
            instr_fm = (read_doc(instr_folder / "item.md")[0]
                       if (instr_folder / "item.md").exists() else {})
            if fisica.item_slot(instr_fm) != fisica.HAND_SLOT:
                instrumento = None
                nota_instrumento = 0
                empunhou = None
        mem_path = actor_folder / "memories" / f"{memoria_id}.md"
        if not mem_path.exists():
            continue   # revalidação: sumiu entre a guarda e a aplicação (raro)
        fonte_fm, fonte_body = read_doc(mem_path)
        if fonte_fm.get("type") != "memory" or not _is_alive(fonte_fm, now):
            continue
        sobre = next((x for x in memory_involved(fonte_fm) if x and x != character_id),
                     None)
        if not sobre:
            continue

        nivel_musica = memoria.proficiencies_for(character_id).get("musica", 0.0)
        desfecho, roll_info = roll_sing_check(actor_fm, nota_instrumento,
                                              nivel_musica, rolls)
        degraus = degraus_por_desfecho(desfecho)

        # DUAS plateias (research R5): a do RECONTO exclui cantor E sujeito
        # (FR-006 — ele não troca a própria vivência por um boato dela); a da
        # REPUTAÇÃO exclui só o cantor (o sujeito ouve cantarem sobre ele).
        ouvintes_reputacao: list[str] = []
        ouvintes_reconto: list[tuple[str, Path]] = []
        for oid, ofolder in present_chars.items():
            if oid == character_id:
                continue
            ofm, _ = read_doc(ofolder / "character.md")
            if fisica.is_down(ofm) or fisica.is_resting(ofm):
                continue
            ouvintes_reputacao.append(oid)
            if oid != sobre:
                ouvintes_reconto.append((oid, ofolder))

        reconto_ids: list[dict] = []
        if degraus is not None and letra:
            # `about` chaveado pelo EPISÓDIO fonte (não pelo cantor): FR-027 —
            # cantar o MESMO feito à MESMA plateia toda noite renova UMA
            # memória por ouvinte (`vezes` crescendo), nunca infla em arquivos,
            # e a intensidade nunca sobe na renovação (garantia de
            # `_remember_recurring`).
            for oid, ofolder in ouvintes_reconto:
                mid = _record_hearsay(ofolder, [fonte_fm], sobre, letra,
                                      character_id, degraus=degraus,
                                      about=f"sing_reconto\x00{memoria_id}")
                if mid:
                    reconto_ids.append({"target": oid, "id": mid})

        fisica.spend_fatigue(character_id, "baixo")

        sobre_nome = _char_name(sobre)
        content = (f"Cantei sobre {sobre_nome}: {letra}" if letra
                  else f"Cantei sobre {sobre_nome}.")
        evento = {"otimo": "sing_otimo", "comum": "sing", "ruim": "sing_ruim",
                 "fracasso": "sing_ruim"}[desfecho]
        applied.append({
            "memoria_id": memoria_id, "sobre": sobre, "instrumento": instrumento,
            "desfecho": desfecho, "letra": letra,
            **({"empunhou": empunhou} if empunhou else {}),
            "ouvintes": ouvintes_reputacao,
            "virada": bool(roll_info.get("virada")),
            "reconto_ids": reconto_ids,
            "memory": {
                "content": content, "intensity": "small",
                "involved": list(ouvintes_reputacao), "valence": None,
                "event": evento, "domain": "musica", "about": memoria_id,
            },
        })
    return applied, rejected


@registro.handler("musica_ops")
def _h_sing(cid, af, res, rolls):
    applied, rejected = _apply_sing_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)
