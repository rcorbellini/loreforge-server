"""O Motor / trabalho (spec 052) — A PEÇA EM PROCESSO, entidade compartilhada.

Um ato que não termina no turno em que começa deixa uma COISA no mundo — uma
lâmina na bigorna, uma panela no fogo — e não um campo escondido no personagem.
Esta primitiva é essa coisa.

Por que mora aqui e não em `forja/` nem em `cozinha/`: as DUAS a usam. Pôr em
`forja/` obrigaria `cozinha/` a importar de um domínio irmão (acoplamento lateral
que o projeto não tem em lugar nenhum); pôr em `cozinha/` seria pior ainda, porque
quem criou o mecanismo não é quem o generaliza. É primitiva de Runtime, no mesmo
nível de `io`/`rolagem`/`registro` — e é onde o Princípio XII manda o reuso morar.

OS DOIS RELÓGIOS (spec 052, FR-048/049) — a distinção é deliberada, e forçar um no
outro estragaria os dois:

  ESFORÇO (`forge_*`)  o tempo só corre enquanto alguém trabalha; é creditado por
                       sessão; conclui num ATO. Campos: `tempo_necessario_s`,
                       `tempo_trabalhado_s`, `trabalhando_desde`.
  PRAZO   (`cook`)     o tempo corre sozinho, ninguém precisa estar presente;
                       conclui na consulta ao mundo. Campo: `pronto_ts`.

**O campo presente diz qual relógio vale** — não existe enum de modo nem máquina de
estados. É `pronto_ts` ou é `tempo_necessario_s`; nunca os dois.

NÍVEL 0: sem turno, sem LLM, sem conhecer tool nenhuma.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import io
from .io import read_doc, write_doc

BLOCO = "trabalho"


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #

def ler(item_folder: Path) -> dict | None:
    """O bloco de trabalho de uma peça em processo, ou None se não for uma.

    É o RECONHECEDOR estrutural (spec 052, FR-011): a retomada sabe que o alvo é
    uma peça olhando o arquivo, sem gastar uma única chamada de LLM."""
    arquivo = item_folder / "item.md"
    if not arquivo.exists():
        return None
    fm, _ = read_doc(arquivo)
    bloco = fm.get(BLOCO)
    return bloco if isinstance(bloco, dict) else None


def por_esforco(bloco: dict) -> bool:
    """Relógio de ESFORÇO? (só avança com alguém presente)"""
    return "tempo_necessario_s" in bloco


def por_prazo(bloco: dict) -> bool:
    """Relógio de PRAZO? (corre sozinho)"""
    return "pronto_ts" in bloco


def sessao_aberta(bloco: dict) -> bool:
    """Há alguém na bigorna agora? Peça de PRAZO está sempre 'em curso' até
    vencer — o fogo não larga o serviço."""
    if por_prazo(bloco):
        return True
    return bool(bloco.get("trabalhando_desde"))


def concluido(bloco: dict) -> bool:
    """O trabalho se cumpriu? (não materializa nada — só responde)"""
    if por_prazo(bloco):
        return time.time() >= (bloco.get("pronto_ts") or 0)
    return (bloco.get("tempo_trabalhado_s") or 0) >= (bloco.get("tempo_necessario_s") or 0)


def restante_s(bloco: dict) -> float:
    """Quanto de trabalho ainda falta, em segundos. Nunca negativo."""
    if por_prazo(bloco):
        return max(0.0, (bloco.get("pronto_ts") or 0) - time.time())
    return max(0.0, (bloco.get("tempo_necessario_s") or 0)
               - (bloco.get("tempo_trabalhado_s") or 0))


# --------------------------------------------------------------------------- #
# Escrita
# --------------------------------------------------------------------------- #

def criar_peca(local_folder: Path, corpo: str, bloco: dict,
               name: str = "Trabalho em curso", weight_kg: float = 0.3) -> tuple[str, Path]:
    """Instancia a peça em processo NO LUGAR onde o ato começou.

    Devolve (id, pasta). Passa por `io.create_entity` — mesmo `write_doc`, mesmo
    World Validator, sem atalho (Princípio VI). O `bloco` já vem montado pelo
    domínio: esta primitiva não sabe o que é banda nem prato."""
    peca_id = io.new_id("peca")
    pasta = io.create_entity(local_folder, peca_id, "item.md", {
        "type": "item", "id": peca_id, "name": name,
        "weight_kg": round(float(weight_kg), 3) or 0.3,
        "origin": "emergente",
        BLOCO: dict(bloco),
    }, corpo)
    return peca_id, pasta


def _grava_bloco(item_folder: Path, bloco: dict) -> None:
    arquivo = item_folder / "item.md"
    fm, body = read_doc(arquivo)
    fm[BLOCO] = bloco
    write_doc(arquivo, fm, body)


def abrir_sessao(item_folder: Path, ator_id: str) -> dict:
    """Põe alguém na bigorna. Só faz sentido no relógio de ESFORÇO."""
    bloco = dict(ler(item_folder) or {})
    bloco["trabalhando_desde"] = time.time()
    bloco["ator"] = ator_id
    _grava_bloco(item_folder, bloco)
    return bloco


def creditar_e_fechar(item_folder: Path) -> dict:
    """Fecha a sessão aberta e credita o tempo efetivamente trabalhado.

    **O CLAMP É A LINHA QUE IMPORTA** (spec 052, FR-016): credita
    `min(decorrido, o que ainda faltava)`. Sem ele, uma peça largada por três dias
    na bigorna creditaria três dias de trabalho e sairia pronta de graça. Com ele,
    nenhuma sessão pode creditar mais do que o bloco a que se comprometeu — a peça
    esquecida simplesmente conclui, nunca ganha qualidade por ter esperado."""
    bloco = dict(ler(item_folder) or {})
    desde = bloco.get("trabalhando_desde")
    if not desde or por_prazo(bloco):
        return bloco
    creditado = min(max(0.0, time.time() - desde), restante_s(bloco))
    bloco["tempo_trabalhado_s"] = round((bloco.get("tempo_trabalhado_s") or 0) + creditado, 3)
    bloco.pop("trabalhando_desde", None)
    _grava_bloco(item_folder, bloco)
    return bloco


def atualizar(item_folder: Path, **campos) -> dict:
    """Mescla campos no bloco (a catraca da banda usa isto)."""
    bloco = dict(ler(item_folder) or {})
    bloco.update(campos)
    _grava_bloco(item_folder, bloco)
    return bloco


def encerrar(item_folder: Path, fm_novo: dict, corpo: str) -> None:
    """A peça deixa de ser peça: o bloco SAI INTEIRO e o item vira o que foi feito.

    Item pronto não carrega estado de trabalho (invariante 2 do contrato)."""
    arquivo = item_folder / "item.md"
    fm, _ = read_doc(arquivo)
    fm.update(fm_novo)
    fm.pop(BLOCO, None)
    write_doc(arquivo, fm, corpo)


# --------------------------------------------------------------------------- #
# Consultas de cena
# --------------------------------------------------------------------------- #

def peca_pendente_de(actor_folder: Path, *, apenas_prazo: bool = False) -> tuple[Path, dict] | None:
    """A peça em processo, NA CENA do ator, com o relógio ligado a ele.

    Escopo é a CENA, nunca o mundo (spec 052, R8): esta função roda em TODO
    executor, então uma varredura global seria um custo por ação. E o escopo curto
    é o certo, não só o barato — quem cozinha não pode se deslocar (o próprio gate
    impede), e quem forja com sessão aberta está na bigorna. Se alguém levar a peça
    para outro lugar, o ator deixa de estar ocupado: é o comportamento desejado,
    não efeito colateral."""
    place_folder = actor_folder.parent
    if not place_folder.is_dir():
        return None
    ator_id = io._char_fm(actor_folder).get("id")
    if not ator_id:
        return None
    _, _, items = io._scene_entities(place_folder)
    for pasta in items.values():
        bloco = ler(pasta)
        if not bloco or bloco.get("ator") != ator_id:
            continue
        if apenas_prazo and not por_prazo(bloco):
            continue
        if sessao_aberta(bloco):
            return pasta, bloco
    return None


def is_busy(actor_folder: Path) -> bool:
    """Nível 0 (spec 052, molde EXATO de `is_resting`): a ÚNICA definição de "está
    ocupado, não pode fazer outra coisa" no código. Substitui `fisica.is_cooking`,
    que lia um campo do personagem — o fato passou a morar na PEÇA, e a ocupação é
    DERIVADA dela. Quem precisa bloquear uma ação CHAMA esta função na própria
    validação; nunca um hook central.

    **SÓ PRAZO TRAVA**, e a distinção é o desenho inteiro desta spec, não um
    detalhe. Quem cozinha está ESPERANDO o fogo: não há o que fazer senão esperar,
    e é por isso que `cook` sempre travou tudo. Quem forja está TRABALHANDO: largar
    a peça e fazer outra coisa não é uma ação proibida, é simplesmente sair da
    bigorna — a sessão fica aberta, e a próxima martelada credita o que foi feito,
    com o clamp impedindo que a espera vire trabalho.

    Se ESFORÇO travasse como PRAZO, o gate cosmético de manifesto esconderia todas
    as tools de mutação do ferreiro — inclusive a própria tool de RETOMAR. Ele
    ficaria preso à peça sem poder terminá-la."""
    return peca_pendente_de(actor_folder, apenas_prazo=True) is not None


def vencidas_por_prazo() -> list[tuple[Path, dict]]:
    """Peças de PRAZO cujo tempo se cumpriu — a varredura da resolução preguiçosa
    (`cozinha.lazy_evaluate`). Só PRAZO: ESFORÇO conclui num ato, nunca na trilha
    de leitura do mundo (spec 052, FR-021/FR-049)."""
    out = []
    for arquivo in io.WORLD_DIR.rglob("item.md"):
        fm, _ = read_doc(arquivo)
        bloco = fm.get(BLOCO)
        if not isinstance(bloco, dict) or not por_prazo(bloco):
            continue
        if concluido(bloco):
            out.append((arquivo.parent, bloco))
    return out
