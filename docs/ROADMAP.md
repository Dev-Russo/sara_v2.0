# Roadmap de commits

Este arquivo mantém o próximo passo técnico explícito para preservar a
cadência de um commit por dia. Cada entrega deve ser pequena, testada e
limitada a uma responsabilidade principal.

## Última entrega

### `feat: deliver Telegram responses through TelegramGateway`

- Concluído.
- Transformar o `ResponseDecision` devolvido pelo Graph em mensagem do Telegram.
- Usar o `TelegramGateway` como única porta de saída.
- Enviar respostas somente após o processamento do Graph.
- Persistir snapshots de entrega e repetir apenas entregas pendentes.
- Exibir teclado inline para confirmações sem alterar o contrato do domínio.

## Próximo commit

### `feat: connect Telegram callback acknowledgements`

- Responder callbacks com `answerCallbackQuery`.
- Confirmar e cancelar pendências pelo caminho determinístico do `ConfirmationResolver`.
- Manter callbacks fora do Supervisor e sem nova interpretação do LLM.

## Sequência planejada

1. ~~Adapter de updates Telegram.~~
2. ~~Identidade confiável e deduplicação de updates.~~
3. ~~Chamada do Graph a partir de mensagens Telegram.~~
4. ~~Envio de `ResponseDecision` pelo `TelegramGateway`.~~
5. Acknowledgement e callbacks de confirmações conectados ao `ConfirmationResolver`.
6. Checkpoint persistido para retomada de fluxos e confirmações.
7. Fluxo de deleção completo pelo Telegram.

## Histórico recente

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
