"""Parser/emissor de frontmatter — subconjunto de YAML, apenas stdlib.

Loreforge grava o mundo como arquivos `.md` com um bloco de frontmatter entre
`---`. Para respeitar o Princípio I (mínimo de código, sem dependências), este
módulo implementa só o subconjunto de YAML que os schemas do MVP usam:

  - mapeamentos aninhados por indentação (2 espaços)
  - escalares: int, float, bool (true/false), null (null/~), strings
  - strings entre aspas simples ou duplas
  - listas inline: [a, b, c]
  - sequências em bloco de escalares ou de mapeamentos:
        - item
        - chave: valor
          outra: valor
  - comentários de linha inteira e comentários inline iniciados por " #"

Não é um YAML completo; é o suficiente para location/character/route/memory/item.
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# Split / join do documento .md (frontmatter + body)
# --------------------------------------------------------------------------- #

def split(text: str) -> tuple[dict, str]:
    """Separa um documento `.md` em (frontmatter: dict, body: str)."""
    if text.startswith("﻿"):
        text = text.lstrip("﻿")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    fm_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:])
    return parse(fm_text), body.lstrip("\n")


def join(frontmatter: dict, body: str) -> str:
    """Recompoe um documento `.md` a partir de (frontmatter, body)."""
    fm = dump(frontmatter).rstrip("\n")
    body = body.rstrip("\n")
    return f"---\n{fm}\n---\n\n{body}\n"


# --------------------------------------------------------------------------- #
# Parse
# --------------------------------------------------------------------------- #

def parse(text: str) -> dict:
    lines = _clean_lines(text)
    value, _ = _parse_block(lines, 0, 0)
    return value if isinstance(value, dict) else {}


def _clean_lines(text: str) -> list[tuple[int, str]]:
    """Retorna [(indent, conteudo)] ignorando linhas vazias/comentário."""
    out: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = _strip_inline_comment(raw)
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        out.append((indent, stripped.strip()))
    return out


def _strip_inline_comment(line: str) -> str:
    """Remove comentário inline ' #...' respeitando aspas. Comentário de linha
    inteira (começa com #) vira string vazia."""
    in_single = in_double = False
    result = []
    prev = ""
    for ch in line:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and prev in ("", " ", "\t"):
            break
        result.append(ch)
        prev = ch
    return "".join(result)


def _parse_block(lines: list[tuple[int, str]], start: int, indent: int):
    """Faz parse de um bloco (mapa ou sequência) no nível de indentação `indent`.
    Retorna (valor, proximo_indice)."""
    if start >= len(lines):
        return None, start
    first_indent, first_content = lines[start]
    if first_content.startswith("- "):
        return _parse_sequence(lines, start, indent)
    return _parse_mapping(lines, start, indent)


def _parse_mapping(lines, start, indent):
    result: dict = {}
    i = start
    while i < len(lines):
        cur_indent, content = lines[i]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            # não deveria acontecer num mapa bem-formado
            break
        if content.startswith("- "):
            break
        key, sep, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            # valor em bloco aninhado (mapa ou sequência)
            child, i = _parse_child(lines, i + 1, indent)
            result[key] = child if child is not None else None
        else:
            result[key] = _parse_scalar_or_flow(rest)
            i += 1
    return result, i


def _parse_sequence(lines, start, indent):
    result: list = []
    i = start
    while i < len(lines):
        cur_indent, content = lines[i]
        if cur_indent < indent or not content.startswith("- "):
            break
        if cur_indent > indent:
            break
        item_content = content[2:].strip()
        if ":" in item_content and not _looks_like_flow(item_content):
            # item de sequência que é um mapa; a primeira chave vem inline
            # e chaves seguintes vêm indentadas sob o "- "
            inner_lines = [(indent + 2, item_content)]
            j = i + 1
            while j < len(lines) and lines[j][0] > indent and not lines[j][1].startswith("- "):
                inner_lines.append(lines[j])
                j += 1
            mapping, _ = _parse_mapping(inner_lines, 0, indent + 2)
            result.append(mapping)
            i = j
        else:
            result.append(_parse_scalar_or_flow(item_content))
            i += 1
    return result, i


def _parse_child(lines, start, parent_indent):
    """Parse do bloco filho (indentação > parent_indent)."""
    if start >= len(lines):
        return None, start
    child_indent = lines[start][0]
    if child_indent <= parent_indent:
        return None, start
    if lines[start][1].startswith("- "):
        # sequências podem estar no mesmo indent do pai ou maior
        return _parse_sequence(lines, start, child_indent)
    return _parse_mapping(lines, start, child_indent)


def _looks_like_flow(text: str) -> bool:
    return text.startswith("[") or text.startswith("{")


def _parse_scalar_or_flow(text: str):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if inner == "":
            return []
        # recursivo: itens podem ser eles mesmos mapas/listas flow (spec 019, o
        # body {focinho: {capacidade: 1, pega: true}} exige aninhamento inline)
        return [_parse_scalar_or_flow(p.strip()) for p in _split_flow(inner)]
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        out: dict = {}
        if inner:
            for pair in _split_flow(inner):
                k, _, v = pair.partition(":")
                out[k.strip()] = _parse_scalar_or_flow(v.strip())  # valor pode ser flow
        return out
    return _parse_scalar(text)


def _split_flow(inner: str) -> list[str]:
    """Divide 'a, b, [c, d]' por vírgulas de topo (respeita colchetes/aspas)."""
    parts, depth, buf = [], 0, []
    in_single = in_double = False
    for ch in inner:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(buf))
                buf = []
                continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _parse_scalar(text: str):
    text = text.strip()
    if text == "" or text in ("null", "~"):
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        interno = text[1:-1]
        if text[0] == '"':  # desfaz o escape do dump (ver _dump_scalar)
            interno = interno.replace('\\"', '"').replace("\\n", "\n")
        return interno
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


# --------------------------------------------------------------------------- #
# Dump
# --------------------------------------------------------------------------- #

def dump(data: dict, indent: int = 0) -> str:
    lines: list[str] = []
    _dump_mapping(data, indent, lines)
    return "\n".join(lines) + ("\n" if lines else "")


def _dump_mapping(data: dict, indent: int, lines: list[str]) -> None:
    pad = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            if value:
                lines.append(f"{pad}{key}:")
                _dump_mapping(value, indent + 2, lines)
            else:
                lines.append(f"{pad}{key}: {{}}")
        elif isinstance(value, list):
            if _is_scalar_list(value):
                lines.append(f"{pad}{key}: {_dump_flow_list(value)}")
            else:
                lines.append(f"{pad}{key}:")
                # indentado (+2) em relação à chave: parse()/_parse_child exige
                # child_indent > parent_indent para reconhecer o bloco na releitura.
                _dump_sequence(value, indent + 2, lines)
        else:
            lines.append(f"{pad}{key}: {_dump_scalar(value)}")


def _dump_sequence(seq: list, indent: int, lines: list[str]) -> None:
    pad = " " * indent
    for item in seq:
        if isinstance(item, dict):
            inner: list[str] = []
            _dump_mapping(item, indent + 2, inner)
            if inner:
                first = inner[0].lstrip(" ")
                lines.append(f"{pad}- {first}")
                lines.extend(inner[1:])
            else:
                lines.append(f"{pad}- {{}}")
        else:
            lines.append(f"{pad}- {_dump_scalar(item)}")


def _is_scalar_list(seq: list) -> bool:
    return all(not isinstance(x, (dict, list)) for x in seq)


def _dump_flow_list(seq: list) -> str:
    return "[" + ", ".join(_dump_scalar(x) for x in seq) + "]"


def _dump_scalar(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    # QUEBRA DE LINHA nunca pode sair crua: um valor multi-linha vira linhas
    # soltas no meio do frontmatter, e o parser passa a ler o resto como chaves
    # novas — silenciosamente, perdendo tudo o que vinha depois. Foi assim que a
    # ficha de um personagem perdeu `mood` e `conditions`: um narrative_hint com
    # \n foi parar em status.action e cortou o documento ao meio.
    if "\n" in text or "\r" in text:
        text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
        return "\"" + text.replace("\"", "\\\"") + "\""
    # cita quando há caracteres que confundiriam o parser
    if text == "" or text[0] in "[{'\"#-" or ": " in text or text.strip() != text:
        return "\"" + text.replace("\"", "\\\"") + "\""
    return text
