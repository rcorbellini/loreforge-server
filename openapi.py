"""OpenAPI 3.1 GERADO do código — a fronteira HTTP e o catálogo de capacidades.

Por que gerado e não escrito: um contrato escrito à mão diverge do código no primeiro
dia agitado, e o projeto já pagou esse preço uma vez (o `portal/rules.json` existia só
para carregar uma SEGUNDA cópia do texto das capacidades, com um `sync.py` inteiro
para detectar quando ela divergia). Aqui não há cópia: os paths saem do despacho de
`app.py` e as capacidades saem de `motor.registro.specs()`, que é a mesma fonte que a
engine usa para montar o manifesto do turno. Não existe estado em que a doc esteja
certa e o código errado.

O QUE ISTO NÃO É: não é a face exposta à Mente. É a visão do MANTENEDOR — mostra
inclusive o que a fronteira retém (Princípio IX). Cada parâmetro leva `x-classe`, e é
por ela que se AUDITA a fronteira a olho nu: nada marcado `juizo` ou `sistema` pode
aparecer no que desce ao client.

`x-classe` é DERIVADA, nunca declarada à parte (spec 043, o veredito de "Estruturado vs
Descritivo"): um campo de visibilidade seria uma segunda fonte de verdade sobre o mesmo
fato, e no dia em que divergisse da realidade venceria calado.
"""
from __future__ import annotations

import motor
from version import __version__

def _classe(tool: str, param: str, spec) -> str:
    """ESCOLHA · VOZ · JUIZO · SISTEMA — as quatro classes da spec 043.

    O JUÍZO sai da DECLARAÇÃO da capacidade (`juizo=((param, RÉGUA), ...)`, spec 046),
    não de uma lista de nomes nem da forma do schema: é o mesmo dado que faz o
    parâmetro sumir da face e a capacidade pedir a nota ao mundo. Uma fonte, três
    consequências.
    """
    if spec.interna:
        return "sistema"
    if any(p == param for p, _ in spec.juizo):
        return "juizo"
    if param in ("content", "summary", "expectativa", "reason", "narrative_hint",
                 "trecho", "sobre"):
        return "voz"
    return "escolha"


def _capacidades() -> dict:
    """Uma entrada por capacidade: descrição player-facing + params classificados."""
    vistos, out = set(), {}
    ativas = motor.ativacao.active_tool_ids()
    for nome, spec in motor.registro.specs().items():
        if id(spec) in vistos:
            continue
        vistos.add(id(spec))
        for n in spec.names:
            desc = spec.description
            props = {}
            for p, sch in spec.params.items():
                # schema que depende da cena vira um marcador honesto: o enum real só
                # existe com um lugar e um elenco na frente.
                base = ({"type": "string", "description": "enum montado da cena viva"}
                        if callable(sch) else dict(sch))
                base["x-classe"] = _classe(n, p, spec)
                if p in spec.enum_sources:
                    base.setdefault("description", "")
                    base["x-fonte-de-enum"] = (
                        spec.enum_sources[p] if isinstance(spec.enum_sources[p], str)
                        else "(derivado da cena)")
                props[p] = base
            out[n] = {
                "type": "object",
                "title": n,
                "description": (desc if isinstance(desc, str)
                                else "(a descrição cita a cena; resolvida por turno)"),
                "properties": props,
                "required": list(spec.required),
                "x-ativa-neste-mundo": ativas is None or n in ativas,
                "x-expoe-a-mente": not spec.interna,
                "x-consulta": False,
            }
    # A LANE DE CONSULTA também é capacidade — e o contrato tem de dizê-la, senão a
    # bancada mente por omissão. Este arquivo tinha a MESMA cegueira que a face
    # tinha: iterava só `registro.specs()` (mutação), e `consult_specs()` é um
    # dicionário separado. Sem isto, o filtro por personagem do `spec.html`
    # esconderia as duas consultas — elas estariam na face e sem ficha para mostrar.
    for nome, spec in motor.consult_specs().items():
        out[nome] = {
            "type": "object",
            "title": nome,
            "description": spec.description or "",
            "properties": {p: {**dict(sch), "x-classe": "escolha"}
                           for p, sch in (spec.params or {}).items()},
            "required": list(spec.params or {}),
            # fora do manifesto de ativação de propósito (ver `face._consultas`):
            # perguntar não muda o mundo, então não há o que um mundo desligue.
            "x-ativa-neste-mundo": True,
            "x-expoe-a-mente": True,
            "x-consulta": True,
        }
    return out


def _q(nome: str, obrig: bool = True, desc: str = "") -> dict:
    return {"name": nome, "in": "query", "required": obrig,
            "schema": {"type": "string"}, "description": desc}


_OK = {"200": {"description": "ok", "content": {"application/json": {}}}}


def _paths() -> dict:
    cid = _q("character_id", True, "id do personagem que percebe/age")
    return {
        "/api/characters": {"get": {
            "summary": "Quem existe no mundo", "tags": ["mundo"], "responses": _OK}},
        "/api/context": {"get": {
            "summary": "A cena como o personagem a percebe",
            "description": ("O que ELE percebe agora — já recortado contra metagaming. "
                            "É daqui que a Mente tira tudo o que sabe."),
            "tags": ["percepção"], "parameters": [cid], "responses": _OK}},
        "/api/character": {"get": {
            "summary": "A ficha de um personagem", "tags": ["percepção"],
            "parameters": [cid], "responses": _OK}},
        "/api/inventory": {"get": {
            "summary": "O que ele carrega", "tags": ["percepção"],
            "parameters": [cid], "responses": _OK}},
        "/api/entity": {"get": {
            "summary": "Detalhe de uma entidade", "tags": ["percepção"],
            "parameters": [_q("id", True, "id da entidade")], "responses": _OK}},
        "/api/observe": {"get": {
            "summary": "Olhar para algo ao alcance", "tags": ["percepção"],
            "parameters": [cid, _q("id", True, "o que se observa")], "responses": _OK}},
        "/api/known_routes": {"get": {
            "summary": "O mapa que ele traz na cabeça",
            "description": "Só o que ELE lembra — dois personagens no mesmo lugar veem mapas diferentes.",
            "tags": ["percepção"], "parameters": [cid], "responses": _OK}},
        "/api/proficiencies": {"get": {
            "summary": "O que ele sabe fazer, por prática",
            "description": "Derivado da memória; é a percepção dele sobre si mesmo.",
            "tags": ["percepção"], "parameters": [cid], "responses": _OK}},
        "/api/consult": {"get": {
            "summary": "Consultas que a Mente PUXA (read-only)",
            "description": "Despacho genérico: uma consulta nova não toca este endpoint.",
            "tags": ["percepção"],
            "parameters": [_q("tool", True, "nome da consulta"),
                           _q("character_id", False)], "responses": _OK}},
        "/api/world/health": {"get": {
            "summary": "Saúde do mundo (schema dos .md)", "tags": ["mundo"],
            "responses": _OK}},
        "/api/spec": {"get": {
            "summary": "Este documento", "tags": ["mundo"], "responses": _OK}},
        "/api/act": {"post": {
            "summary": "A ÚNICA via de escrita",
            "description": ("Recebe uma INTENÇÃO — nunca um efeito, nunca um valor já "
                            "resolvido. Toda tradução de intenção em efeito acontece "
                            "do lado autoritativo (Princípio III)."),
            "tags": ["ação"],
            "requestBody": {"required": True, "content": {"application/json": {
                "schema": {"type": "object",
                           "properties": {
                               "character_id": {"type": "string"},
                               "intent": {"type": "object",
                                          "description": "a intenção em prosa"},
                               "origem": {"type": "string",
                                          "enum": ["manual", "autonoma"]},
                               "plano": {"type": "object",
                                         "description": "telemetria (modo sombra)"}},
                           "required": ["character_id", "intent"]}}}},
            "responses": _OK}},
    }


def gerar() -> dict:
    caps = _capacidades()
    juizo = sorted({f"{n}.{p}" for n, c in caps.items()
                    for p, s in c["properties"].items()
                    if s.get("x-classe") == "juizo"})
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Loreforge — a fronteira do mundo",
            "version": __version__,
            "description": (
                "Gerado do código a cada chamada; não existe cópia a dessincronizar.\n\n"
                "**Como ler `x-classe`** (spec 043, Princípio IX — Escolha × Juízo):\n\n"
                "- `escolha` — quem, o quê, para onde. É a agência do personagem: DESCE.\n"
                "- `voz` — o conteúdo narrativo que só ele tem: DESCE.\n"
                "- `juizo` — a nota lida de uma régua em prosa. **Nunca desce**: pedir "
                "ao personagem que pontue o próprio desfecho, ou a boa vontade alheia, "
                "é o que o princípio existe para impedir.\n"
                "- `sistema` — o peso e a duração do que fica gravado. **Nunca desce**: "
                "é a caneta do mundo, não agência de ninguém.\n\n"
                "Esta é a visão do MANTENEDOR — mostra inclusive o que a fronteira "
                "retém. A face que a Mente recebe é esta menos `juizo` e menos as "
                "capacidades de `sistema`."),
        },
        "servers": [{"url": "/", "description": "o próprio server do mundo"}],
        "tags": [
            {"name": "percepção", "description": "leitura do que o personagem percebe"},
            {"name": "ação", "description": "a única via de escrita"},
            {"name": "mundo", "description": "metadados e saúde"},
        ],
        "paths": _paths(),
        "components": {"schemas": caps},
        "x-capacidades": {
            "total": len(caps),
            "expostas": sum(1 for c in caps.values() if c["x-expoe-a-mente"]),
            "internas": sorted(n for n, c in caps.items() if not c["x-expoe-a-mente"]),
            "consultas": sorted(n for n, c in caps.items() if c["x-consulta"]),
            "params_de_juizo": juizo,
        },
    }
