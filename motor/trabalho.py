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

# spec 053: os arquivos de entidade que podem carregar um bloco de trabalho. A ordem
# importa só para o desempate teórico — uma pasta nunca tem os dois (io._scene_entities
# usa `elif` desde sempre, e o validador passou a afirmar isso).
_ARQUIVOS = ("item.md", "object.md")


def _arquivo_de(pasta: Path) -> Path | None:
    """O `.md` de entidade desta pasta, seja qual for o tipo (spec 053).

    POR QUE ISTO PRECISOU EXISTIR. A primitiva nasceu na forja e na cozinha, onde
    toda peça em processo era um ITEM — e por isso cinco funções abriam `item.md`
    direto. A primeira coisa do projeto que se transforma no tempo SEM ser portátil
    (uma fonte de fogo, spec 053) não cabia em nenhuma delas. Generalizar aqui é o
    que o Princípio XII manda: o reuso mora na primitiva, e uma segunda primitiva
    para o mesmo relógio seria a duplicação que tirar `trabalho` de dentro de
    `forja/` já tinha evitado uma vez."""
    for nome in _ARQUIVOS:
        arquivo = pasta / nome
        if arquivo.exists():
            return arquivo
    return None


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #

def ler(item_folder: Path) -> dict | None:
    """O bloco de trabalho de uma peça em processo, ou None se não for uma.

    É o RECONHECEDOR estrutural (spec 052, FR-011): a retomada sabe que o alvo é
    uma peça olhando o arquivo, sem gastar uma única chamada de LLM."""
    arquivo = _arquivo_de(item_folder)
    if arquivo is None:
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
    arquivo = _arquivo_de(item_folder)
    if arquivo is None:
        return
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
    arquivo = _arquivo_de(item_folder)
    if arquivo is None:
        return
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


def resolver_vencidas() -> None:
    """A resolução PREGUIÇOSA de todo prazo do mundo (spec 053).

    Antes morava em `cozinha._resolve_pratos`, e isso era uma bomba-relógio: aquela
    função iterava `vencidas_por_prazo()` — que devolve TODAS as peças de prazo, não
    só as de `cook` — e lia `bloco["prato"]`. No dia em que outro domínio usasse o
    mesmo relógio, sua peça seria renomeada para "Prato", com o corpo "Um prato
    preparado.", em silêncio. Trazer para cá é o Princípio XII: a resolução do prazo
    é operação do dono do bloco, não de um domínio irmão.

    Genérica de verdade — não conhece tool nenhuma. Lê `resultado`, transforma, e
    marca extinto se pedirem. `prato` é aceito como sinônimo de leitura por uma
    versão, para o mundo em voo não perder nada.
    """
    with io.WRITE_LOCK:
        for pasta, bloco in vencidas_por_prazo():
            r = bloco.get("resultado") or bloco.get("prato") or {}
            nome = r.get("nome") or "Trabalho terminado"
            encerrar(pasta, {"name": nome},
                     r.get("description") or "Algo que ficou pronto.")
            if r.get("extinto"):
                io.marcar_extinto(pasta)
            _notificar(bloco, pasta, r)


# spec 053: a frase do desfecho é do MOTOR, fixa por tool — não do Árbitro. `cook` já
# fazia assim ("o prato que estava no fogo ficou pronto"); só ganhou vizinhos.
_FATO_POR_TOOL = {
    "cook": "o prato que estava no fogo ficou pronto",
    "kindle_fire": "o fogo que ardia aqui se apagou",
}


def _notificar(bloco: dict, pasta: Path, resultado: dict) -> None:
    """Princípio X: o efeito precisa CHEGAR a quem viveu.

    COM `ator` (cook, forja) avisa só ele — é dele o trabalho. SEM `ator` (a fonte de
    fogo, que não ocupa ninguém) avisa QUEM ESTÁ NO LUGAR: sem isto o apagamento
    seria absolutamente mudo, e o canal ficaria com dois dos três passos do
    Princípio X. `status.action` é o canal de sempre — transitório, lido pela
    narração do momento seguinte, sem tocar em memória."""
    fato = resultado.get("fato") or _FATO_POR_TOOL.get(bloco.get("tool")) \
        or "algo que estava em curso aqui terminou"
    ator = bloco.get("ator")
    if ator:
        try:
            alvos = [io.find_character_folder(ator)]
        except Exception:
            return
    else:
        chars, _, _ = io._scene_entities(pasta.parent)
        alvos = list(chars.values())
    for char_folder in alvos:
        arquivo = char_folder / "character.md"
        if not arquivo.exists():
            continue
        fm, body = read_doc(arquivo)
        status = dict(fm.get("status") or {})
        status["action"] = fato
        fm["status"] = status
        write_doc(arquivo, fm, body)


def vencidas_por_prazo() -> list[tuple[Path, dict]]:
    """Peças de PRAZO cujo tempo se cumpriu — a varredura da resolução preguiçosa
    (`cozinha.lazy_evaluate`). Só PRAZO: ESFORÇO conclui num ato, nunca na trilha
    de leitura do mundo (spec 052, FR-021/FR-049)."""
    out = []
    for nome in _ARQUIVOS:          # spec 053: object também tem prazo (a fonte de fogo)
        for arquivo in io.WORLD_DIR.rglob(nome):
            fm, _ = read_doc(arquivo)
            bloco = fm.get(BLOCO)
            if not isinstance(bloco, dict) or not por_prazo(bloco):
                continue
            if concluido(bloco):
                out.append((arquivo.parent, bloco))
    return out
