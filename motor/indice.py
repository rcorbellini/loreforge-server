"""O Motor / indice (spec 063) — o GRAFO DERIVADO do disco. NÍVEL 0.

O mundo JÁ é um grafo: ≈7 000 arestas declaradas em frontmatter (`involved`, `about`,
`ouvido_de`, `from`/`to`, `prerequisites`), mais a contenção, que é o aninhamento de
pastas. O que faltava era travessia REVERSA — tudo estava guardado numa direção só
(memória → entidade) e percorrido na outra por força bruta.

Este módulo NÃO acrescenta nada ao mundo. Ele torna barato de atravessar o que já está
declarado, nos dois sentidos.

NÍVEL 0 (primitiva): NÃO importa nenhum outro módulo do Motor — só `frontmatter` e
`validator`. É o que mantém o grafo de dependências do pacote um DAG (spec 021), e a
fase 38 reprova quem quebrar. A raiz do mundo VEM POR PARÂMETRO (`garantir(raiz)`)
justamente para não precisar importar `io.WORLD_DIR`.

O CONTRATO, em duas frases:

  1. O `.md` é a fonte da verdade. O índice é derivado, vive em memória e NUNCA é
     persistido. Apagá-lo é impossível porque não existe em disco; desligá-lo
     (`LOREFORGE_SEM_INDICE=1`) deixa o jogo idêntico, só mais devagar.
  2. O índice entrega ARESTA CRUA. O CORTE é de quem pergunta. Não existe, e não pode
     passar a existir, `memorias_vivas_de(x)` aqui — porque "viva" não é propriedade da
     aresta: `familiarity_with` precisa das vencidas (pesam ¼), `recognizes_route`
     precisa delas (é a razão dela existir) e `get_context` não pode vê-las. Um filtro
     aqui apagaria as três distinções de uma vez.

COERÊNCIA (research R1/R4). O índice é WRITE-THROUGH pelas cinco primitivas mutadoras de
`io.py` (`write_doc`, `rewrite_description`, `move_entity`, `remove_entity`,
`create_entity`), dentro do WRITE_LOCK que elas já tomam. Isso é o que o distingue de um
MEMO, e a distinção é a razão de esta spec existir:

    memo de requisição (rejeitado no item 63 §3.4)  |  índice write-through
    envelhece a cada escrita, em silêncio           |  a escrita o atualiza
    op 2 NÃO vê a escrita da op 1  <- o defeito     |  op 2 vê (mesma seção crítica)

Escrita EXTERNA (edição à mão, `git checkout`, `submodule update`) não passa pelas cinco
portas — para essa há `garantir()`, que revalida por `mtime` (21 ms para 3 151 arquivos)
e é chamada UMA VEZ na fronteira da requisição, nunca por leitura.

Se um caminho de escrita novo nascer fora de `io.py`, o índice diverge em silêncio — o
modo de falha que o item 63 §3.1 nomeia. Contra isso há duas defesas, e as duas são
entregáveis: a fase 62 (lê o fonte e reprova varredura/escrita nova) e a suíte rodando
nos DOIS modos, com e sem índice. Discordando os dois, o disco ganha.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import frontmatter


# Duplicado de `io.ENTITY_FILENAMES` de propósito — o mesmo padrão que
# `intencoes._INTENTION_STATUSES` (duplica `validator.INTENTION_STATES`) e
# `memoria._MEMORY_INTENSITIES` já usam. Importar `io` daqui criaria o ciclo que o
# nível 0 existe para evitar, e a lista é estável desde a spec 001.
ENTITY_FILENAMES = ("location.md", "character.md", "route.md", "item.md", "object.md")


# As arestas de FATO lidas do frontmatter: campo -> nome da aresta. O valor pode ser
# um id ou uma lista de ids; ambos viram arestas.
#
# `ouvido_de` está aqui e é FATO — de propósito, e é a guarda estrutural do Invariante 11
# ("secreto até do Árbitro"). Mecânica social atravessa CRENÇA, e crença sai de `envolve`.
# Ninguém pede `reverso(x, "ouviu_de")` sem estar escrevendo uma capacidade de revelação,
# que é uma decisão consciente e revisável — não um acidente de travessia genérica.
_ARESTAS_FM = {
    "involved": "envolve",
    "about": "sobre",
    "ouvido_de": "ouviu_de",
    "from": "rota_de",
    "to": "rota_para",
    "prerequisites": "pre_requisito",
    "memoria_id": "memoria_de",
    "intention_id": "intencao_de",
}


_LOCK = threading.RLock()
_ESTADO: "_Estado | None" = None
_RAIZ: Path | None = None

# Ids atrás dos quais já revalidamos o mundo inteiro sem achar nada. Zerado a cada
# revalidação bem-sucedida — ver `caminhos_de`.
_MISS_CURADO: set = set()

# A ÉPOCA: avança a cada escrita pelas portas e a cada revalidação de fronteira. É o
# que deixa a recusa de duplicata olhar o disco uma vez por turno em vez de por chamada.
_EPOCA = 0
_EPOCA_SINCRONIZADA = -1


class No:
    """Um nó do grafo: uma entidade do mundo que já tem `id`. Nenhum nó é criado aqui."""

    __slots__ = ("id", "tipo", "caminho", "fm", "body", "mtime_ns", "arquivo")

    def __init__(self, id, tipo, caminho, fm, body, mtime_ns, arquivo):
        self.id = id
        self.tipo = tipo
        self.caminho = caminho      # a PASTA da entidade (para memória/intenção: a pasta que a contém)
        self.fm = fm
        self.body = body
        self.mtime_ns = mtime_ns
        self.arquivo = arquivo      # o `.md` em si


class _Estado:
    __slots__ = ("nos", "por_caminho", "por_tipo", "pai", "filhos",
                 "arestas", "reverso", "pasta_de_entidade", "por_arquivo",
                 "por_pasta", "por_nome", "sujos", "mtime_pasta")

    def __init__(self):
        self.nos = {}                  # id -> No   (só o PRIMEIRO; duplicata vive em por_caminho)
        self.por_caminho = {}          # str(arquivo) -> No
        self.por_tipo = {}             # tipo -> [ids]
        self.pai = {}                  # id -> id | None
        self.filhos = {}               # id -> [ids]
        self.arestas = {}              # (id, tipo_aresta) -> [ids]
        self.reverso = {}              # (id, tipo_aresta) -> [ids]
        self.pasta_de_entidade = {}    # str(pasta) -> id
        # (nome_do_arquivo, id) -> [Path]. É o que torna `caminhos_de` uma busca por
        # chave em vez de varrer os 3 150 nós: 0,286 ms -> microssegundos. A LISTA é o
        # ponto — id duplicado guarda os dois caminhos, e quem chama é que recusa.
        self.por_arquivo = {}
        # str(pasta) -> [Path]: os `.md` DIRETAMENTE numa pasta. Substitui
        # `sorted(mem_dir.glob("*.md"))`, que é o padrão mais repetido do Motor
        # (15 sítios) e o mais caro em quem tem muita memória.
        self.por_pasta = {}
        # nome do arquivo -> [Path]: substitui `WORLD_DIR.rglob("route.md")` e irmãos.
        self.por_nome = {}
        # Listas que ganharam item e ainda não foram reordenadas. A ORDEM importa —
        # os chamadores faziam `sorted(...)` e a saída deles depende dela — mas
        # reordenar a cada leitura custava caro: comparar `Path` passa por
        # `_parts_normcase`, e ordenar as 804 memórias da Mira 238 vezes por face
        # somava mais de um segundo. Ordena-se uma vez, na primeira leitura depois de
        # uma mudança.
        self.sujos = set()
        # str(pasta) -> mtime_ns do DIRETÓRIO. É a chave de invalidação da contenção:
        # criar, apagar ou renomear um arquivo muda o mtime da pasta que o contém.
        # Um stat de diretório substitui os 804 stats de arquivo que a conferência de
        # existência custava — e ainda apanha arquivo NOVO, que antes só `garantir()`
        # via.
        self.mtime_pasta = {}


# --------------------------------------------------------------------------- #
# Liga/desliga (FR-010) — a alternativa "apenas .md" continua no código, e testada
# --------------------------------------------------------------------------- #

def ativo() -> bool:
    """False no modo sem índice. Todo consumidor migrado mantém o caminho de disco
    vivo atrás deste teste — é ele que faz a suíte poder rodar duas vezes, e é a
    defesa estrutural contra a divergência índice↔disco."""
    return os.environ.get("LOREFORGE_SEM_INDICE") != "1"


# --------------------------------------------------------------------------- #
# Construção e revalidação
# --------------------------------------------------------------------------- #

def _copia(valor):
    """Cópia profunda de um frontmatter. Especializada de propósito.

    A `deepcopy` da stdlib é genérica: carrega memo, `id()`, `_keep_alive` e despacho por
    tipo, e num perfil da face do Coppo aparecia como 34 s de 110 s — o maior item
    isolado, depois que o índice já tinha tirado o parse do caminho. Frontmatter é
    JSON-ish (dict, list, escalares), então a versão especializada é **4,7× mais barata**
    (0,96 µs contra 4,57 µs por documento), com equivalência conferida em 400 documentos
    reais.

    `type(v) is dict` em vez de `isinstance`: subclasse de dict não aparece em
    frontmatter parseado, e a checagem exata é mais rápida.
    """
    if type(valor) is dict:
        return {k: _copia(v) for k, v in valor.items()}
    if type(valor) is list:
        return [_copia(v) for v in valor]
    return valor


def _ids_de(valor) -> list:
    if isinstance(valor, str):
        return [valor] if valor else []
    if isinstance(valor, (list, tuple)):
        return [v for v in valor if isinstance(v, str) and v]
    return []


def _indexar_arquivo(est: _Estado, arquivo: Path, raiz: Path) -> No | None:
    """Lê um `.md` e insere/atualiza o nó. Devolve o nó, ou None se não é entidade."""
    try:
        st = arquivo.stat()
        fm, body = frontmatter.split(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(fm, dict):
        return None
    eid = fm.get("id")
    if not eid or not isinstance(eid, str):
        return None

    # A PASTA da entidade: para `character.md`/`item.md`/... é a pasta que o contém;
    # para memória/intenção (`memories/mem-x.md`) o nó não tem pasta própria — a dele
    # é a do dono, que é quem responde `pai`.
    if arquivo.name in ENTITY_FILENAMES:
        pasta = arquivo.parent
        est.pasta_de_entidade[str(pasta)] = eid
    else:
        pasta = arquivo.parent

    no = No(eid, fm.get("type"), pasta, fm, body, st.st_mtime_ns, arquivo)
    est.por_caminho[str(arquivo)] = no
    # `nos` guarda o primeiro; a duplicata é detectada por `caminhos_de`, que varre
    # `por_caminho` — assim `find_character_folder` mantém a recusa alta que já tem.
    est.nos.setdefault(eid, no)
    est.por_tipo.setdefault(no.tipo, []).append(eid)
    est.por_arquivo.setdefault((arquivo.name, eid), []).append(arquivo)
    est.por_pasta.setdefault(str(arquivo.parent), []).append(arquivo)
    est.por_nome.setdefault(arquivo.name, []).append(arquivo)
    est.sujos.add(("pasta", str(arquivo.parent)))
    est.sujos.add(("nome", arquivo.name))
    # NÃO carimbar aqui o `mtime` da pasta. A primeira versão carimbava, para que uma
    # pasta criada em runtime entrasse na vigilância — e o efeito foi o oposto: indexar
    # UM arquivo marcava a pasta INTEIRA como sincronizada, mascarando deleções
    # anteriores que ainda não tinham sido reconciliadas. As fases 19, 20 e 58 caíram
    # com `FileNotFoundError` por isso.
    #
    # Pasta desconhecida é o estado CERTO: `_sincronizar_pasta` trata `None != mtime`
    # como "nunca sincronizada" e lista de verdade, uma vez, e só então carimba.
    return no


def _pai_de(arquivo: Path, raiz: Path, pasta_de_entidade: dict) -> str | None:
    """A entidade que CONTÉM esta — subindo pastas até achar uma que seja entidade.

    É a aresta `dentro_de`, e ela é a espinha: hoje o aninhamento de pastas É a
    topologia (Invariante 3). Para `X/character.md` o pai é a entidade acima de `X`;
    para `X/memories/mem.md` o pai é `X` (a pasta `memories/` não é entidade).
    """
    if arquivo.name in ENTITY_FILENAMES:
        atual = arquivo.parent.parent
    else:
        atual = arquivo.parent
    while True:
        eid = pasta_de_entidade.get(str(atual))
        if eid is not None:
            return eid
        if atual == raiz or atual.parent == atual:
            return None
        atual = atual.parent


def _ligar(est: _Estado, raiz: Path) -> None:
    """Monta contenção e arestas de frontmatter, com reverso. Roda depois de todos os
    nós existirem — `pasta_de_entidade` precisa estar completa para `_pai_de` acertar."""
    est.pai.clear()
    est.filhos.clear()
    est.arestas.clear()
    est.reverso.clear()
    for no in est.por_caminho.values():
        pid = _pai_de(no.arquivo, raiz, est.pasta_de_entidade)
        if pid == no.id:
            pid = None
        est.pai[no.id] = pid
        if pid is not None:
            est.filhos.setdefault(pid, []).append(no.id)
        for campo, tipo in _ARESTAS_FM.items():
            for alvo in _ids_de(no.fm.get(campo)):
                if alvo == no.id:
                    continue
                est.arestas.setdefault((no.id, tipo), []).append(alvo)
                est.reverso.setdefault((alvo, tipo), []).append(no.id)


def _construir(raiz: Path) -> _Estado:
    est = _Estado()
    for arquivo in raiz.rglob("*.md"):
        if arquivo.name == "README.md":
            continue
        _indexar_arquivo(est, arquivo, raiz)
    _ligar(est, raiz)
    return est


def garantir(raiz: Path | None = None) -> None:
    """Constrói o índice se não existe; revalida por `mtime` se existe.

    CHAMADA UMA VEZ na fronteira da requisição — nunca por leitura. Custo medido:
    construir 254 ms (cache de página quente) / 16,5 s (disco frio, uma vez por boot da
    MÁQUINA, não do server); revalidar 21 ms para 3 151 arquivos.

    A revalidação é o que apanha escrita externa (edição à mão, `git checkout`,
    `submodule update`) — o que não passou pelas cinco portas de `io.py`.
    """
    global _ESTADO, _RAIZ, _EPOCA
    _EPOCA += 1
    if not ativo():
        return
    if raiz is not None:
        raiz = Path(raiz)
    with _LOCK:
        if raiz is not None and raiz != _RAIZ:
            _RAIZ = raiz
            _ESTADO = None
        if _RAIZ is None:
            return
        if _ESTADO is None:
            _ESTADO = _construir(_RAIZ)
            _MISS_CURADO.clear()
            return
        # revalidação incremental
        est = _ESTADO
        vistos = set()
        mudou = False
        for arquivo in _RAIZ.rglob("*.md"):
            if arquivo.name == "README.md":
                continue
            chave = str(arquivo)
            vistos.add(chave)
            no = est.por_caminho.get(chave)
            try:
                mt = arquivo.stat().st_mtime_ns
            except OSError:
                continue
            if no is None or no.mtime_ns != mt:
                _desindexar(est, chave)
                _indexar_arquivo(est, arquivo, _RAIZ)
                mudou = True
        for chave in [k for k in est.por_caminho if k not in vistos]:
            _desindexar(est, chave)
            mudou = True
        if mudou:
            _ligar(est, _RAIZ)
            _MISS_CURADO.clear()


def _desindexar(est: _Estado, chave: str) -> None:
    no = est.por_caminho.pop(chave, None)
    if no is None:
        return
    est.pasta_de_entidade.pop(str(no.caminho), None)
    ids = est.por_tipo.get(no.tipo)
    if ids and no.id in ids:
        ids.remove(no.id)
    caminhos = est.por_arquivo.get((no.arquivo.name, no.id))
    if caminhos and no.arquivo in caminhos:
        caminhos.remove(no.arquivo)
        if not caminhos:
            est.por_arquivo.pop((no.arquivo.name, no.id), None)
    for mapa, chave in ((est.por_pasta, str(no.arquivo.parent)),
                        (est.por_nome, no.arquivo.name)):
        lista = mapa.get(chave)
        if lista and no.arquivo in lista:
            lista.remove(no.arquivo)
            if not lista:
                mapa.pop(chave, None)
    if est.nos.get(no.id) is no:
        est.nos.pop(no.id, None)
        # se havia duplicata, promove outra cópia
        for outro in est.por_caminho.values():
            if outro.id == no.id:
                est.nos[no.id] = outro
                break


# --------------------------------------------------------------------------- #
# As portas de escrita (write-through) — acionadas por `io.py`, sob o WRITE_LOCK
# --------------------------------------------------------------------------- #

def invalidar(caminho) -> None:
    global _EPOCA
    """`write_doc`, `rewrite_description`, `create_entity`: um `.md` foi (re)escrito."""
    global _ESTADO
    if not ativo() or _ESTADO is None or _RAIZ is None:
        return
    _EPOCA += 1
    with _LOCK:
        arquivo = Path(caminho)
        _desindexar(_ESTADO, str(arquivo))
        if arquivo.exists():
            _indexar_arquivo(_ESTADO, arquivo, _RAIZ)
        _ligar(_ESTADO, _RAIZ)


def mover(origem, destino) -> None:
    global _EPOCA
    """`move_entity`: uma PASTA mudou de lugar — reindexa a subárvore inteira.

    É o caso que `git-ressuscita-personagem-movido` torna crítico: um índice apontando
    para a pasta antiga liga A Mente ao fantasma, em silêncio.
    """
    global _ESTADO
    if not ativo() or _ESTADO is None or _RAIZ is None:
        return
    _EPOCA += 1
    with _LOCK:
        prefixo = str(Path(origem))
        for chave in [k for k in _ESTADO.por_caminho if k == prefixo or k.startswith(prefixo + os.sep)]:
            _desindexar(_ESTADO, chave)
        destino = Path(destino)
        if destino.is_dir():
            for arquivo in destino.rglob("*.md"):
                if arquivo.name != "README.md":
                    _indexar_arquivo(_ESTADO, arquivo, _RAIZ)
        elif destino.exists():
            _indexar_arquivo(_ESTADO, destino, _RAIZ)
        _ligar(_ESTADO, _RAIZ)


def remover(caminho) -> None:
    global _EPOCA
    """`remove_entity`: uma pasta foi apagada (item consumido, spec 046)."""
    global _ESTADO
    if not ativo() or _ESTADO is None or _RAIZ is None:
        return
    _EPOCA += 1
    with _LOCK:
        prefixo = str(Path(caminho))
        for chave in [k for k in _ESTADO.por_caminho if k == prefixo or k.startswith(prefixo + os.sep)]:
            _desindexar(_ESTADO, chave)
        _ligar(_ESTADO, _RAIZ)


# --------------------------------------------------------------------------- #
# Consulta — nós e conteúdo
# --------------------------------------------------------------------------- #

def pronto() -> bool:
    return ativo() and _ESTADO is not None


def doc(caminho):
    """`(fm, body)` de um `.md`, ou None se não está no índice.

    **NUNCA devolve conteúdo obsoleto.** Cada chamada confere o `mtime` do arquivo; se
    ele mudou por fora (edição à mão, `git checkout`, o `os.replace` cru que as fixtures
    de selftest fazem), o nó é reindexado NA HORA e o valor volta fresco. Custa um
    `stat` (~1 µs) contra os 35,8 µs de parsear — e compra a propriedade que torna esta
    spec defensável: o caminho de execução pode ler daqui sem violar o Princípio III,
    porque não há foto, há verificação.

    O `fm` sai em CÓPIA PROFUNDA, e isso não é zelo: chamadores MUTAM o mapa antes de
    regravar (`marcar_extinto` faz `fm["state"] = ...`, `_expire_memories` idem), e sem
    a cópia a mutação corromperia o índice em memória. A cópia é `_copia`, especializada
    (0,96 µs contra 35,8 µs de parsear — 37× mais barato). O `body` é str (imutável), vai
    como está.
    """
    if not pronto():
        return None
    chave = str(caminho)
    no = _ESTADO.por_caminho.get(chave)
    if no is None:
        return None
    try:
        mt = os.stat(chave).st_mtime_ns
    except OSError:
        return None
    if mt != no.mtime_ns:
        with _LOCK:
            _desindexar(_ESTADO, chave)
            no = _indexar_arquivo(_ESTADO, Path(chave), _RAIZ)
            if no is None:
                return None
            _ligar(_ESTADO, _RAIZ)
    return _copia(no.fm), no.body


def campos(caminho, *nomes):
    """Os valores destes campos do frontmatter, sem cópia. `None` se não indexado.

    Irmã barata de `doc()`: mesma validação por `mtime` (nunca devolve obsoleto), mas
    sem construir a cópia profunda — porque devolve ESCALARES, que são imutáveis, e
    portanto não há como um chamador corromper o índice por engano. Pedir um campo que
    guarda dict/list devolve o objeto vivo, e por isso esta função é para os campos de
    DECISÃO (`type`, `state`, `timestamp_end`, `kind`, `evento`), nunca para os que
    carregam estrutura (`involved`, `status`).

    Existe por um número: `_expire_memories` varria as 804 memórias da Mira a cada
    chamada, 238 vezes por face — 191 458 leituras completas para decidir três campos.

    O CORTE continua fora daqui: esta função não sabe o que é "vencida". Ela entrega os
    campos; quem pergunta é que compara com o relógio.
    """
    if not pronto():
        return None
    chave = str(caminho)
    no_ = _ESTADO.por_caminho.get(chave)
    if no_ is None:
        return None
    try:
        mt = os.stat(chave).st_mtime_ns
    except OSError:
        return None
    if mt != no_.mtime_ns:
        with _LOCK:
            _desindexar(_ESTADO, chave)
            no_ = _indexar_arquivo(_ESTADO, Path(chave), _RAIZ)
            if no_ is None:
                return None
            _ligar(_ESTADO, _RAIZ)
    return tuple(no_.fm.get(nome) for nome in nomes)


def no(entity_id: str) -> No | None:
    return _ESTADO.nos.get(entity_id) if pronto() else None


def caminhos_de(nome_arquivo: str, entity_id: str | None = None) -> list:
    """Os `.md` chamados `nome_arquivo` — todos, ou só os do id dado.

    Substitui `WORLD_DIR.rglob(nome_arquivo)` nas buscas por id. Devolve LISTA, e não
    "o primeiro que casar", porque quem chama precisa poder ver a duplicata e recusar:
    `find_character_folder` levanta quando acha duas, e essa recusa é a defesa contra
    `git-ressuscita-personagem-movido`. O índice não escolhe entre cópias.

    Devolve **None** (não `[]`) quando o índice não está de pé — para o chamador
    distinguir "não há índice, varra o disco" de "o índice olhou e não achou".
    """
    if not pronto():
        return None
    if entity_id is None:
        return [no_.arquivo for no_ in list(_ESTADO.por_caminho.values())
                if no_.arquivo.name == nome_arquivo and no_.arquivo.exists()]
    # A RECUSA DE DUPLICATA NÃO PODE DEPENDER DE FRESCOR (achado do exploratório).
    # `find_character_folder` levanta quando o mesmo id existe em duas pastas, e essa
    # recusa é a defesa contra `git-ressuscita-personagem-movido` — a duplicata NASCE
    # justamente por fora das portas (`checkout`/`stash`/`submodule update` recria a
    # pasta antiga enquanto a nova segue no disco). Com o índice velho, ele via UMA
    # cópia e devolvia em silêncio: o modo de falha exato que a recusa existe para
    # impedir, e o pior possível para esta feature.
    #
    # Custa uma sincronização estrutural (stat de 267 diretórios, ~0,6 ms) e só nos
    # arquivos de DEFINIÇÃO de entidade — memória e intenção não têm essa recusa.
    if nome_arquivo in ENTITY_FILENAMES:
        _sincronizar_estrutura_se_preciso()
    bruto = _ESTADO.por_arquivo.get((nome_arquivo, entity_id), ())
    saida = [c for c in bruto if c.exists()]
    if saida:
        return saida

    # MISS. Aqui mora a "invalidação por miss" que o item 63 §4-A propôs, e o que ela
    # compra é a propriedade que importa: entrada obsoleta vira resposta LENTA E
    # CORRETA, nunca resposta errada.
    #
    # Mas a cura tem de distinguir TRÊS misses, e não distinguir custou caro na
    # primeira versão: `find_entity` varre `ENTITY_FILENAMES` em ordem, então
    # perguntar "o `corno-de-sinalizacao` é um location.md?" é um não-achou LEGÍTIMO —
    # e revalidar o mundo a cada um desses fez `find_entity` ir a 66 ms, PIOR que a
    # varredura que o índice veio substituir.
    if bruto:
        # tínhamos caminhos e todos sumiram do disco: a pasta mudou de lugar por fora
        # das portas (o `os.replace` cru das fixtures, o `git checkout` no mundo real).
        # É staleness de verdade — cura.
        pass
    elif entity_id in _ESTADO.nos:
        # o id existe, só não com ESTE nome de arquivo. Não-achou legítimo.
        return []
    elif entity_id in _MISS_CURADO:
        # já revalidamos o mundo atrás deste id e ele não estava lá. Não insiste: um id
        # inexistente consultado em laço revalidaria o mundo a cada volta.
        return []
    _MISS_CURADO.add(entity_id)
    garantir()
    return [c for c in _ESTADO.por_arquivo.get((nome_arquivo, entity_id), ())
            if c.exists()]


def _ordenado(mapa: dict, especie: str, chave: str) -> list:
    """A lista, ordenada e SÓ COM O QUE EXISTE — reordenando só se ela mudou.

    Ordena por `Path` (não por `str`) de propósito: são ordens DIFERENTES quando os
    caminhos divergem antes do último componente (`a-x/b.md` vem antes de `a/b.md` por
    string, e depois por partes), e a ordem que os chamadores viam era a de `Path`.

    O FILTRO DE EXISTÊNCIA não é zelo: `glob` nunca devolveu arquivo apagado, e 16 das
    56 fases de selftest apagam `.md` direto (`p.unlink`, `shutil.rmtree`) sem passar
    pelas portas de `io.py`. Sem o filtro, o índice devolvia o caminho morto e quem
    chamava estourava com `FileNotFoundError` — um modo de falha que o disco nunca
    tinha. Desindexa no ato, então o custo é pago uma vez por arquivo removido.
    """
    lista = mapa.get(chave)
    if lista is None:
        return []
    if (especie, chave) in _ESTADO.sujos:
        lista.sort()
        _ESTADO.sujos.discard((especie, chave))
    return lista


def _sincronizar_estrutura_se_preciso() -> None:
    """Sincroniza a estrutura da árvore quando houve escrita — para a recusa de duplicata.

    A ÉPOCA avança a cada escrita pelas portas e a cada revalidação de fronteira; entre
    duas escritas, a estrutura não muda por dentro do jogo e não há o que reconciliar.
    Custo no caso comum (época igual): um teste de inteiro.

    **Por que isto não precisa ser mais forte que isso.** A recusa de id duplicado é a
    defesa contra `git-ressuscita-personagem-movido`, e a duplicata NUNCA nasce do jogo:
    `new_id` carrega sufixo aleatório e `move_entity` recusa destino existente. Ela nasce
    de OPERAÇÃO — `checkout`/`stash`/`submodule update` recriando a pasta antiga. Por
    isso o portão é a SUBIDA (`app.main` recusa subir com duplicata, spec 063) e não uma
    conferência em cada leitura: o mundo que um processo serve está limpo por construção,
    e a fronteira da requisição (`garantir()`) apanha o que mudar depois.

    Uma versão anterior tinha aqui um limiar de tempo de 200 ms, para cobrir a duplicata
    nascida com o server no ar. Saiu quando o portão de boot entrou: guardar contra um
    estado que não pode existir é complexidade sem dono.
    """
    global _EPOCA_SINCRONIZADA
    if _EPOCA_SINCRONIZADA == _EPOCA:
        return
    sincronizar()
    _EPOCA_SINCRONIZADA = _EPOCA


def sincronizar() -> None:
    """Reconcilia a ESTRUTURA do mundo com o disco — barato, por `mtime` de DIRETÓRIO.

    Criar, apagar ou renomear um `.md` muda o `mtime` da pasta que o contém, e o mundo
    tem 267 pastas contra 3 151 arquivos: statar todas custa **0,6 ms**, contra 21 ms
    de statar os arquivos. É o que torna viável chamar isto a cada enumeração
    (`arquivos_no_mundo` roda 176 vezes numa face) em vez de só na fronteira.

    NÃO apanha edição de CONTEÚDO em lugar (mesmo arquivo, mesmo nome): para essa há
    duas defesas — `doc()`/`campos()` conferem o `mtime` do arquivo em toda leitura, e
    `garantir()` faz a varredura completa uma vez por requisição.
    """
    if not pronto() or _RAIZ is None:
        return
    with _LOCK:
        conhecidas = _ESTADO.mtime_pasta
        if not conhecidas:
            _varrer_pastas(str(_RAIZ))
            return
        # O caso comum: nada mudou. Só `stat` — sem `scandir`, sem `listdir`.
        mudadas = []
        for pasta, mt_antigo in list(conhecidas.items()):
            try:
                mt = os.stat(pasta).st_mtime_ns
            except OSError:
                mt = None
            if mt != mt_antigo:
                mudadas.append(pasta)
        for pasta in mudadas:
            if os.path.isdir(pasta):
                _sincronizar_pasta(pasta)
                _varrer_pastas(pasta, so_novas=True)   # subpasta que nasceu
            else:
                for chave in [str(c) for c in _ESTADO.por_pasta.get(pasta, ())]:
                    _desindexar(_ESTADO, chave)
                conhecidas.pop(pasta, None)
                _ligar(_ESTADO, _RAIZ)


def _varrer_pastas(raiz: str, so_novas: bool = False) -> None:
    """Desce a árvore a partir de `raiz`, registrando pastas. Com `so_novas`, só entra
    nas que o índice ainda não conhece — é como uma pasta recém-criada é descoberta
    sem repassar o mundo inteiro."""
    pilha = [raiz]
    while pilha:
        atual = pilha.pop()
        nova = atual not in _ESTADO.mtime_pasta
        if nova or not so_novas:
            _sincronizar_pasta(atual)
        try:
            with os.scandir(atual) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        if not so_novas or e.path not in _ESTADO.mtime_pasta:
                            pilha.append(e.path)
        except OSError:
            continue


def sincronizar_pasta(pasta) -> None:
    """Porta pública de `_sincronizar_pasta` — para quem atravessa arestas de uma pasta
    sem passar por `arquivos_em` (a travessia reversa de `io.arquivos_envolvendo`)."""
    if pronto():
        _sincronizar_pasta(str(pasta))


def _sincronizar_pasta(pasta: str) -> None:
    """Reconcilia UMA pasta com o disco, se o `mtime` dela mudou.

    Criar, apagar ou renomear um `.md` muda o `mtime` do diretório que o contém — então
    um stat de diretório decide se há algo a fazer. Quando não há (o caso comum), custa
    um stat; quando há, reindexa só aquela pasta.

    É isto que apanha o que não passa pelas portas de `io.py`: as 16 fases de selftest
    que apagam `.md` com `p.unlink()`/`shutil.rmtree`, e o `git checkout` no mundo real.
    """
    try:
        mt = os.stat(pasta).st_mtime_ns
    except OSError:
        mt = None
    if _ESTADO.mtime_pasta.get(pasta) == mt:
        return
    with _LOCK:
        atuais = set()
        if mt is not None:
            try:
                for nome in os.listdir(pasta):
                    if nome.endswith(".md") and nome != "README.md":
                        atuais.add(os.path.join(pasta, nome))
            except OSError:
                pass
        conhecidos = {str(c) for c in _ESTADO.por_pasta.get(pasta, ())}
        mudou = False
        for morto in conhecidos - atuais:
            _desindexar(_ESTADO, morto)
            mudou = True
        for novo in atuais - conhecidos:
            if _indexar_arquivo(_ESTADO, Path(novo), _RAIZ) is not None:
                mudou = True
        if mudou:
            _ligar(_ESTADO, _RAIZ)
        _ESTADO.mtime_pasta[pasta] = mt


def arquivos_em(pasta) -> list | None:
    """Os `.md` indexados DIRETAMENTE em `pasta`, ordenados. None se não há índice.

    Substitui `sorted(pasta.glob("*.md"))` — o padrão mais repetido do Motor, e o que
    domina em quem tem muita memória (a Mira tem 804). Sai SEMPRE ordenado, inclusive
    onde o original não ordenava: ordem de `glob` nunca foi garantida, então fixá-la só
    torna determinístico o que já era arbitrário.

    Uma pasta que o índice não conhece devolve `[]`, não None — "olhei e está vazia".
    Só a ausência de índice devolve None.
    """
    if not pronto():
        return None
    chave = str(pasta)
    _sincronizar_pasta(chave)
    return list(_ordenado(_ESTADO.por_pasta, "pasta", chave))


def caminhos_por_nome(nome_arquivo: str) -> list | None:
    """Todos os `.md` com este nome, no mundo inteiro, ordenados. None se não há índice.

    Substitui `WORLD_DIR.rglob("route.md")` e irmãos — a varredura mundial por TIPO,
    que é o que `find_route`, `_location_folder_by_id` e o grafo de rotas fazem.
    """
    if not pronto():
        return None
    lista = _ordenado(_ESTADO.por_nome, "nome", nome_arquivo)
    vivos = [c for c in lista if os.path.exists(c)]
    if len(vivos) != len(lista):
        # Devolve os VIVOS, não a lista relida do índice: se por algum motivo a
        # desindexação não limpar tudo, o caminho morto não pode escapar mesmo assim.
        # `glob` nunca devolveu arquivo apagado, e é esse contrato que vale.
        with _LOCK:
            for c in lista:
                if not os.path.exists(c):
                    _desindexar(_ESTADO, str(c))
            _ligar(_ESTADO, _RAIZ)
    return vivos


def pasta_de_entidade_id(pasta) -> str | None:
    """O id da entidade DONA de uma pasta — subindo até achar uma pasta de entidade.

    `<...>/mira-vigia-da-praca/memories` devolve `mira-vigia-da-praca`. É o que deixa
    `arquivos_envolvendo` conferir que a memória achada pela aresta reversa é mesmo
    daquela pasta, e não de outro personagem.
    """
    if not pronto() or _RAIZ is None:
        return None
    atual = Path(pasta)
    while True:
        eid = _ESTADO.pasta_de_entidade.get(str(atual))
        if eid is not None:
            return eid
        if atual == _RAIZ or atual.parent == atual:
            return None
        atual = atual.parent


def por_tipo(tipo: str) -> list:
    return list(_ESTADO.por_tipo.get(tipo, ())) if pronto() else []


# --------------------------------------------------------------------------- #
# Consulta — arestas
# --------------------------------------------------------------------------- #

def pai(entity_id: str) -> str | None:
    return _ESTADO.pai.get(entity_id) if pronto() else None


def filhos(entity_id: str) -> list:
    return list(_ESTADO.filhos.get(entity_id, ())) if pronto() else []


def subarvore(entity_id: str):
    """Todos os descendentes, em largura. O que `carried_item_ids` e o peso já fazem
    à mão descendo pastas."""
    if not pronto():
        return
    fila = list(_ESTADO.filhos.get(entity_id, ()))
    visto = set()
    while fila:
        atual = fila.pop(0)
        if atual in visto:
            continue
        visto.add(atual)
        yield atual
        fila.extend(_ESTADO.filhos.get(atual, ()))


def arestas(entity_id: str, tipo: str) -> list:
    """Arestas SAINDO de `entity_id`. Pode devolver id sem nó (aresta pendente): um
    `involved` cujo personagem foi removido, um `about` de item consumido. Não é erro e
    não se apaga a memória por isso (Princípio IV) — quem chama trata ausência como
    ausência, exatamente como `name_of` e `dono` já fazem."""
    return list(_ESTADO.arestas.get((entity_id, tipo), ())) if pronto() else []


def reverso(entity_id: str, tipo: str) -> list:
    """Arestas CHEGANDO em `entity_id` — a travessia que não existia, e a razão desta
    spec. `reverso(elga, "envolve")` devolve toda memória do mundo que cita a Elga:
    0,1 µs medidos, contra uma varredura mundial."""
    return list(_ESTADO.reverso.get((entity_id, tipo), ())) if pronto() else []


# --------------------------------------------------------------------------- #
# Diagnóstico
# --------------------------------------------------------------------------- #

def estatisticas() -> dict:
    if not pronto():
        return {"ativo": ativo(), "construido": False}
    n_arestas = sum(len(v) for v in _ESTADO.arestas.values())
    return {"ativo": True, "construido": True,
            "nos": len(_ESTADO.por_caminho), "arestas": n_arestas,
            "tipos": {t: len(v) for t, v in _ESTADO.por_tipo.items()}}


def _resetar() -> None:
    """Só para teste: força a próxima `garantir()` a reconstruir."""
    global _ESTADO
    with _LOCK:
        _ESTADO = None
        _MISS_CURADO.clear()
