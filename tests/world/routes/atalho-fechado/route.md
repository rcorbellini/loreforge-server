---
type: route
id: atalho-fechado
name: Atalho Fechado
from: forja-de-ferro
to: mirante-do-corvo
travel_time_base: 5
bidirectional: true
prerequisites:
  - id: precisa-da-chave-do-corvo
    type: item
    required: chave-do-corvo
    deny_reason: o portão do atalho não cede sem a chave certa.
origin: teste
---

Um atalho curto e barrado: sem a chave certa, o portão não cede.
