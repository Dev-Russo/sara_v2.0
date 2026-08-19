# SARA 2.0 — Harness Determinístico

## Objetivo

O Harness é a porta única entre uma decisão de agente e uma mutação do sistema. Ele transforma um `Command` em um `CommandResult` somente depois de validar todos os requisitos determinísticos.

O Harness não interpreta linguagem natural e não substitui os agentes. Sua função é garantir que uma intenção já estruturada seja segura, autorizada, válida, idempotente e executada dentro de uma transação.

## Interface principal

```python
async def handle(
    command: Command,
    context: ExecutionContext,
) -> HarnessResult:
    ...
```

O `ExecutionContext` deve ser criado pelo sistema confiável e conter, no mínimo:

```python
class ExecutionContext:
    user_id: UUID
    flow_id: UUID | None
    graph_thread_id: str
    correlation_id: str
    idempotency_key: str
    source: Literal["telegram", "scheduler", "test"]
```

O `user_id` nunca é aceito do payload produzido pelo LLM.

## Resultado do Harness

```python
class HarnessResult:
    status: Literal[
        "executed",
        "awaiting_confirmation",
        "awaiting_selection",
        "rejected",
        "failed",
        "duplicate",
    ]
    command_id: UUID
    command_type: str
    message: str | None
    effect: dict[str, object] | None
    confirmation_id: UUID | None
    error_code: str | None
```

O Graph usa `status` para decidir se pausa ou entrega o resultado ao `ResponseAgent`. O agente não deve inferir sucesso a partir de texto.

`effect` é o payload pós-execução que descreve o que realmente aconteceu. Exemplos:

```json
{
  "status": "executed",
  "command_type": "tasks.create",
  "effect": {
    "kind": "task_created",
    "task_id": "...",
    "title": "Revisar documentação",
    "due_date": "2026-08-19"
  }
}
```

```json
{
  "status": "executed",
  "command_type": "tasks.delete_many",
  "effect": {
    "kind": "tasks_deleted",
    "count": 4,
    "task_ids": ["...", "..."]
  }
}
```

O Harness é a fonte de verdade do efeito. O `ResponseAgent` pode transformar esse payload em linguagem natural, mas não pode acrescentar ações que não estejam nele.

## Pipeline de validação

```text
1. validar tipo e payload do comando
2. encontrar o handler registrado
3. validar contexto e usuário
4. validar alvo e ownership
5. avaliar policy de confirmação
6. verificar idempotency key
7. executar caso de uso em transação
8. registrar resultado
9. devolver resultado estruturado
```

Uma etapa que falha encerra o pipeline. O Harness não “tenta compensar” uma operação parcial sem um caso de uso explícito para isso.

## Catálogo inicial de comandos

| Comando | Uso | Confirmação |
| --- | --- | --- |
| `tasks.create` | Criar uma tarefa. | Não |
| `tasks.list` | Consultar tarefas por período/status. | Não |
| `tasks.complete` | Buscar tarefas pendentes por referência e concluir quando houver um único candidato. | Não |
| `tasks.complete_by_id` | Concluir internamente a tarefa selecionada pelo Graph. | Não |
| `tasks.update` | Editar uma tarefa. | Não |
| `tasks.reschedule` | Alterar data/horário de uma tarefa. | Não |
| `tasks.delete` | Excluir uma tarefa. | Sim |
| `tasks.create_many` | Criar várias tarefas como resultado de planejamento. | Não por padrão; avaliar se o lote for também uma alteração de alto impacto |
| `tasks.complete_many` | Concluir várias tarefas. | Sim |
| `tasks.update_many` | Alterar vários atributos de várias tarefas. | Sim |
| `tasks.reschedule_many` | Remanejar várias tarefas. | Sim |
| `tasks.delete_many` | Excluir várias tarefas. | Sim |
| `reminders.create` | Criar lembrete vinculado a uma tarefa. | Não |
| `reminders.list` | Consultar lembretes da pessoa. | Não |
| `reminders.cancel` | Cancelar um lembrete de tarefa. | Não |

O catálogo deve ser explícito. Um agente não pode inventar um `type` para obter acesso a um handler genérico.

## Policy de confirmação

### Operações obrigatórias

O Harness cria confirmação pendente para:

- exclusão individual;
- exclusão em lote;
- qualquer comando que altere várias tarefas;
- qualquer nova operação marcada como irreversível ou difícil de reverter.

`tasks.create_many` só exige confirmação quando o fluxo ou a policy classificar o lote como alteração de alto impacto. O planejamento comum pode criar várias tarefas após o aceite textual do plano, sem uma segunda confirmação, desde que não altere ou remova tarefas existentes.

### O que a confirmação deve mostrar

O resumo deve ser suficiente para uma decisão consciente:

- ação;
- número de tarefas;
- títulos truncados quando necessário;
- data/horário afetados;
- aviso de irreversibilidade ou escopo;
- prazo de expiração;
- identificador interno não exposto como segredo.

Exemplo:

```text
Excluir 4 tarefas selecionadas?
Essa ação não poderá ser desfeita.

[Confirmar] [Cancelar]
```

### Estado pendente

Uma confirmação pendente contém:

- `confirmation_id`;
- `command_id`;
- snapshot validado do comando;
- `user_id`;
- resumo apresentado;
- estado `pending`, `confirmed`, `cancelled`, `expired` ou `consumed`;
- `expires_at`;
- timestamps.

O comando é consumido no máximo uma vez. Callback duplicado não repete a mutação.

### Confirmação por botão e por texto

O Telegram pode gerar callbacks `confirm:<id>` e `cancel:<id>`. A resposta textual só é considerada confirmação quando existe exatamente uma pendência aplicável para o usuário e o texto é normalizado para uma intenção inequívoca, como `sim`, `confirmar`, `não` ou `cancelar`.

O texto não recria o comando. Ele apenas resolve a pendência já persistida.

## Pós-confirmação e resposta final

O caminho de confirmação é direto:

```text
Telegram callback/text
        ↓
ConfirmationResolver
        ↓
Harness.resolve_confirmation()
        ↓
execução do command snapshot
        ↓
HarnessResult(status="executed", effect=...)
        ↓
ResponseAgent
        ↓
Telegram Adapter
```

O callback não deve voltar ao Supervisor nem chamar novamente o agente que originalmente propôs o comando para “perguntar” o que fazer. Se o fluxo original precisar ser encerrado ou atualizado, essa transição é aplicada depois da execução, usando o `flow_id` persistido.

Para falhas, rejeições e confirmações expiradas, o `ResponseAgent` recebe o mesmo contrato com `status` e `error_code` e produz a resposta correspondente.

## Autorização e ownership

Antes de executar, o Harness deve confirmar que:

- o usuário autenticado é dono dos alvos;
- todos os IDs pertencem ao mesmo usuário;
- o alvo ainda está em estado compatível;
- a confirmação, quando necessária, pertence ao mesmo usuário e comando;
- o comando não está expirado ou já consumido.

Se um lote contiver um alvo inválido, o comportamento padrão é rejeitar o lote inteiro. Não executar parcialmente sem uma policy de negócio explícita.

## Transação e idempotência

O Harness delega a execução ao caso de uso dentro de uma transação controlada pelo service. O repository não deve fazer commit oculto.

Toda execução recebe uma `idempotency_key`. Repetições do mesmo comando devem:

- devolver o resultado já registrado, quando a execução terminou;
- devolver a mesma confirmação pendente, quando ainda aguarda decisão;
- nunca criar uma segunda tarefa, lembrete ou exclusão.

As chaves podem ser derivadas de `update_id`, `callback_query.id`, `command_id` ou de uma chave criada pelo Graph para eventos sem origem Telegram.

## Auditoria

Registrar, no mínimo:

- tipo e versão do comando;
- usuário e origem;
- alvos e resumo seguro;
- resultado;
- código de erro, se houver;
- `correlation_id`, `flow_id` e `graph_thread_id`;
- timestamps de recebimento, confirmação e execução.

O log não precisa guardar a conversa completa nem segredos. Conteúdo pessoal deve ser minimizado e ter retenção definida.

## Erros públicos e internos

O usuário recebe mensagens simples, por exemplo:

- `COMMAND_INVALID`: “Não consegui entender os dados dessa ação.”
- `NOT_FOUND`: “Não encontrei essa tarefa.”
- `NOT_ALLOWED`: “Essa ação não está disponível para esta tarefa.”
- `CONFIRMATION_EXPIRED`: “A confirmação expirou. Posso preparar a ação novamente.”
- `EXECUTION_FAILED`: “Não consegui concluir a ação agora. Nada foi alterado.”

Detalhes de SQL, stack trace, tokens e respostas completas de provedores ficam apenas nos logs protegidos.

## Invariantes

- Nenhuma mutação iniciada por agente contorna o Harness.
- Nenhum delete ou lote de alteração é executado sem confirmação válida.
- Nenhum comando usa `user_id` fornecido pelo agente.
- Nenhuma confirmação é reutilizada.
- Nenhuma resposta de sucesso é enviada antes da persistência confirmada.
- Toda execução concluída produz um `effect` suficiente para o `ResponseAgent` explicar o resultado.
- O resultado de execução é determinístico para a mesma chave de idempotência.

## O que não pertence ao Harness

- decidir se a mensagem do usuário significa “deletar”;
- criar texto conversacional rico;
- construir teclado ou chamar Telegram;
- chamar diretamente o LLM;
- implementar retry de rede de integração;
- guardar estado apenas em memória;
- abrigar policies de finanças, pagamentos ou integrações fora do escopo.
