"""O Motor / craft — EXECUTORES (spec 057).

`_apply_craft_ops` (valida contra os arquivos, rola, aplica) + o
`@registro.handler` `_h_craft`.

TRÊS CAMINHOS, não dois — a generalização real desta spec sobre o molde de
`forja` (spec 052):

  ABERTURA RÁPIDA   viabilidade > 0 e a duração cabe no LIMIAR_SINCRONO: a
                    entidade nasce PRONTA no mesmo ato, sem bloco `trabalho`
                    nenhum — molde de `forage`/`esquartejar`, não de `forja`.
  ABERTURA LONGA    viabilidade > 0 e a duração excede o limiar: nasce peça em
                    processo no relógio de ESFORÇO — molde de `forja`, a
                    primeira chamada NUNCA conclui.
  RETOMADA          nenhuma régua, nenhuma rolagem, nenhuma LLM. Credita o
                    tempo trabalhado (clamp) e, se cumprido, materializa.
"""
from __future__ import annotations

from pathlib import Path

from .. import fisica, io, registro, trabalho
from ..io import _fail, _rejection, read_doc

from .primitivas import (
    LIMIAR_SINCRONO_S, banda_final, duracao_segundos_craft, roll_craft_check,
    sanear_tamanho,
)

_FILENAME_POR_TIPO = {"item": "item.md", "object": "object.md",
                      "location": "location.md"}

# `craft` é o caminho GENÉRICO — ao contrário de `forge_weapon`/`forge_armor`
# (ferraria/armaria, DEX/STR), não há um segundo tipo pra desambiguar aqui.
# Fixos no executor, nunca julgados (mesmo molde de `forja/executores.py`,
# `_DOMINIO`/`_ATRIBUTO`): pedir isso ao Árbitro a cada tentativa é o que
# fazia um boneco de cera virar "herbalismo" — sem material pra ancorar a
# resposta, o modelo colava no vocabulário mais forte do prompt (a descrição
# do LUGAR), não no que estava sendo feito.
_DOMINIO = "construtor"
_ATRIBUTO = "DEX"


def _posicao_e_peso_kg(tipo: str, tamanho: str, actor_fm: dict) -> tuple[str, float]:
    """Onde a coisa fica, e quanto pesa — decisão do MOTOR, não do Árbitro.

    `tamanho` (a régua compartilhada, `validator.SIZES`) já é o que decide se
    um item cabe num contêiner ou o porte de uma location (spec 004/012);
    craft só precisava parar de pedir a POSIÇÃO pronta e passar a comparar
    peso contra `fisica.carry_capacity`, do mesmo jeito que qualquer outro
    peso do mundo já é validado. object/location nunca têm posse física —
    ficam sempre na location (mesma regra de antes)."""
    peso = fisica.DEFAULT_WEIGHT_BY_SIZE.get(tamanho, fisica.DEFAULT_WEIGHT_BY_SIZE["P"])
    if tipo != "item":
        return "solto_na_location", peso
    posicao = ("com_personagem" if peso <= fisica.carry_capacity(actor_fm)
              else "solto_na_location")
    return posicao, peso


def _memoria_ator(peca_id: str, content: str, evento: str,
                  dominio: str | None, intensity: str = "small") -> dict:
    """Contrato genérico (spec 038): o payload embute a memória do ator.

    SEM `about` — de propósito, mesmo molde de `forge_start`/`forge_session`
    (nenhuma memória de ator em `forja/executores.py` usa `about`). O motivo
    NÃO é estilo: `about` é a MESMA chave que `remember_recurring` usa para
    RENOVAR (`(evento, about)`, `_remember_recurring`). Se `about` fosse
    `character_id` (pensando em `dono()`), duas peças DIFERENTES do mesmo
    autor colidiriam na mesma memória — perderia a segunda ao "renovar" a
    primeira. `involved` cita `peca_id` mesmo assim (rastreável, não é o que
    quebra); a resolução de `dono()` sem testemunha nenhuma passa pela posse
    FÍSICA (ver `_abrir`, caminho síncrono: a peça nasce COM o personagem, não
    solta), não por este campo."""
    return {"content": content, "intensity": intensity,
            "involved": [peca_id] if peca_id else [],
            "valence": None, "event": evento, "domain": dominio or "nenhuma"}


def _gerar_route_de_acesso(mae_folder: Path, filha_folder: Path, nome_filha: str) -> None:
    """Conserto pós-057 (achado da exploração): sem isto, uma `location` criada
    por craft nasce ILHADA. Confirmado lendo o código real: o único mecanismo
    de movimento entre locations é `enter_route`, e o enum de destinos
    (`_available_routes`, `motor/rotas/primitivas.py`) vem exclusivamente de
    `route.md` DECLARADA em algum lugar do mundo (`WORLD_DIR.rglob`, não filtra
    por pasta) — aninhamento de pasta sozinho NUNCA bastou (as duas locations
    aninhadas que já existiam no mundo, `quarto-da-elga`/`quarto-de-hospedes`,
    têm `route.md` própria, escrita à mão, mesmo formato usado aqui).

    Mesmo formato de `escada-de-elga`: `travel_time_base` pequeno (é uma porta
    ali do lado, não uma jornada), bidirecional, sem restrição — craft não
    decide fechadura, isso é outra feature. A rota nasce como IRMÃ da location
    nova, na pasta da location-MÃE (mesmo `parent_folder` que já recebeu a
    location) — `all_route_ids`/`_available_routes` acham por `rglob`, então o
    lugar exato no filesystem não importa para o mecanismo, só para a
    organização; ficar ao lado da mãe é o mais legível para quem for olhar."""
    mae_fm, _ = read_doc(mae_folder / "location.md")
    mae_id = mae_fm.get("id") or mae_folder.name
    mae_nome = mae_fm.get("name") or mae_id
    filha_fm, _ = read_doc(filha_folder / "location.md")
    filha_id = filha_fm.get("id") or filha_folder.name
    route_id = io.new_id("acesso")
    io.create_entity(mae_folder, route_id, "route.md", {
        "type": "route", "id": route_id, "name": f"Entrada de {nome_filha}",
        "from": mae_id, "to": filha_id, "travel_time_base": 10,
        "bidirectional": True,
        "prerequisites": [{"id": "sem-restricao", "type": "none"}],
        "origin": "emergente",
    }, f"O jeito de ir e vir entre {mae_nome} e {nome_filha}.")


def _apply_craft_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list, list]:
    applied, rejected = [], []
    if not resolution.get("craft_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected

    _, present_objects, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    pendente = trabalho.peca_pendente_de(actor_folder)
    # a peça em processo pode ser ITEM, OBJECT ou LOCATION (spec 057) — a retomada
    # precisa achá-la nos três universos; materiais, esses sim, são sempre item.
    # Location em processo é FILHA da location atual, não "presente na cena" no
    # sentido de `_scene_entities` (topologia, não presença — spec 035), daí a
    # varredura à parte (`pecas_location_em`).
    present_pecas = {**present_items, **present_objects,
                     **trabalho.pecas_location_em(actor_folder.parent)}

    for op in resolution.get("craft_ops") or []:
        if op.get("retomada"):
            resultado = _retomar(character_id, actor_folder, op, present_pecas,
                                 pendente)
        else:
            resultado = _abrir(character_id, actor_folder, actor_fm, op,
                               present_items, pendente, rolls)
        ok, payload = resultado
        (applied if ok else rejected).append(payload)
    return applied, rejected


def _abrir(character_id, actor_folder, actor_fm, op, present_items, pendente,
           rolls):
    """Começar algo. É o único caminho que consulta a régua e rola dado."""
    materiais = list(op.get("materiais") or [])
    narracao = op.get("narracao") or ""
    base = {"narracao": narracao, "materiais": materiais}

    if pendente is not None:
        return False, _rejection(base, _fail("ja_trabalhando"))

    material_folders = []
    for mid in materiais:
        pasta = present_items.get(mid)
        if pasta is None:
            return False, _rejection(base, _fail("material_inacessivel", item=mid))
        material_folders.append((mid, pasta))

    viabilidade = int(op.get("viabilidade") or 0)
    if viabilidade <= 0:
        # GATE — nenhum material é consumido (FR-003/FR-007).
        return False, {
            **base, "regra": "sem_viabilidade", "valores": {},
            "why": io._WHY_BY_REGRA["sem_viabilidade"],
            "memory": _memoria_ator("", "Tentei fazer algo, mas não havia com "
                                    "o quê.", "craft_recusado", None)}

    for _mid, pasta in material_folders:
        io.remove_entity(pasta)  # consumo total — mesma exceção escopada de forja/cook

    tipo = op.get("tipo") or "item"
    tamanho = sanear_tamanho(op.get("tamanho"))
    dominio = _DOMINIO
    atributo = _ATRIBUTO
    filename = _FILENAME_POR_TIPO.get(tipo, "item.md")
    banda, extremo, _info = roll_craft_check(actor_fm, viabilidade, atributo, rolls)
    duracao_s = duracao_segundos_craft(op.get("duracao") or 0)
    nome = (op.get("nome") or "").strip() or "Algo"
    posicao, peso_kg = _posicao_e_peso_kg(tipo, tamanho, actor_fm)

    if duracao_s < LIMIAR_SINCRONO_S:
        # SÍNCRONO — conclui no mesmo ato (molde de `forage`/`esquartejar`):
        # NUNCA existe bloco `trabalho` para algo que nasce pronto.
        final = banda_final(banda, extremo)
        descricao = (op.get("descricao_alta") if final not in ("falha", "comum")
                    else op.get("descricao_baixa")) or "Algo simples, recém-feito."
        peca_id = io.new_id("local" if tipo == "location" else "craft")
        fm = {"type": tipo, "id": peca_id, "name": nome, "origin": "emergente"}
        if tipo == "item":
            fm["weight_kg"] = peso_kg
            fm["size"] = tamanho
        if tipo == "location":
            fm["size"] = "PP"
        # "com_personagem" (o caso comum — sai da mão de quem fez) ou
        # "solto_na_location" (grande/impróprio pra carregar): o MOTOR decide,
        # comparando `peso_kg` (de `tamanho`) contra `carry_capacity` — não é
        # mais o Árbitro escolhendo a posição pronta (`_posicao_e_peso_kg`).
        # Isso não é só verossimilhança: "com_personagem" é o que faz `dono()`
        # reconhecer o autor MESMO sem testemunha nenhuma, pelo fallback de
        # posse física que a primitiva já tem — sem campo `owner` nem gambiarra
        # em memória. object/location NUNCA têm posse física: ficam sempre na
        # location (object fixo ali; location nasce como SUBPASTA da location
        # atual — `actor_folder.parent` já É "dentro de onde se está").
        parent_folder = (actor_folder if tipo == "item"
                         and posicao == "com_personagem" else actor_folder.parent)
        nova_pasta = io.create_entity(parent_folder, peca_id, filename, fm, descricao)
        if tipo == "location":
            _gerar_route_de_acesso(actor_folder.parent, nova_pasta, nome)
        dominio_final = dominio if final != "falha" else None
        return True, {
            "peca": peca_id, "tipo": tipo, "materiais": materiais,
            "retomada": False, "concluido": True, "sincrono": True,
            "fase": "conclusao", "dominio": dominio_final or "nenhuma",
            "banda": final,
            "memory": _memoria_ator(peca_id, f"Fiz {nome}.", "craft",
                                    dominio_final, "small")}

    # ASSÍNCRONO — nasce peça em processo (molde de `forja`). A peça em processo
    # SEMPRE mora na location (nunca com o personagem, mesmo se `posicao` for
    # "com_personagem" — um trabalho inacabado não vive largado na sua bolsa; é
    # uma COISA no mundo, US6). `posicao` (já derivada de `tamanho` acima) só
    # decide o destino FINAL, aplicado na conclusão em `_retomar` (move a pasta
    # se for item + com_personagem).
    bloco = {
        "tool": "craft", "tipo": tipo, "dominio": dominio, "atributo": atributo,
        "tamanho": tamanho, "posicao": posicao,
        "tempo_necessario_s": duracao_s, "tempo_trabalhado_s": 0, "banda": banda,
        "nome_final": nome,
        "descricao_alta": op.get("descricao_alta") or "Um trabalho bem feito.",
        "descricao_baixa": op.get("descricao_baixa") or "Um trabalho malfeito.",
    }
    if extremo:
        bloco["extremo"] = extremo
    extra_fm = {"size": "PP"} if tipo == "location" else None
    corpo = f"{nome} ainda em processo: falta muito para estar pronto."
    peca_id, pasta = trabalho.criar_peca(
        actor_folder.parent, corpo, bloco, name=f"{nome} (em processo)",
        weight_kg=peso_kg, filename=filename, extra_fm=extra_fm)
    trabalho.abrir_sessao(pasta, character_id)
    return True, {
        "peca": peca_id, "tipo": tipo, "materiais": materiais,
        "retomada": False, "concluido": False, "fase": "abertura",
        "dominio": "nenhuma",  # abrir não é prática concluída (mesma regra de forge)
        "memory": _memoria_ator(peca_id, f"Comecei a fazer {nome}.",
                                "craft_start", None)}


def _retomar(character_id, actor_folder, op, present_pecas, pendente):
    """Continuar (ou terminar) um trabalho. NENHUMA chamada ao Árbitro, nunca."""
    peca = op.get("peca")
    narracao = op.get("narracao") or ""
    base = {"peca": peca, "narracao": narracao}
    pasta = present_pecas.get(peca)
    if pasta is None:
        return False, _rejection(base, _fail("peca_inacessivel", item=peca))
    bloco = trabalho.ler(pasta)
    if not bloco:
        # conserto pós-057: a causa REAL de "sem bloco" quase sempre é "já
        # concluiu" (o bloco morre em `encerrar()`), não "é de outro tipo de
        # trabalho" — as duas frases confundiam quem lia (achado da exploração).
        regra = "peca_ja_concluida" if trabalho.origin_de(pasta) == "emergente" \
            else "peca_de_outro_trabalho"
        return False, _rejection(base, _fail(regra, item=peca))
    if bloco.get("tool") != "craft":
        return False, _rejection(base, _fail("peca_de_outro_trabalho", item=peca))
    if pendente is not None and pendente[0] != pasta:
        return False, _rejection(base, _fail("ja_trabalhando"))

    bloco = trabalho.creditar_e_fechar(pasta)
    nome = bloco.get("nome_final") or "Algo"

    if not trabalho.concluido(bloco):
        trabalho.abrir_sessao(pasta, character_id)
        return True, {
            "peca": peca, "retomada": True, "concluido": False, "fase": "retomada",
            "dominio": "nenhuma",
            "memory": _memoria_ator(peca, f"Continuei trabalhando em {nome}.",
                                    "craft_session", None)}

    # CONCLUSÃO
    tipo = bloco.get("tipo") or "item"
    final = banda_final(bloco.get("banda") or "comum", bloco.get("extremo"))
    descricao = (bloco.get("descricao_alta") if final not in ("falha", "comum")
                else bloco.get("descricao_baixa"))
    novo = {"name": nome}
    if tipo == "item":
        tamanho = sanear_tamanho(bloco.get("tamanho"))
        novo["weight_kg"] = fisica.DEFAULT_WEIGHT_BY_SIZE.get(
            tamanho, fisica.DEFAULT_WEIGHT_BY_SIZE["P"])
        novo["size"] = tamanho
    trabalho.encerrar(pasta, novo, descricao or "Algo terminado.")
    # US5: item "com_personagem" só migra da location pro personagem AGORA —
    # peça em processo sempre morou na location (US6, ver nota em `_abrir`).
    if tipo == "item" and bloco.get("posicao") == "com_personagem":
        destino = actor_folder / pasta.name
        if not destino.exists():
            io.move_entity(pasta, destino)
    if tipo == "location":
        # Conserto pós-057: sem a route, a location concluída fica ilhada —
        # ver `_gerar_route_de_acesso`. `pasta` não se move pra location (só
        # item+com_personagem move), então `pasta.parent` continua sendo a
        # location-MÃE de verdade, quem quer que tenha retomado o trabalho.
        _gerar_route_de_acesso(pasta.parent, pasta, nome)

    dominio = bloco.get("dominio") or _DOMINIO
    excepcional = final in ("raro", "lendario")
    evento = ("craft_falha" if final == "falha" else
             "craft_excepcional" if excepcional else "craft")
    content = (f"Terminei {nome}, e saiu melhor do que eu esperava." if excepcional
              else f"Terminei {nome}, mas não presta para nada." if final == "falha"
              else f"Terminei {nome}.")
    return True, {
        "peca": peca, "retomada": True, "concluido": True, "fase": "conclusao",
        "banda": final, "tipo": tipo, "dominio": dominio,
        "memory": _memoria_ator(peca, content, evento,
                                dominio if final != "falha" else None,
                                "medium" if excepcional else "small")}


@registro.handler("craft_ops")
def _h_craft(cid, af, res, rolls):
    applied, rejected = _apply_craft_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator) via react_actor_memory (genérico)
