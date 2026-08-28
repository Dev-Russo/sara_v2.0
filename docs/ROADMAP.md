# Roadmap de commits

Este arquivo mantém o próximo passo técnico explícito para preservar a
cadência de um commit por dia. Cada entrega deve ser pequena, testada e
limitada a uma responsabilidade principal.

## Última entrega

### `feat: connect Telegram callback acknowledgements`

- Concluído.
- Responder callbacks com `answerCallbackQuery`.
- Confirmar e cancelar pendências pelo caminho determinístico do `ConfirmationResolver`.
- Manter callbacks fora do Supervisor e sem nova interpretação do LLM.

## Próximo commit

### `feat: persist Graph checkpoints for Telegram confirmations`

- Persistir o estado necessário para retomar fluxos e confirmações após reinício.
- Retomar o mesmo checkpoint sem reexecutar a interpretação do LLM.
- Manter ownership, idempotência e consumo único da confirmação.

## Sequência planejada

1. ~~Adapter de updates Telegram.~~
2. ~~Identidade confiável e deduplicação de updates.~~
3. ~~Chamada do Graph a partir de mensagens Telegram.~~
4. ~~Envio de `ResponseDecision` pelo `TelegramGateway`.~~
5. ~~Acknowledgement e callbacks de confirmações conectados ao `ConfirmationResolver`.~~
6. Checkpoint persistido para retomada de fluxos e confirmações.
7. Fluxo de deleção completo pelo Telegram.

## Histórico recente

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
