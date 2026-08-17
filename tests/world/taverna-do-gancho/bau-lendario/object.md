---
type: object
id: bau-lendario
name: Baú Lendário
state:
  fechado: true
locks:
  open:
    - {type: item, required: chave-de-ferro}
    - {type: item, required: chave-de-prata, deny_reason: "a segunda fechadura, prateada, não cede"}
  close:
    - {type: item, required: chave-de-ferro}
origin: editorial
---

Um baú de madeira negra cintado em ferro e prata, com duas fechaduras lado a
lado — uma escura, uma clara. Ninguém na taverna lembra de tê-lo visto aberto.
