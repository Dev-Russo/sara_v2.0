# Roadmap de commits

Este arquivo mantém o próximo passo técnico explícito para preservar a
cadência de um commit por dia. Cada entrega deve ser pequena, testada e
limitada a uma responsabilidade principal.

## Última entrega

### `feat: complete Telegram task deletion flow`

- Concluído.
- Exclusão individual iniciada por mensagem Telegram percorre ingress, Graph persistente,
  Harness, confirmação e entrega.
- Confirmações sobrevivem ao reinício do runner e callbacks não repetem a mutação.
- Cancelamento e confirmação expirada retornam efeitos controlados sem alterar a tarefa.

## Próximo commit

Ainda não definido; revisar a próxima fatia do ciclo Telegram.

## Sequência planejada

1. ~~Adapter de updates Telegram.~~
2. ~~Identidade confiável e deduplicação de updates.~~
3. ~~Chamada do Graph a partir de mensagens Telegram.~~
4. ~~Envio de `ResponseDecision` pelo `TelegramGateway`.~~
5. ~~Acknowledgement e callbacks de confirmações conectados ao `ConfirmationResolver`.~~
6. ~~Checkpoint persistido para retomada de fluxos e confirmações.~~
7. ~~Fluxo de deleção completo pelo Telegram.~~

## Histórico recente

### `feat: persist Graph checkpoints for Telegram confirmations`

- Concluído.
- O banco mantém o último snapshot de continuação por thread, com ownership e controle de versão.
- Telegram e CLI reidratam confirmações sem depender de memória local ou de nova chamada ao LLM.

### `feat: complete Telegram task deletion flow`

- Concluído.
- O fluxo HTTP integrado valida confirmação, retomada após reinício, cancelamento,
  expiração e idempotência sem chamar Telegram ou LLM reais.

### `feat: connect Telegram callback acknowledgements`

- Concluído.
- O webhook reconhece callbacks e mantém confirmações no caminho determinístico do Harness.

### `feat: deliver Telegram responses through TelegramGateway`

- Concluído.
- O webhook entrega respostas após o Graph e reprocessa somente snapshots pendentes.

### `feat: connect Telegram ingress to Graph`

- Concluído.
- O webhook interpreta updates, valida o ingresso confiável e encaminha eventos aceitos ao Graph.

### `feat: map Telegram updates to trusted users`

- Concluído.
- O ingresso resolve identidade, deduplica updates e cria eventos internos.

### `feat: add Telegram update adapter`

- Concluído.
- Parser determinístico para mensagens privadas e callbacks de confirmação.
- Updates de grupos, canais e mídia sem texto permanecem fora do escopo.

## Regra de atualização

Depois de cada commit, mover o item concluído para o histórico e promover o
próximo item para a seção `Próximo commit`. Não incluir alterações prévias de
`AGENTS.md` nesses commits.
