# Roadmap de commits

Este arquivo mantém o próximo passo técnico explícito para preservar a cadência
de um commit por dia. Cada entrega deve ser pequena, testada e limitada a uma
responsabilidade principal.

## Última entrega

### `feat: add Telegram update adapter`

- Concluído.
- Validar updates recebidos do Telegram com uma função determinística.
- Produzir `TelegramMessageUpdate` para mensagens privadas de texto.
- Produzir `TelegramConfirmationUpdate` para callbacks de confirmação.
- Ignorar grupos, canais e updates de mídia sem texto.
- Não chamar Graph, banco, LLM ou Telegram neste commit.

## Próximo commit

### `feat: map Telegram updates to trusted users`

- Resolver `chat_id` para o `User.id` interno.
- Rejeitar chats privados não autorizados.
- Persistir/deduplicar `update_id` com `ProcessedUpdate`.
- Criar `MessageEvent` e `ConfirmationEvent` somente após a identidade ser
  validada.
- Cobrir ownership e repetição do mesmo update com testes.

## Sequência planejada

1. Adapter de updates Telegram.
2. Identidade confiável e deduplicação de updates.
3. Chamada do Graph a partir de mensagens Telegram.
4. Envio de `ResponseDecision` pelo `TelegramGateway`.
5. Callbacks de confirmação conectados ao `ConfirmationResolver`.
6. Checkpoint persistido para retomada de fluxos e confirmações.
7. Fluxo de deleção completo pelo Telegram.

## Regra de atualização

Depois de cada commit, mover o item concluído para o histórico e promover o
próximo item para a seção `Próximo commit`. Não incluir alterações prévias de
`AGENTS.md` nesses commits.
