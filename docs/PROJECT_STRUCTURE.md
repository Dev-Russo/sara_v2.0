# SARA 2.0 — Estrutura do Projeto

## Estrutura proposta

```text
.
├── app/
│   ├── main.py
│   ├── cli.py
│   ├── runtime.py
│   ├── config.py
│   ├── api/
│   │   └── routers/
│   │       ├── health.py
│   │       └── telegram.py
│   ├── agents/
│   │   ├── base.py
│   │   ├── supervisor.py
│   │   ├── task.py
│   │   ├── planning.py
│   │   ├── review.py
│   │   ├── reminder.py
│   │   └── response.py
│   ├── graph/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── routing.py
│   │   ├── confirmation_resolver.py
│   │   ├── builder.py
│   │   └── visualization.py
│   ├── harness/
│   │   ├── service.py
│   │   ├── handlers.py
│   │   ├── policies.py
│   │   ├── confirmation.py
│   │   ├── registry.py
│   │   └── results.py
│   ├── models/
│   │   ├── user.py
│   │   ├── task.py
│   │   ├── reminder.py
│   │   ├── planning_session.py
│   │   ├── daily_review.py
│   │   ├── conversation_session.py
│   │   ├── confirmation_request.py
│   │   ├── command_execution.py
│   │   └── processed_update.py
│   ├── schemas/
│   │   ├── commands.py
│   │   ├── decisions.py
│   │   ├── results.py
│   │   ├── events.py
│   │   ├── tasks.py
│   │   └── confirmations.py
│   ├── repositories/
│   │   ├── interfaces.py
│   │   ├── task_repository.py
│   │   ├── user_repository.py
│   │   ├── processed_update_repository.py
│   │   ├── command_execution_repository.py
│   │   ├── reminder_repository.py
│   │   ├── session_repository.py
│   │   └── confirmation_repository.py
│   ├── services/
│   │   ├── tasks.py
│   │   ├── planning.py
│   │   ├── review.py
│   │   └── reminders.py
│   ├── integrations/
│   │   ├── telegram/
│   │   │   ├── adapter.py
│   │   │   ├── ingress.py
│   │   │   ├── keyboards.py
│   │   │   ├── messages.py
│   │   │   └── updates.py
│   │   └── llm/
│   │       ├── interface.py
│   │       └── anthropic_adapter.py
│   ├── scheduler/
│   │   ├── jobs.py
│   │   └── idempotency.py
│   ├── db/
│   │   ├── session.py
│   │   ├── metadata.py
│   │   └── migrations/
│   └── observability/
│       ├── logging.py
│       ├── metrics.py
│       └── correlation.py
├── tests/
│   ├── unit/
│   ├── component/
│   ├── integration/
│   └── e2e/
├── alembic/
│   └── versions/
│       ├── 0001_create_users_tasks_and_executions.py
│       ├── 0002_add_confirmation_requests.py
│       └── 0003_add_processed_updates.py
├── scripts/
├── docs/
│   ├── PROJECT_CONTEXT.md
│   ├── ARCHITECTURE.md
│   ├── PROJECT_STRUCTURE.md
│   ├── HARNESS.md
│   ├── DATA_MODEL.md
│   ├── CONVENTIONS.md
│   ├── TESTING.md
│   ├── DEVELOPMENT.md
│   └── ROADMAP.md
├── requirements.txt
├── docker-compose.yaml
├── AGENTS.md
└── README.md
```

## Regras de dependência

```text
routers → graph → agents/harness/services → repositories → db
scheduler → graph
integrations → adapters das interfaces internas
models/schemas → não dependem de routers ou integrações
```

O sentido da seta indica uso. Um módulo inferior não deve importar um módulo superior só para reutilizar uma função conveniente.

## Onde colocar código novo

### Nova rota HTTP ou webhook

Adicionar um router em `app/api/routers/`, definir schemas em `app/schemas/` quando forem reutilizados e encaminhar o evento ao Graph. A rota não pode acessar repository ou model diretamente.

### Novo comando de tarefa

1. Definir o payload tipado em `app/schemas/commands.py`.
2. Registrar o tipo no catálogo do Harness.
3. Implementar ou reutilizar o caso de uso em `app/services/tasks.py`.
4. Adicionar policy de confirmação, se necessário.
5. Expor o comando ao agente adequado.
6. Cobrir Harness, serviço e fluxo conversacional.

### Novo agente

Adicionar um módulo em `app/agents/`, implementar a interface comum e registrar o agente no Supervisor/Graph. O agente deve retornar `AgentDecision` e não pode executar efeitos colaterais diretamente. O `ResponseAgent` é uma exceção de posição no fluxo, não de autoridade: ele recebe `HarnessResult` e apenas produz a resposta final.

### Novo fluxo agendado

Adicionar um job em `app/scheduler/jobs.py`, produzir um evento idempotente e iniciar o Graph. O job não deve duplicar regras existentes em `services/`.

### Alteração de banco

Alterar model, migration, repository e testes na mesma mudança. A migration deve funcionar em banco vazio e em banco com dados compatíveis.

## Arquivos que devem permanecer simples

- `main.py`: composição da aplicação e lifecycle.
- routers: transporte e autenticação.
- `graph/builder.py`: composição do Graph.
- adapters de integração: conversão de protocolo.

Se a regra começar a crescer nesses arquivos, movê-la para um módulo com interface própria.

## Limites de contexto

O domínio de tarefas é o contexto atual. Planejamento, revisão e lembretes são casos de uso sobre tarefas, não domínios externos independentes. Não criar módulos de finanças, calendário ou mensagens de terceiros para “deixar pronto”.
