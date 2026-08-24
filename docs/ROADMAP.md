# Roadmap de commits

Este arquivo mantém o próximo passo técnico explícito para preservar a cadência
de um commit por dia. Cada entrega deve ser pequena, testada e limitada a uma
responsabilidade principal.

## Última entrega

### `feat: map Telegram updates to trusted users`

- Concluído.
- Resolver `chat_id` para o `User.id` interno.
- Rejeitar chats privados não autorizados.
- Deduplicar `update_id` com `ProcessedUpdate` dentro de uma transação.
- Criar `MessageEvent` e `ConfirmationEvent` após validar a identidade.
- Manter o Graph fora deste commit.

## Próximo commit

### `feat: connect Telegram ingress to Graph`

- Ler o corpo do webhook e chamar `parse_telegram_update`.
- Encaminhar eventos aceitos pelo `TelegramIngressAdapter` ao Graph.
- Criar `ExecutionContext` com identidade e correlação confiáveis.
- Manter duplicados e chats não autorizados fora do Graph.
- Ainda não enviar respostas pelo Telegram.

## Sequência planejada

1. ~~Adapter de updates Telegram.~~
2. ~~Identidade confiável e deduplicação de updates.~~
3. Chamada do Graph a partir de mensagens Telegram.
4. Envio de `ResponseDecision` pelo `TelegramGateway`.
5. Callbacks de confirmação conectados ao `ConfirmationResolver`.
6. Checkpoint persistido para retomada de fluxos e confirmações.
7. Fluxo de deleção completo pelo Telegram.

## Histórico recente

### `feat: add Telegram update adapter`

- Concluído.
- Parser determinístico para mensagens privadas e callbacks de confirmação.
- Updates de grupos, canais e mídia sem texto permanecem fora do escopo.

## Regra de atualização

Depois de cada commit, mover o item concluído para o histórico e promover o
próximo item para a seção `Próximo commit`. Não incluir alterações prévias de
`AGENTS.md` nesses commits.
