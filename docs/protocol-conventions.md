# Convenções do Protocolo PayTree

## Folha do Merkle: enviar segredo, não hash

**Padrão adotado:** Na fronteira do protocolo (prover → verifier), enviar o **segredo** (preimagem) da folha, não o hash do segredo.

- **Prover envia:** `secret` + `siblings`
- **Verifier recebe:** `secret`, calcula `leaf_hash = hash_bytes(secret)` e procede com a verificação

O verifier nunca recebe o hash diretamente; ele recebe o segredo e obtém o hash internamente.

### Justificativa

- O segredo pode ser necessário em outros passos do protocolo (ex.: desbloqueio de pagamento).
- Consistência: a prova demonstra conhecimento do preimagem; enviar o preimagem torna isso explícito.
