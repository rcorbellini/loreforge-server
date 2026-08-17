"""Camada TOOLS (item 31 §3) — BASE compartilhada do pacote por domínio.

Os registros (HANDLERS/MANIFESTS) e os decorators (tool/manifest) + helpers comuns
(_arb_deny). Cada domínio vive em arbiter_tools/<dominio>.py e registra aqui.
"""
from __future__ import annotations

import motor

HANDLERS: dict = {}


def _arb_deny(ctx, rolled: bool, narr_key: tuple, narr_base: dict, rej: dict):
    """Recusa de tool ARBITRADA vinda do executor (item 31 §2). SEMPRE registra em
    `rejections` para o CLIENT narrar a tentativa frustrada (falhas nunca silenciosas).
    Se `rolled` (o DADO decidiu), o desfecho é segredo do mundo (Princípio IX): devolve
    NEUTRO ao modelo — ele segue, o client narra. Se DETERMINÍSTICO (veredito sem dado),
    sobe ao modelo o motivo, para narrar fiel e travar o veredito único do turno."""
    why = rej.get("why") or motor._WHY_BY_REGRA.get(rej.get("regra"), "não foi possível")
    ctx.rejections[narr_key] = {**narr_base, "regra": rej.get("regra"),
                                "valores": rej.get("valores", {}), "why": why}
    if rolled:
        return {"ok": True, "nota": "o desfecho sai na aplicação"}, False
    return ctx.err(why, rej=(rej if rej.get("regra") else None)), False


def tool(*names):
    """Registra a função como handler de uma ou mais tools (o canal Open/Closed do
    Árbitro: acrescentar tool é registrar, nunca editar o despachante)."""
    def deco(fn):
        for n in names:
            HANDLERS[n] = fn
        return fn
    return deco


def build_face(spec, name: str, scene):
    """Builder de FACE GENÉRICO (spec 038, T021): monta o dict do manifest de UMA
    tool a partir da sua DECLARAÇÃO (`motor.ToolSpec`) + a cena viva — substitui os
    `manifest_X` à mão. Byte-equivalente ao manifest de v2.0.0 (golden).

    Regras de composição:
    - `enum_sources[p]` = chave de `scene.cand` OU callable(scene)->list. O enum é
      injetado no topo do param, OU em `items` se o param é `array` (buy/trade).
    - `omit_if_empty`: param OPCIONAL sem candidato SOME (ex.: attack.arma).
    - `params[p]` pode ser um callable(scene)->schema quando o enum mora FUNDO
      (learn_routes: array de objetos com enum em `items.properties.rota`) — o
      callable devolve o schema pronto; o `enum_sources[p]` (se houver) serve só ao
      GATE.
    - `description` = str OU callable(scene)->str (cita a cena/régua).
    GATE: param OBRIGATÓRIO com fonte-de-enum vazia → a tool some do turno."""
    enums = {p: (src(scene) if callable(src) else scene.cand[src])
             for p, src in spec.enum_sources.items()}
    for pname in spec.required:
        if pname in enums and not enums[pname]:
            return None
    # spec 043: o parâmetro de JUÍZO some da FACE. Ninguém de fora o preenche — nem A
    # Mente nem o Árbitro: a capacidade pergunta a nota ao mundo, com a régua que mora
    # ao lado dela (`ctx.ask`). O que sobra na face é ESCOLHA e VOZ.
    juizo_param = spec.juizo[0] if spec.juizo else None
    props: dict = {}
    for pname, pschema in spec.params.items():
        if pname == juizo_param:
            continue
        if callable(pschema):
            props[pname] = pschema(scene)     # schema pronto (enum já embutido, fundo)
            continue
        if pname not in enums:
            props[pname] = dict(pschema)
            continue
        enum = enums[pname]
        if not enum and pname in spec.omit_if_empty:
            continue
        if pschema.get("type") == "array":
            props[pname] = {**pschema, "items": {**pschema.get("items", {}), "enum": enum}}
        else:
            props[pname] = {**pschema, "enum": enum}
    desc = spec.description(scene) if callable(spec.description) else spec.description
    return {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": [r for r in spec.required if r != juizo_param]},
    }


MANIFESTS: dict = {}


def manifest(*names):
    """Registra a FACE da tool (o dict do manifest do turno). Co-localizada com o
    handler: uma tool nova é UM lugar. `build_tools` (no Árbitro) só monta a cena e
    itera este registro — nunca se edita lá para acrescentar tool (Open/Closed)."""
    def deco(fn):
        for n in names:
            MANIFESTS[n] = fn
        return fn
    return deco


