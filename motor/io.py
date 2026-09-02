"""O Motor / io (spec 021 — extraído de __init__).

Parte do pacote em níveis. Ver research.md (T001) para o grafo de dependências.
"""
from __future__ import annotations

import os
import random
import shutil
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from . import indice


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


WORLD_DIR = Path(os.environ.get("LOREFORGE_WORLD", REPO_ROOT / "loreforge-world" / "tardenia"))


WRITE_LOCK = threading.RLock()


class MotorError(Exception):
    """Erro operacional do Motor com mensagem legível."""


class ValidationError(MotorError):
    """Escrita rejeitada pelo World Validator."""


ENTITY_FILENAMES = {
    "location.md": "location",
    "character.md": "character",
    "route.md": "route",
    "item.md": "item",
    "object.md": "object",
}


def indice_pronto() -> bool:
    """Garante que o índice exista, uma vez. Depois disso é um teste de ponteiro.

    A CONSTRUÇÃO é aqui e não no boot de propósito: os selftests apontam
    `LOREFORGE_WORLD` para um mundo temporário e o Motor tem de seguir o que a variável
    disser no momento do primeiro uso, não no do import."""
    if not indice.ativo():
        return False
    if not indice.pronto():
        indice.garantir(WORLD_DIR)
    return indice.pronto()


def arquivos_em(pasta: Path, padrao: str = "*.md") -> list:
    """Os `.md` diretamente em `pasta`, ordenados — pelo índice quando ele está de pé.

    O substituto de `sorted(pasta.glob("*.md"))`. Troca a FONTE da iteração e nada
    mais: quem chama continua lendo cada arquivo e aplicando o PRÓPRIO corte, que é a
    regra do contrato (o índice entrega aresta crua; o corte é de quem pergunta)."""
    achado = indice.arquivos_em(pasta) if indice_pronto() else None
    if achado is None:
        return sorted(pasta.glob(padrao)) if pasta.is_dir() else []
    return achado


def arquivo_por_id(nome_arquivo: str, entity_id: str) -> Path | None:
    """O `.md` chamado `nome_arquivo` cujo `id` é `entity_id`, ou None.

    Separada de `arquivos_no_mundo` de propósito, e a separação é de CUSTO, não de
    gosto: buscar POR ID é chave (e se cura por miss, barato), enquanto ENUMERAR exige
    sincronizar a estrutura do mundo para não perder arquivo recém-nascido. Metade das
    chamadas de enumeração numa face eram busca por id disfarçada — 137 de 176 — e
    sincronizar em cada uma custava mais que a varredura que o índice veio substituir.

    Devolve o PRIMEIRO em ordem, como o laço original fazia. Id duplicado não levanta
    aqui: quem tem essa recusa é `find_character_folder`, e ela é sobre PERSONAGEM.
    """
    if indice_pronto():
        achados = indice.caminhos_de(nome_arquivo, entity_id)
        if achados is not None:
            return achados[0] if achados else None
    for path in sorted(WORLD_DIR.rglob(nome_arquivo)):
        fm, _ = read_doc(path)
        if fm.get("id") == entity_id:
            return path
    return None


def arquivos_no_mundo(nome_arquivo: str) -> list:
    """Todos os `.md` com este nome, no mundo — o substituto de `WORLD_DIR.rglob(nome)`."""
    if not indice_pronto():
        return sorted(WORLD_DIR.rglob(nome_arquivo))
    if "*" in nome_arquivo or "?" in nome_arquivo or "[" in nome_arquivo:
        # PADRÃO, não nome. `validador.duplicate_ids` passa `"*.md"`, e o índice é
        # chaveado por nome exato — devolvia lista VAZIA, e o mundo com id duplicado
        # passava na validação em silêncio. Justamente a recusa que existe para conter
        # `git-ressuscita-personagem-movido`. Padrão volta ao disco, e é raro: só o
        # validador usa, e só no boot.
        indice.sincronizar()
        return sorted(WORLD_DIR.rglob(nome_arquivo))
    # ENUMERAR exige ver o que NASCEU. Diferente da busca por id (que se cura por
    # miss), aqui um arquivo novo que o índice não conhece é uma ausência silenciosa —
    # foi como o "cão inline" da fase 22 sumiu do seletor. A sincronização estrutural
    # por mtime de diretório custa 0,6 ms e resolve.
    indice.sincronizar()
    achado = indice.caminhos_por_nome(nome_arquivo)
    if achado is None:
        return sorted(WORLD_DIR.rglob(nome_arquivo))
    return achado


def _arquivos_por_aresta(pasta: Path, alvo_id: str, tipo: str) -> list | None:
    """Base de `arquivos_envolvendo`/`arquivos_sobre`: os `.md` de `pasta` ligados a
    `alvo_id` pela aresta `tipo`. None quando não há índice."""
    if not indice_pronto():
        return None
    dono_esperado = indice.pasta_de_entidade_id(pasta)
    if dono_esperado is None:
        return None
    # SINCRONIZA A PASTA ANTES de atravessar. Sem isto a travessia enxergava nós de
    # arquivos já apagados por fora das portas (o `p.unlink()` das fixtures de
    # selftest), e quem chamava estourava com `FileNotFoundError` — um modo de falha
    # que a varredura em disco nunca teve, porque `glob` não devolve o que não existe.
    indice.sincronizar_pasta(pasta)
    saida = []
    for mid in indice.reverso(alvo_id, tipo):
        no = indice.no(mid)
        if no is None or indice.pai(mid) != dono_esperado:
            continue
        if no.arquivo.parent != pasta:
            continue
        saida.append(no.arquivo)
    return sorted(saida)


def arquivos_sobre(pasta: Path, alvo_id: str) -> list | None:
    """Os `.md` de `pasta` cujo `about` aponta para `alvo_id` — a aresta `sobre`.
    É como a memória de ROTA se liga à rota."""
    return _arquivos_por_aresta(pasta, alvo_id, "sobre")


def arquivos_envolvendo(pasta: Path, alvo_id: str) -> list | None:
    """Os `.md` de `pasta` que CITAM `alvo_id` em `involved` — pela aresta REVERSA.

    Devolve None quando não há índice, e aí quem chama varre a pasta como sempre.

    É esta função que entrega o ganho real da spec 063, e o número que a justifica:
    montar a face da Mira fazia **775 220** leituras de documento sobre ~1 000 arquivos.
    A causa não era o custo de cada leitura — era perguntar "esta memória cita o Fulano?"
    varrendo as 804 memórias dela, uma vez por pessoa presente e por item da cena. A
    aresta reversa responde a mesma pergunta olhando só as memórias que citam o Fulano.

    O CORTE continua sendo de quem pergunta: esta função não filtra por vivo, por
    `kind`, nem por `evento`. Ela só troca a FONTE da iteração — e é por isso que os
    consumidores migrados devolvem exatamente o que devolviam antes.
    """
    return _arquivos_por_aresta(pasta, alvo_id, "envolve")


def _entity_file(folder: Path) -> Path | None:
    """Retorna o arquivo de definição de uma pasta de entidade, se houver."""
    for fname in ENTITY_FILENAMES:
        candidate = folder / fname
        if candidate.exists():
            return candidate
    return None


def read_doc(path: Path) -> tuple[dict, str]:
    """Lê `(frontmatter, body)` de um `.md` — pelo índice quando ele está de pé.

    Por que o índice entra AQUI, num lugar só, e não em cada chamador (spec 063): um
    único `get_context` do personagem mais vivido fazia **206 818** chamadas desta função
    sobre **1 011 arquivos distintos** — amplificação de 205×. Servir o conteúdo daqui
    conserta todos os chamadores de uma vez, sem tocar em nenhum deles, e é por isso que
    a migração pode provar resposta byte-idêntica.

    O `fm` volta em cópia profunda (`indice.doc`): chamadores mutam o mapa antes de
    regravar, e sem a cópia corromperiam o índice. Ainda assim é 7,7× mais barato que
    parsear."""
    doc = indice.doc(path)
    if doc is not None:
        return doc
    text = path.read_text(encoding="utf-8")
    return frontmatter.split(text)


def _is_valid(fm: dict) -> bool:
    """True se o frontmatter passa no World Validator (usado nas leituras)."""
    return validator.validate(fm) == []


# spec 053 — A ENTIDADE EXTINTA. Irmã exata de `_is_alive` para memória: a coisa que
# deixou de existir no jogo continua no disco como VESTÍGIO, e só some das leituras.
#
# Por que não deletar. O Princípio IV proíbe deletar arquivo durante o jogo, e a
# exceção da spec 046 é escopada a "só ITEM consumido por completo" — reforçando que
# "qualquer outra classe de entidade continua SEM exceção nenhuma". Um object é outra
# classe. Marcar+filtrar honra a letra, e ainda guarda a DATA: uma capacidade futura
# de investigar pode achar as cinzas e saber há quanto tempo alguém acampou ali.
_EXTINTO = "extinto_em"


def esta_extinto(fm: dict) -> bool:
    """A entidade já deixou de existir no jogo? (o arquivo continua no disco)"""
    state = fm.get("state")
    return isinstance(state, dict) and state.get(_EXTINTO) is not None


def marcar_extinto(pasta: Path) -> None:
    """Carimba o instante da extinção. NUNCA remove o arquivo (Princípio IV)."""
    for nome in ("object.md", "item.md"):
        arquivo = pasta / nome
        if not arquivo.exists():
            continue
        fm, body = read_doc(arquivo)
        state = dict(fm.get("state") or {})
        state[_EXTINTO] = int(time.time())
        fm["state"] = state
        write_doc(arquivo, fm, body)
        return


def find_character_folder(character_id: str) -> Path:
    """A pasta do personagem — e ela tem de ser ÚNICA.

    ANTES devolvia o PRIMEIRO `rglob` que casasse. Com o mesmo id em duas pastas
    (o que o git produz sozinho: deslocar é rename, e `checkout`/`stash`/
    `submodule update` ressuscita o caminho antigo enquanto o novo segue no
    disco) isso ligava A Mente ao fantasma EM SILÊNCIO, e a ordem do `rglob` nem
    é garantida — o mesmo mundo podia dar respostas diferentes. Em 2026-08-20 havia
    12 personagens assim. Falhar alto é a única resposta honesta: o mundo está
    corrompido e nenhuma escolha automática entre as duas cópias é defensável aqui.
    Quem resolve é `sanea_duplicatas.py`, com histórico do git na mão.
    """
    achados = []
    candidatos = indice.caminhos_de("character.md", character_id) if indice_pronto() else None
    if candidatos is None:
        candidatos = WORLD_DIR.rglob("character.md")
    for path in candidatos:
        fm, _ = read_doc(path)
        if fm.get("id") == character_id:
            errors = validator.validate(fm)
            if errors:  # não se guia um personagem com arquivo inválido (FR-010)
                raise MotorError(
                    f"personagem '{character_id}' tem arquivo inválido: "
                    + "; ".join(errors)
                )
            achados.append(path.parent)
    if not achados:
        raise MotorError(f"personagem não encontrado: '{character_id}'.")
    if len(achados) > 1:
        onde = ", ".join(str(p.relative_to(WORLD_DIR)) for p in sorted(achados))
        raise MotorError(
            f"personagem '{character_id}' existe em MAIS DE UM lugar: {onde}. "
            "O mundo está duplicado — rode "
            "`python3 loreforge-server/sanea_duplicatas.py`."
        )
    return achados[0]


def find_entity(entity_id: str) -> tuple[Path, dict, str] | None:
    """Procura qualquer entidade por id em todo o mundo."""
    pronto = indice_pronto()
    for fname in ENTITY_FILENAMES:
        candidatos = indice.caminhos_de(fname, entity_id) if pronto else None
        if candidatos is None:
            candidatos = WORLD_DIR.rglob(fname)
        for path in candidatos:
            fm, body = read_doc(path)
            if fm.get("id") == entity_id:
                return path, fm, body
    return None


def _char_fm(char_folder: Path) -> dict:
    """Frontmatter do character.md de uma pasta de personagem (só o mapa)."""
    fm, _ = read_doc(char_folder / "character.md")
    return fm


def _fail(regra: str, **valores) -> dict:
    return {"regra": regra, "valores": valores}


def _marca(item_fm: dict | None, campo: str) -> bool:
    return (item_fm or {}).get(campo) is True


def _sinal(x: float) -> int:
    return (x > 0) - (x < 0)


_SYSTEM_FIELDS = {
    "type", "id", "controlled_by", "origin", "timestamp_start", "timestamp_end",
    "state", "travel_time_base", "from", "to", "bidirectional",
    "entry_point_on_arrival", "prerequisites",
}


def write_doc(path: Path, frontmatter_data: dict, body: str) -> None:
    """Valida e grava um documento de entidade de forma atômica.

    Levanta ValidationError se o frontmatter não passar no World Validator.
    """
    errors = validator.validate(frontmatter_data)
    if errors:
        raise ValidationError("; ".join(errors))
    text = frontmatter.join(frontmatter_data, body)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    # PORTA 1 do índice (spec 063). Cobre também `rewrite_description` e
    # `create_entity`, que gravam POR AQUI — o funil dentro do funil. É esta linha
    # que faz a op 2 de um turno enxergar a escrita da op 1, que era exatamente a
    # armadilha do memo de requisição (item 63 §3.4).
    indice.invalidar(path)


def rewrite_description(entity_folder: Path, filename: str, texto: str) -> None:
    """Reescreve o BODY (a descrição diegética) de uma entidade, no PRÓPRIO arquivo —
    mesmo id, mesma pasta (spec 046, `eat`, consumo parcial). Nunca cria arquivo novo
    nem move pasta: é a mesma disciplina de `_set_condition`/`_set_field` (mutação de
    campo em lugar), só que no BODY em vez do frontmatter."""
    fm, _ = read_doc(entity_folder / filename)
    write_doc(entity_folder / filename, fm, texto)


def move_entity(src: Path, dest: Path) -> None:
    """Move a pasta de uma entidade inteira (rename atômico) — a ÚNICA primitiva
    que desloca pasta no mundo (spec 037, Princípio XII): mover pasta é ESTRUTURA,
    não regra de tool. Todo deslocamento de pasta passa por aqui.

    Assume o WRITE_LOCK já tomado. Guarda defensiva: se `dest` já existe, LEVANTA —
    rede contra o overwrite silencioso que já apagou dado (ver new_id). A frase de
    recusa de colisão é SENTIDO da tool e fica no CHAMADOR, que checa dest.exists()
    antes, com a própria mensagem in-world.
    """
    if dest.exists():
        raise FileExistsError(f"destino de move_entity já existe: {dest}")
    os.replace(src, dest)
    indice.mover(src, dest)   # PORTA 2 — a subárvore inteira muda de caminho


_MUTABLE_ROOT_BY_KIND = {"character": "status", "object": "state", "item": "state"}


_IMMUTABLE_ROOTS_BY_KIND = {
    # `skills` SAIU daqui (spec 058, US6): não é mais um campo de identidade
    # reconhecido — deixou de ser obrigatório e deixou de subir ao contexto do
    # Árbitro. Mutar `skills.*` continua bloqueado do mesmo jeito (cai no
    # segundo guard, "só 'status.*' é mutável", já que não é a raiz mutável de
    # `character`), só a MENSAGEM de recusa muda de "identidade é imutável"
    # para "só 'status.*' é mutável" — comportamento protegido idêntico.
    "character": {"attributes", "id", "name", "type", "controlled_by"},
    "object": {"id", "name", "type", "interactions"},
    "item": {"id", "name", "type", "interactions"},
}


_ENTITY_FILE_BY_KIND = {"character": "character.md", "object": "object.md",
                        "item": "item.md"}


def new_id(prefix: str) -> str:
    """Id único para entidade CRIADA em runtime (memória, e o que vier depois).

    O sufixo aleatório não é enfeite. Duas entidades criadas no mesmo
    milissegundo recebiam o mesmo id, e como o mundo é arquivo, o segundo
    `os.replace` sobrescrevia o primeiro EM SILÊNCIO — nada falhava, o dado
    simplesmente sumia. Aconteceu ao aprender as rotas de um mapa só: seis
    memórias viraram uma.

    Vale só para id gerado. Id EDITORIAL (`taverna-do-gancho`, `portao-lateral`)
    continua legível de propósito: é referência cruzada entre arquivos, vira
    enum no prompt do Árbitro, e é o que faz um mundo em `.md` valer a pena.
    Contra id editorial repetido a defesa é outra: `duplicate_ids()`, que recusa
    no boot em vez de deixar sobrescrever.
    """
    return f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"


def name_of(entity_id: str) -> str:
    """Nome legível de qualquer entidade. Id cru é ruído — na memória e na prosa.

    Um personagem não lembra de "gibao-de-placas": ele lembra do gibão de placas.
    O id serve ao mundo; quem lê é gente.
    """
    if not entity_id:
        return "algo"
    found = find_entity(entity_id)
    if not found:
        return entity_id
    return (found[1].get("name") or entity_id)


def descricao_de(entity_id: str) -> dict | None:
    """A PROSA de uma entidade, lida do arquivo dela (spec 052).

    Irmã de `name_of`, e pela mesma razão: uma régua não julga um id, julga o que a
    coisa DIZ de si. Devolve `{nome, descricao, fazendo}` — só as chaves que
    existem.

    POR QUE ESTA PRIMITIVA PRECISOU EXISTIR. As réguas liam a descrição pelo
    `proximity_context` (o bundle que o Motor monta para A Mente), e esse bundle
    NUNCA carregou a prosa de item nem de object — só de location. Resultado: toda
    régua que diz ler a descrição de um item julgava pelo NOME
    (`cozinhabilidade`, `comestibilidade`, `toxicidade`, `embriaguez`, a vistosidade
    do furto, a arma no combate). O erro estava na CAMADA, não na falta do dado: o
    bundle é uma VISTA para o client — serve para validar que a coisa está ao
    alcance, não para ser a fonte do que ela é. O arquivo é a fonte (Princípio IV), e
    quem toca arquivo é primitiva (Princípio XII).

    Lê SOB DEMANDA, e é por isso que a prosa não precisa entrar no contexto de toda
    cena: só quem pergunta paga, e inflar o bundle degradaria todas as decisões do
    turno para servir a régua de uma.
    """
    if not entity_id:
        return None
    found = find_entity(entity_id)
    if not found:
        return None
    _path, fm, corpo = found
    out = {"nome": fm.get("name") or entity_id,
           "descricao": " ".join((corpo or "").split()) or None,
           "fazendo": (fm.get("status") or {}).get("action")}
    return {k: v for k, v in out.items() if v}


_GROUND_WORDS = {"chao", "solo", "terra", "ground", "floor"}


def _slugify(text) -> str:
    """Normaliza uma referência para comparação: minúsculas, sem acentos,
    palavras separadas por hífen ('Chão da Praça' → 'chao-da-praca')."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    parts, word = [], []
    for ch in text:
        if ch.isalnum():
            word.append(ch)
        elif word:
            parts.append("".join(word))
            word = []
    if word:
        parts.append("".join(word))
    return "-".join(parts)


_WHY_BY_REGRA = {
    "tamanho_excede_container": "o item excede o tamanho que o contêiner aceita",
    "container_lotado": "não há vaga no contêiner",
    "nao_e_container": "isso não guarda nada dentro",
    # spec 062, US2: a colheita não pode se chamar como a fonte de onde saiu —
    # "Macieira" colhida de "Macieira da Praça" era o item mal-nomeado que
    # motivou a spec. Recusa DETERMINÍSTICA no executor (nunca depende só do
    # juízo do Árbitro se comportar). Frase DIEGÉTICA — se este caso chegar a
    # narrar (deveria ser raro: a régua já evita), tem de soar como desfecho de
    # cena, não como diagnóstico de sistema.
    "colheita_nomeia_fonte": "nada ali rendeu algo diferente da própria planta",
    # NOMEIA de quem: sem isso, "as mãos já estão ocupadas" numa entrega faz o
    # jogador entender que são as DELE, quando eram as de quem ia RECEBER.
    # Uma recusa mal rotulada é indistinguível de um bug (achado real: Nerissa
    # tentou dar uma moeda a Tobias, que estava de mãos cheias).
    # DIZ O QUE FALTA, não só o que impede. Uma recusa que não aponta saída gasta
    # o turno duas vezes — o mesmo padrão de `persuade`/`expulsar`, que mandam
    # para a ferramenta certa. Em linguagem de MUNDO: sem nome de tool, porque
    # este texto chega ao jogador pela narração (Princípio V).
    "maos_ocupadas": "está de mãos ocupadas — precisaria liberar uma mão antes",
    "slot_ocupado": "já tem algo nessa parte do corpo — precisaria tirar antes",
    "corpo_sem_slot": "não há onde vestir isso nesse corpo",
    "peso_excede_carga": "não tem braço para tanto peso",
    "peso_excede_empurrar": "não tem força para empurrar tanto peso",
    "item_nao_vestivel": "isso não se veste",
    "item_inacessivel": "o item não está ao alcance",
    "destino_inacessivel": "o destino não está ao alcance",
    "container_fechado": "está fechado",
    "trava_nao_satisfeita": "a tranca não cede",
    "nao_tranca": "isso não abre nem fecha",
    "teste_de_forca_falhou": "a força não bastou desta vez",
    "objeto_fixo": "faz parte do lugar — não se carrega",
    "recusa_absoluta": "nada nesta conversa o move",
    "persuasao_falhou": "as palavras não bastaram",
    "personagem_inacessivel": "não está ao alcance de conversa",
    "rota_indisponivel": "esse caminho não se abre a você",
    "ataque_errou": "o golpe passou ao largo",
    "golpe_absorvido": "o golpe acertou, mas a proteção segurou",
    "alvo_ja_morto": "já não há o que ferir",
    "atacante_caido": "não tem como agir agora",
    "ja_dormindo": "já está dormindo",
    "nao_esta_dormindo": "não está dormindo",
    "sono_profundo": "o corpo não deixa: o sono é fundo demais para se levantar agora",
    "rest_sem_op": "não ficou claro se era deitar ou despertar",
    "sem_alvo_valido": "não há quem golpear ao alcance",
    "peso_excede_arrasto": "não consegue arrastar esse corpo nem um palmo",
    "alvo_resistiu": "ele se soltou e não vai a lugar nenhum",
    "alvo_desacordado": "não se convence quem não ouve",
    "item_nao_e_do_alvo": "isso não pertence a quem se pediu para entregar",
    "destino_e_o_dono": "ele já é o dono — não faz sentido pedir que dê a si mesmo",
    "nada_a_ceder": "ele não abre mão disso de jeito nenhum",
    "nao_cedeu": "ele ouviu, pensou, e não se desfez do que é seu",
    "furto_impossivel": "não há como tirar isso sem que o dono perceba",
    "valor_insuficiente": "o que você oferece não paga isso",
    "necessidade_insuficiente": "ele não precisa disso o bastante para abrir mão do que é dele",
    "rota_inexistente": "esse caminho não existe em lugar nenhum",
    "leitura_falhou": "os rabiscos não se deixaram entender",
    "informante_indisponivel": "não há como perguntar a quem não pode responder",
    "recusou_informar": "ele não quis dizer",
    "nao_confiou": "ela não quis abrir o que sabe",
    "nada_a_contar": "ela nada sabe disso",
    "informante_nao_sabe": "ele não sabe fazer esse caminho",
    "fonte_omitida": "isso não foi lido em parte alguma — alguém o disse",
    "citacao_nao_confere": "isso não está escrito aí",
    "nada_a_examinar": "não há nada escrito aí para se debruçar",
    "nao_esta_a_venda": "isso não está à venda",
    "nao_e_negociavel": "isso não está à venda",
    "item_nao_e_seu": "isso não está com quem oferece",
    "sem_espaco_para_receber": "não há como levar tudo isso",
    "pagamento_nao_e_dinheiro": "isso não é moeda que se aceite",
    "parceiro_incapaz": "não está em condições de negociar",
    "destino_ocupado": "não há onde pôr isso sem confundir com outra coisa",
    "caminho_desconhecido": "você não sabe como chegar lá",
    "ja_esta_la": "você já está onde queria chegar",
    "viagem_interrompida": "a jornada parou antes do fim",
    "descansando": "você está dormindo — precisa acordar antes de agir",
    "alvo_nao_caido": "ele já pode agir sozinho — não há o que socorrer",
    "nao_possui_item": "isso não está com quem age — pegue antes de entregar ou largar",
    "item_vestido": "isso está vestido no corpo — precisaria tirar antes",
    "item_carregado": "isso está com alguém — empurra-se só o que ninguém carrega",
    "item_alheio": "isso está com outra pessoa — pegue antes de vestir",
    "nao_vestido_em_voce": "isso não está vestido em quem age — não há o que tirar",
    "nao_comestivel": "isso não é algo que se coma",
    "nao_alimenta": "isso não mataria a fome em nada — não vale a mordida",
    "nao_bebivel": "isso não é algo que se beba",
    "alvo_inacessivel": "não está ao alcance para beber",
    "ingrediente_inacessivel": "esse ingrediente não está ao alcance",
    "fonte_calor_inacessivel": "essa fonte de calor não está ao alcance",
    "sem_calor": "isso não fornece calor nenhum para cozinhar",
    "nao_cozinhavel": "isso não forma prato nenhum",
    "ja_cozinhando": "já está ocupado com outra coisa no fogo",
    # spec 052 — forjar. As três de admissão dizem QUAL das três coisas faltou:
    # uma nota agregada esconderia se o problema era o metal, o fogo ou a oficina,
    # e uma recusa que não aponta a saída gasta o turno duas vezes.
    "sem_material": "não há material nenhum para trabalhar",
    "material_inacessivel": "esse material não está ao alcance",
    "peca_inacessivel": "essa peça em processo não está ao alcance",
    "peca_de_outra_oficina": "essa peça foi começada para outra coisa — não é este o trabalho dela",
    "ja_trabalhando": "já está com as mãos em outra peça",
    "nao_forjavel": "não dá para forjar nada com isso",
    "material_imprestavel": "esse material não presta para trabalho nenhum",
    "sem_calor_de_forja": "esse fogo não dá conta de trabalhar metal",
    "sem_ferramental": "não há aqui com que trabalhar metal",
    # spec 057 — craft. `ja_trabalhando`/`material_inacessivel`/`peca_inacessivel`/
    # `descansando` são REUSADOS da forja (mesmo fato, mesma frase — craft segue o
    # mesmo molde de trabalho retomável).
    "sem_viabilidade": "não há nada aqui que sustente o que você quer fazer",
    "peca_de_outro_trabalho": "esse trabalho foi começado para outra coisa — não é isto que está em processo",
    # conserto pós-057 (achado da exploração): "sem bloco de trabalho" quase
    # sempre significa "já terminou", não "é de outra coisa" — reusado por
    # forja também (`origin_de`, `motor/trabalho.py`).
    "peca_ja_concluida": "esse trabalho já terminou; não há mais o que retomar ali",
    "alvo_inacessivel": "não está ao alcance para esquartejar",
    "alvo_nao_morto": "não há como esquartejar quem ainda pode se mexer",
    "ja_esquartejado": "esse corpo já foi todo revirado; não sobrou nada a tirar",
    "sem_carne": "aquilo não é feito de carne",
    "nada_a_aproveitar": "não sobrou nada aproveitável ali",
    # spec 053 — acender fogo. (`material_inacessivel` é reusado da forja: mesma
    # recusa, mesma frase — não vale um segundo texto para o mesmo fato.)
    "sem_combustivel": "não há material nenhum para acender",
    "nao_queima": "isso não é coisa que pegue fogo",
    "nao_pegou": "a chama não pegou desta vez — o material continua aí",
    "ocupado_para_acender": "já está ocupado com outra coisa",
    # spec 054 — colher. Chave PRÓPRIA (`onde_inacessivel`, não `alvo_inacessivel`
    # — esse nome já colide entre `drink`/`butcher` neste mesmo dicionário, dict
    # literal resolve pelo ÚLTIMO valor; não vale acrescentar um terceiro
    # colidente). A recusa por cooldown (alvo ainda não rebrotado) nunca chega
    # aqui — sai do enum antes, zero LLM (FR-003).
    "onde_inacessivel": "não está ao alcance para colher",
    "sem_vegetacao": "não há nada de verde ali para colher",
    "nada_a_colher": "há verde, mas nada que se aproveite agora",
    # spec 055 — preparar. `ingrediente_inacessivel` é reusado de `cook` (mesmo
    # fato, mesma frase — não vale um segundo texto). `recipiente_inacessivel`
    # é chave PRÓPRIA (não `fonte_calor_inacessivel`, que já é de `cook`).
    "recipiente_inacessivel": "não está ao alcance para preparar",
    "sem_recipiente": "isso não serve de recipiente pra preparar nada",
    "nao_combina": "isso não forma preparo nenhum junto",
    "ja_preparando": "já está com as mãos em outro preparo",
    # spec 059 — escrever. Os dois gates de admissão (superfície, instrumento)
    # e as revalidações de arquivo (item/memória sumiram entre a guarda e a
    # aplicação — raríssimo, fase única).
    "item_sumiu": "o que você ia escrever sumiu da cena",
    "sem_instrumento": "isso não está mais na sua mão",
    "nao_e_superficie": "isso não é algo em que se escreva",
    "nao_serve_pra_escrever": "isso não serve pra escrever",
    "memoria_sumiu": "essa lembrança já não está mais viva",
    "nada_a_escrever": "não há o que escrever",
}


def _rejection(base: dict, rej: dict) -> dict:
    """Anexa o motivo estruturado (regra + valores) e o `why` em prosa curta."""
    return {**base, "regra": rej["regra"], "valores": rej["valores"],
            "why": _WHY_BY_REGRA.get(rej["regra"], rej["regra"])}


def remove_entity(folder: Path) -> None:
    """Apaga a pasta de uma entidade por completo (spec 046, `eat`: item
    totalmente consumido). É a EXCEÇÃO escopada ao Princípio IV (emenda
    2.1.0): só item, só consumo total, só por capacidade que declare essa
    consequência de propósito — personagens e memórias seguem sem exceção
    nenhuma. Remove árvore inteira (item aninhado dentro de item some junto,
    como um bolso costurado na peça)."""
    if folder.exists():
        shutil.rmtree(folder)
        indice.remover(folder)   # PORTA 3


def create_entity(parent_folder: Path, entity_id: str, filename: str,
                  frontmatter_data: dict, body: str) -> Path:
    """Cria uma entidade NOVA (pasta + `.md`) sob `parent_folder` — primeira
    primitiva do projeto que INSTANCIA em vez de mover/consumir/reescrever
    (spec 048, `cook`), simétrica a `remove_entity`. Passa pelo MESMO
    `write_doc` que qualquer outra escrita usa (Princípio VI: mesmo World
    Validator, sem atalho). `entity_id` já vem resolvido pelo CHAMADOR
    (`new_id`, tipicamente) — esta primitiva não inventa id nenhum."""
    dest = parent_folder / entity_id
    if dest.exists():
        raise FileExistsError(f"destino de create_entity já existe: {dest}")
    write_doc(dest / filename, frontmatter_data, body)
    return dest


def _iter_within_location(location_folder: Path, filename: str):
    """`filename` sob `location_folder`, sem cruzar para uma sub-location.

    Uma location pode conter outra location aninhada (cidade contém taverna,
    taverna contém quarto — spec 035): cada `location.md` é a fronteira de uma
    cena própria. Sem essa poda, o rglob antigo vazava itens de uma sub-location
    para a cena de fora (personagem na taverna via/mexia em item do quarto).
    Personagens e objects já não vazavam (o loop de cima é `iterdir`, raso);
    isto traz itens para a mesma disciplina.
    """
    stack = [location_folder]
    first = True
    while stack:
        folder = stack.pop()
        if not first and (folder / "location.md").exists():
            continue
        first = False
        for child in folder.iterdir():
            if child.is_dir():
                stack.append(child)
            elif child.name == filename:
                yield child


def _scene_entities(location_folder: Path) -> tuple[dict, dict, dict]:
    """Personagens, objects e itens presentes na location/rota atual, id -> pasta.

    Base compartilhada (nível 0, spec 025): resolve alvo de mutações e localiza
    itens na cena. Itens contam onde quer que estejam: soltos, dentro de um object
    ou no inventário de um presente. Vive aqui (io) — e não mais em percepcao —
    para que TODO executor a leia fresca sem ciclo de import (Fase C: a tool
    auto-suficiente lê a própria cena por aqui).
    """
    characters, objects = {}, {}
    for child in location_folder.iterdir():
        if not child.is_dir():
            continue
        if (child / "character.md").exists():
            fm, _ = read_doc(child / "character.md")
            if fm.get("id"):
                characters[fm["id"]] = child
        elif (child / "object.md").exists():
            fm, _ = read_doc(child / "object.md")
            # spec 053: extinto continua no disco como vestígio, mas sai da cena — e
            # daqui saem TODOS os enums do Árbitro (cook_fonte, forge_fonte, shove_to,
            # stow_in, open/close, examinar, drink) e o `_entries` de itens/executores.
            # É o choke-point: um dos três pontos de filtro, e o que cobre mais gente.
            if fm.get("id") and not esta_extinto(fm):
                objects[fm["id"]] = child
    items = {}
    for path in _iter_within_location(location_folder, "item.md"):
        fm, _ = read_doc(path)
        if fm.get("id") and not esta_extinto(fm):
            items[fm["id"]] = path.parent
    return characters, objects, items
