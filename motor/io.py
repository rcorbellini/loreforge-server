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


def _entity_file(folder: Path) -> Path | None:
    """Retorna o arquivo de definição de uma pasta de entidade, se houver."""
    for fname in ENTITY_FILENAMES:
        candidate = folder / fname
        if candidate.exists():
            return candidate
    return None


def read_doc(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    return frontmatter.split(text)


def _is_valid(fm: dict) -> bool:
    """True se o frontmatter passa no World Validator (usado nas leituras)."""
    return validator.validate(fm) == []


def find_character_folder(character_id: str) -> Path:
    for path in WORLD_DIR.rglob("character.md"):
        fm, _ = read_doc(path)
        if fm.get("id") == character_id:
            errors = validator.validate(fm)
            if errors:  # não se guia um personagem com arquivo inválido (FR-010)
                raise MotorError(
                    f"personagem '{character_id}' tem arquivo inválido: "
                    + "; ".join(errors)
                )
            return path.parent
    raise MotorError(f"personagem não encontrado: '{character_id}'.")


def find_entity(entity_id: str) -> tuple[Path, dict, str] | None:
    """Procura qualquer entidade por id em todo o mundo."""
    for fname in ENTITY_FILENAMES:
        for path in WORLD_DIR.rglob(fname):
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


_MUTABLE_ROOT_BY_KIND = {"character": "status", "object": "state", "item": "state"}


_IMMUTABLE_ROOTS_BY_KIND = {
    "character": {"attributes", "skills", "id", "name", "type", "controlled_by"},
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
    "rota_indisponivel": "esse caminho não se abre a ele",
    "ataque_errou": "o golpe passou ao largo",
    "golpe_absorvido": "o golpe acertou, mas a proteção segurou",
    "alvo_ja_morto": "já não há o que ferir",
    "atacante_caido": "não tem como agir agora",
    "ja_dormindo": "já está dormindo",
    "nao_esta_dormindo": "não está dormindo",
    "rest_sem_op": "não ficou claro se era deitar ou despertar",
    "sem_alvo_valido": "não há quem golpear ao alcance",
    "peso_excede_arrasto": "não consegue arrastar esse corpo nem um palmo",
    "alvo_resistiu": "ele se soltou e não vai a lugar nenhum",
    "alvo_desacordado": "não se convence quem não ouve",
    "item_nao_e_do_alvo": "isso não é dele para entregar",
    "destino_e_o_dono": "não faz sentido pedir que ele dê a si mesmo",
    "nada_a_ceder": "ele não abre mão disso de jeito nenhum",
    "nao_cedeu": "ele ouviu, pensou, e não se desfez do que é seu",
    "furto_impossivel": "não há como tirar isso dele sem que perceba",
    "valor_insuficiente": "o que você oferece não paga isso",
    "necessidade_insuficiente": "ele não precisa disso o bastante para abrir mão do que é dele",
    "rota_inexistente": "esse caminho não existe em lugar nenhum",
    "leitura_falhou": "os rabiscos não se deixaram entender",
    "informante_indisponivel": "não há como perguntar a quem não pode responder",
    "recusou_informar": "ele não quis dizer",
    "nao_confiou": "ela não quis abrir o que sabe",
    "nada_a_contar": "disso ela nada sabe",
    "informante_nao_sabe": "esse caminho ele próprio não sabe fazer",
    "fonte_omitida": "isso não foi lido em parte alguma — alguém o disse",
    "citacao_nao_confere": "isso não está escrito aí",
    "nada_a_examinar": "não há nada escrito aí para se debruçar",
    "nao_esta_a_venda": "isso não está à venda",
    "nao_e_negociavel": "disso ele não abre mão",
    "item_nao_e_seu": "isso não está com quem oferece",
    "sem_espaco_para_receber": "não há como levar tudo isso",
    "pagamento_nao_e_dinheiro": "isso não é moeda que se aceite",
    "parceiro_incapaz": "não está em condições de negociar",
    "destino_ocupado": "não há onde pôr isso sem confundir com outra coisa",
    "caminho_desconhecido": "você não sabe como chegar lá",
    "ja_esta_la": "você já está onde queria chegar",
    "viagem_interrompida": "a jornada parou antes do fim",
    "descansando": "você está dormindo — precisa acordar antes de agir",
    "alvo_nao_caido": "não há o que socorrer — ele já pode agir sozinho",
    "nao_possui_item": "isso não está com quem age — pegue antes de entregar ou largar",
    "item_vestido": "isso está vestido no corpo — precisaria tirar antes",
    "item_carregado": "isso está com alguém — empurra-se só o que ninguém carrega",
    "item_alheio": "isso está com outra pessoa — pegue antes de vestir",
    "nao_vestido_em_voce": "isso não está vestido em quem age — não há o que tirar",
    "nao_comestivel": "isso não é algo que se coma",
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
            if fm.get("id"):
                objects[fm["id"]] = child
    items = {}
    for path in _iter_within_location(location_folder, "item.md"):
        fm, _ = read_doc(path)
        if fm.get("id"):
            items[fm["id"]] = path.parent
    return characters, objects, items
