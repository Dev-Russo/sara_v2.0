# Roadmap de commits

Este arquivo mantém o próximo passo técnico explícito para preservar a
cadência de um commit por dia. Cada entrega deve ser pequena, testada e
limitada a uma responsabilidade principal.

## Última entrega

### `feat: persist Graph checkpoints for Telegram confirmations`

- Concluído.
- Persistir somente o estado de continuação necessário para retomar fluxos e confirmações.
- Reidratar o mesmo thread após reinício sem persistir o resultado transitório do turno.
- Aplicar a mesma seam ao Telegram e ao CLI, preservando ownership e versionamento.

## Próximo commit

### `feat: complete Telegram task deletion flow`

- Exercitar o fluxo completo de exclusão iniciado por mensagem Telegram.
- Retomar confirmação persistida e executar a mutação somente pelo Harness.
- Entregar ao usuário o efeito confirmado, incluindo os casos de cancelamento e erro controlado.

## Sequência planejada

1. ~~Adapter de updates Telegram.~~
2. ~~Identidade confiável e deduplicação de updates.~~
3. ~~Chamada do Graph a partir de mensagens Telegram.~~
4. ~~Envio de `ResponseDecision` pelo `TelegramGateway`.~~
5. ~~Acknowledgement e callbacks de confirmações conectados ao `ConfirmationResolver`.~~
6. ~~Checkpoint persistido para retomada de fluxos e confirmações.~~
7. Fluxo de deleção completo pelo Telegram.

## Histórico recente

### `feat: persist Graph checkpoints for Telegram confirmations`

- Concluído.
- O banco mantém o último snapshot de continuação por thread, com ownership e controle de versão.
- Telegram e CLI reidratam confirmações sem depender de memória local ou de nova chamada ao LLM.

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
