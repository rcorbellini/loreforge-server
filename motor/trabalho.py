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

from . import io, registro
from .io import read_doc, write_doc, arquivos_em, arquivos_no_mundo

BLOCO = "trabalho"

# spec 053/057: os arquivos de entidade que podem carregar um bloco de trabalho. A
# ordem importa só para o desempate teórico — uma pasta nunca tem mais de um
# (io._scene_entities usa `elif` desde sempre, e o validador passou a afirmar isso).
# `location.md` entrou na spec 057 (craft): o único domínio até aqui capaz de deixar
# um LUGAR (não só item/object) em processo — "construir uma casa" precisa do mesmo
# relógio de ESFORÇO que a lâmina na bigorna já usa, e pôr um relógio próprio dentro
# de `craft/` reabriria o acoplamento lateral que motivou tirar esta primitiva de
# `forja/` desde o início.
_ARQUIVOS = ("item.md", "object.md", "location.md")


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


def origin_de(pasta: Path) -> str | None:
    """`origin` da entidade nesta pasta, seja qual for o tipo (spec 057, conserto
    pós-exploração). Consumidor: `forja`/`craft`, pra distinguir "nunca foi
    peça" de "já foi peça e concluiu" quando `ler()` devolve None — a peça
    concluída (`encerrar()`) perde o bloco `trabalho`, mas continua carregando
    `origin: emergente`; um item qualquer do mundo autoral não. Sinal, não
    prova — uma colheita/abate também é `emergente` sem nunca ter sido peça
    (spec 054/050 não usam `criar_peca`), então a recusa que consome isto MUST
    ler como palpite útil ("provavelmente já terminou"), nunca como certeza."""
    arquivo = _arquivo_de(pasta)
    if arquivo is None:
        return None
    fm, _ = read_doc(arquivo)
    return fm.get("origin")


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
               name: str = "Trabalho em curso", weight_kg: float = 0.3,
               filename: str = "item.md", extra_fm: dict | None = None
               ) -> tuple[str, Path]:
    """Instancia a peça em processo NO LUGAR onde o ato começou.

    Devolve (id, pasta). Passa por `io.create_entity` — mesmo `write_doc`, mesmo
    World Validator, sem atalho (Princípio VI). O `bloco` já vem montado pelo
    domínio: esta primitiva não sabe o que é banda nem prato.

    `filename`/`extra_fm` (spec 057): generaliza para `object.md`/`location.md`
    além do `item.md` default — os seis chamadores existentes não passam nenhum
    dos dois e continuam byte-a-byte iguais. `weight_kg` só entra no frontmatter
    quando a peça é um item (location não pesa; object não pesa hoje); `extra_fm`
    carrega o que só faz sentido por tipo (ex.: `size` obrigatório de location)."""
    tipo = filename.removesuffix(".md")
    peca_id = io.new_id("local" if tipo == "location" else "peca")
    fm = {"type": tipo, "id": peca_id, "name": name, "origin": "emergente",
          BLOCO: dict(bloco)}
    if filename == "item.md":
        fm["weight_kg"] = round(float(weight_kg), 3) or 0.3
    if extra_fm:
        fm.update(extra_fm)
    pasta = io.create_entity(local_folder, peca_id, filename, fm, corpo)
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
    não efeito colateral.

    Varre ITEM, OBJECT e LOCATION (spec 057): até aqui só item tinha `ator` — a
    fonte de fogo (object) nunca prende ninguém (spec 053, sem `ator`). Craft é o
    primeiro domínio a deixar um OBJECT ou uma LOCATION em processo LIGADOS a
    quem o começou (uma prateleira craftada, um cômodo em construção), então o
    escopo de busca generaliza junto."""
    place_folder = actor_folder.parent
    if not place_folder.is_dir():
        return None
    ator_id = io._char_fm(actor_folder).get("id")
    if not ator_id:
        return None
    _, objects, items = io._scene_entities(place_folder)
    pastas = list(items.values()) + list(objects.values()) \
        + list(pecas_location_em(place_folder).values())
    for pasta in pastas:
        bloco = ler(pasta)
        if not bloco or bloco.get("ator") != ator_id:
            continue
        if apenas_prazo and not por_prazo(bloco):
            continue
        if sessao_aberta(bloco):
            return pasta, bloco
    return None


def pecas_location_em(place_folder: Path) -> dict[str, Path]:
    """`location.md` FILHAS de `place_folder` com bloco `trabalho` — id -> pasta.

    `io._scene_entities` não anda por `location.md` (aninhamento não é "presença
    na cena" do mesmo jeito que item/object/character são — é topologia, spec
    035). Uma location EM CONSTRUÇÃO ainda não é um lugar de verdade (ninguém
    "entra" nela), então quem trabalha nela continua fisicamente na location
    PAI — é de lá que `peca_pendente_de`/a retomada de craft precisam enxergá-la.
    Varredura RASA (só filhos diretos): craft só cria subpasta de primeiro nível
    (Decisão do executor, US5) — não há caso de location-em-processo mais funda."""
    achadas: dict[str, Path] = {}
    if not place_folder.is_dir():
        return achadas
    for child in place_folder.iterdir():
        if not child.is_dir():
            continue
        arquivo = child / "location.md"
        if not arquivo.exists():
            continue
        fm, _ = read_doc(arquivo)
        if fm.get("id") and BLOCO in fm:
            achadas[fm["id"]] = child
    return achadas


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
            _testemunhar_conclusao_prazo(bloco, pasta)


def esforco_pronto(bloco: dict) -> bool:
    """Peça de ESFORÇO cujo tempo já cobre o que falta — o critério da
    resolução preguiçosa de esforço (revisão pós-057), espelhando `concluido()`
    mas sem exigir que a sessão já tenha sido fechada por uma retomada.

    Dois jeitos de estar pronta: (a) já fechada e com `tempo_trabalhado_s`
    suficiente (`concluido(bloco)` — pode ter vindo de uma interrupção, ver
    `apply_op`), ou (b) AINDA aberta, mas o tempo real decorrido desde
    `trabalhando_desde` já cobre `restante_s` — o mesmo cálculo que
    `creditar_e_fechar` faria, só que sem mutar nada (a mutação de verdade é
    responsabilidade de quem chama, via retomada sintética)."""
    if por_prazo(bloco):
        return False
    if concluido(bloco):
        return True
    desde = bloco.get("trabalhando_desde")
    if not desde:
        return False
    return (time.time() - desde) >= restante_s(bloco)


def pendentes_de_esforco() -> list[tuple[Path, dict]]:
    """Peças de ESFORÇO prontas pra concluir — mesma varredura mundial de
    `vencidas_por_prazo`, critério diferente (tempo ACUMULADO, não uma data)."""
    out = []
    for nome in _ARQUIVOS:
        for arquivo in io.arquivos_no_mundo(nome):
            fm, _ = read_doc(arquivo)
            bloco = fm.get(BLOCO)
            if isinstance(bloco, dict) and esforco_pronto(bloco):
                out.append((arquivo.parent, bloco))
    return out


def resolver_esforco_pendente() -> None:
    """A conclusão PREGUIÇOSA do relógio de ESFORÇO (revisão pós-057) — molde
    de `resolver_vencidas()`, mas sem reinventar a conclusão: monta uma
    RETOMADA SINTÉTICA (`{"peca": id, "narracao": "", "retomada": True}`) e
    despacha pelo MESMO canal que uma retomada de verdade usaria
    (`registro.get(bloco["tool"] + "_ops")`, via `turno.apply_op` — a porta
    única). Mover pro personagem, gerar rota de location, creditar o domínio
    certo na memória: tudo isso já mora em `craft`/`forja`, e continua lá —
    esta função só decide QUANDO chamar o que já existe (Princípio XII: a
    resolução é operação do dono do bloco, não de um domínio irmão, nem desta
    primitiva).

    Import de `turno` é LOCAL (mesma razão de `memoria`, acima): `motor/turno.py`
    importa este módulo no topo (pro gate de interrupção), e o oposto no topo
    fecharia ciclo."""
    from . import turno
    with io.WRITE_LOCK:
        for pasta, bloco in pendentes_de_esforco():
            ator_id = bloco.get("ator")
            canal = f"{bloco.get('tool')}_ops"
            if not ator_id or registro.get(canal) is None:
                continue
            try:
                actor_folder = io.find_character_folder(ator_id)
            except io.MotorError:
                continue
            turno.apply_op(ator_id, canal,
                           {"peca": pasta.name, "narracao": "", "retomada": True},
                           actor_folder=actor_folder)


# spec 053: a frase do desfecho é do MOTOR, fixa por tool — não do Árbitro. `cook` já
# fazia assim ("o prato que estava no fogo ficou pronto"); só ganhou vizinhos.
_FATO_POR_TOOL = {
    "cook": "o prato que estava no fogo ficou pronto",
    "kindle_fire": "o fogo que ardia aqui se apagou",
    # spec 054: a ÚNICA linha de código que `forage` acrescenta a esta primitiva
    # compartilhada — o resultado que a rebrota restaura é o TEXTO ANTIGO do
    # alvo (sentido invertido de cook/kindle_fire, que gravam o resultado NOVO),
    # mas a frase do desfecho segue a MESMA convenção: fixa do Motor.
    "forage": "o que foi colhido aqui voltou a crescer",
    # spec 055: a ÚNICA linha de código que `brew` acrescenta a esta primitiva
    # compartilhada — molde EXATO de `cook`, sentido DIRETO (o resultado já É o
    # remédio final, ao contrário de `forage`, que grava o resultado ANTIGO).
    "brew": "o preparo que descansava no recipiente ficou pronto",
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


# spec 057 (US4, Mecanismo B): qual evento de testemunha cada `tool` de PRAZO
# gera na CONCLUSÃO — só `cook`/`brew` (têm ator, conferem posse via
# `_DONO_EVENTOS`). `kindle_fire` fica de fora: acender já é o ato observável
# (Mecanismo A, na abertura); apagar não é um evento novo de interesse
# (FR-020/FR-021 da spec — fogo nunca confere posse).
_EVENTO_PRAZO_POR_TOOL = {"cook": "cook_concluido", "brew": "brew_concluido"}


def _testemunhar_conclusao_prazo(bloco: dict, pasta: Path) -> None:
    """O lado de TESTEMUNHA da conclusão preguiçosa (Mecanismo B).

    Por que este hook precisa existir, separado de `_notificar`: a conclusão de
    PRAZO nunca passa pelo pipeline de `Fato` (`resolver_proposta` → `react_witness`)
    — `resolver_vencidas` roda de dentro de uma CONSULTA (`get_context`), não de
    uma mutação de tool. `_WITNESS_CANAIS`/`react_witness` só despacham `Fato`s
    que esse pipeline produz; sem este hook, a conclusão de `cook`/`brew` seria
    testemunhada por NINGUÉM, para sempre — só a abertura (essa sim, um tool call
    comum) alimentaria `dono()`.

    Import de `memoria` é LOCAL (não no topo do módulo) para não fechar um ciclo:
    `motor/memoria/executores.py` já importa `trabalho` no nível do módulo."""
    chave = _EVENTO_PRAZO_POR_TOOL.get(bloco.get("tool"))
    ator = bloco.get("ator")
    if not chave or not ator:
        return
    from . import memoria
    chars, _, _ = io._scene_entities(pasta.parent)
    if not chars:
        return
    ator_folder = chars.get(ator)
    memoria._record_witness(ator, ator_folder, chars,
                            {chave: [{"peca_id": pasta.name}]})


def vencidas_por_prazo() -> list[tuple[Path, dict]]:
    """Peças de PRAZO cujo tempo se cumpriu — a varredura da resolução preguiçosa
    (`cozinha.lazy_evaluate`). Só PRAZO: ESFORÇO conclui num ato, nunca na trilha
    de leitura do mundo (spec 052, FR-021/FR-049)."""
    out = []
    for nome in _ARQUIVOS:          # spec 053: object também tem prazo (a fonte de fogo)
        for arquivo in io.arquivos_no_mundo(nome):
            fm, _ = read_doc(arquivo)
            bloco = fm.get(BLOCO)
            if not isinstance(bloco, dict) or not por_prazo(bloco):
                continue
            if concluido(bloco):
                out.append((arquivo.parent, bloco))
    return out
