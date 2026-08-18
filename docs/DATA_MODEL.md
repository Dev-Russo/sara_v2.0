# SARA 2.0 — Modelo de Dados

## Princípios

- Todo recurso de negócio pertence a um `user_id`.
- Datas de negócio usam o timezone configurado pelo usuário; timestamps técnicos são armazenados com timezone.
- Estado conversacional e confirmação são duráveis.
- Status derivados, como “atrasada”, devem ser calculados a partir de data e estado sempre que possível.
- Exclusão exige confirmação, mas não cria uma entidade funcional de “lixeira” nesta versão.
- Relações e filtros devem ser indexados para o caminho real de leitura por usuário.

## Entidades principais

### User

Representa a pessoa autorizada a usar a SARA.

Campos mínimos:

| Campo | Regra |
| --- | --- |
| `id` | UUID, chave primária. |
| `timezone` | Obrigatório; padrão configurável. |
| `telegram_chat_id` | Único quando presente. |
| `active` | Controla se o usuário recebe processamento agendado. |
| `created_at`, `updated_at` | Timestamps com timezone. |

O sistema continua otimizado para uso pessoal, mas o `user_id` deve ser aplicado em todas as consultas desde o início.

### Task

Unidade de trabalho do usuário.

Campos mínimos:

| Campo | Regra |
| --- | --- |
| `id` | UUID, chave primária. |
| `user_id` | FK obrigatória para `users`. |
| `title` | Obrigatório, não vazio após normalização. |
| `description` | Opcional. |
| `status` | `active`, `completed` ou `archived`. |
| `priority` | Inteiro binário: `0` para não prioritária ou `1` para prioritária. O padrão é `0`. |
| `due_date` | Data de negócio opcional. |
| `start_at` | Horário opcional, com timezone. |
| `end_at` | Opcional; não pode anteceder `start_at`. |
| `completed_at` | Preenchido quando `status=completed`. |
| `created_at`, `updated_at` | Timestamps com timezone. |

Regras:

- backlog é uma tarefa ativa sem `due_date`;
- atrasada é uma tarefa ativa cuja data ficou antes da data local atual;
- concluída não é reaberta nesta primeira versão sem uma decisão explícita de produto;
- arquivada não aparece nas listas operacionais;
- excluir remove a tarefa e seus lembretes vinculados após confirmação;
- delete em lote é atômico por padrão.

### Reminder

Notificação agendada para uma tarefa.

Campos mínimos:

| Campo | Regra |
| --- | --- |
| `id` | UUID, chave primária. |
| `user_id` | FK obrigatória. |
| `task_id` | FK obrigatória para uma tarefa do mesmo usuário. |
| `remind_at` | Timestamp com timezone. |
| `status` | `scheduled`, `sent`, `cancelled` ou `failed`. |
| `sent_at` | Preenchido quando enviado. |
| `created_at`, `updated_at` | Timestamps. |

O lembrete não é um evento externo nem uma entidade de calendário. Se a necessidade não puder ser relacionada a uma tarefa, ela está fora do escopo atual.

### PlanningSession

Representa um planejamento conversacional para uma data-alvo.

Campos mínimos:

| Campo | Regra |
| --- | --- |
| `id` | UUID. |
| `user_id` | Dono da sessão. |
| `target_date` | Data que será planejada. |
| `status` | `active`, `awaiting_confirmation`, `completed` ou `cancelled`. |
| `context` | JSON estruturado com seleção e proposta atuais. |
| `started_at`, `completed_at` | Timestamps. |

Uma sessão não duplica tarefas automaticamente. O serviço deve identificar tarefas existentes e produzir comandos explícitos de criação ou remanejamento.

### DailyReview

Registro do fluxo de revisão de uma data.

Campos mínimos:

| Campo | Regra |
| --- | --- |
| `id` | UUID. |
| `user_id` | Dono. |
| `review_date` | Data local revisada. |
| `status` | `active`, `completed` ou `cancelled`. |
| `decisions` | JSON reduzido com decisões confirmadas. |
| `started_at`, `completed_at` | Timestamps. |

O registro não deve armazenar uma cópia completa da conversa. A conversa pertence a `ConversationMessage`; a revisão guarda apenas decisões úteis ao domínio.

## Estado de conversação

### ConversationSession

Fonte de verdade do fluxo ativo.

Campos mínimos:

| Campo | Regra |
| --- | --- |
| `id` | UUID. |
| `user_id` | Uma sessão ativa por usuário e canal. |
| `channel` | Inicialmente `telegram`. |
| `flow_type` | `idle`, `task`, `planning`, `review`, `reminder` ou `confirmation`. |
| `current_agent` | Nome registrado do agente. |
| `graph_thread_id` | Identifica o checkpoint do LangGraph. |
| `context` | JSON validado pelo schema do fluxo. |
| `status` | `active`, `paused`, `completed` ou `expired`. |
| `expires_at` | Obrigatório para fluxos interativos. |
| `updated_at` | Usado para concorrência e diagnóstico. |

O estado em memória pode ser um cache, nunca a fonte de verdade para callbacks ou confirmações.

### ConversationMessage

Histórico conversacional sujeito à política de retenção.

Campos mínimos:

- `id`;
- `user_id`;
- `session_id`;
- `role` (`user`, `assistant`, `system` ou `tool`);
- `content`;
- `created_at`;
- `correlation_id`.

Mensagens de ferramenta devem guardar referências estruturadas ao comando, não apenas texto livre, quando houver mutação.

## Segurança operacional

### ConfirmationRequest

Persistência do Human-in-the-Loop.

Campos mínimos:

| Campo | Regra |
| --- | --- |
| `id` | UUID exposto como referência opaca ao canal. |
| `user_id` | Dono da pendência. |
| `command_id` | Comando que aguarda decisão. |
| `command_type` | Tipo registrado no catálogo. |
| `payload_snapshot` | Payload validado, imutável após criação. |
| `summary` | Texto seguro apresentado ao usuário. |
| `status` | `pending`, `confirmed`, `cancelled`, `expired` ou `consumed`. |
| `expires_at` | Prazo da confirmação. |
| `resolved_at` | Preenchido ao resolver. |

O snapshot evita que um callback execute uma versão alterada do comando.

### CommandExecution

Auditoria e idempotência de comandos.

Campos mínimos:

- `id` e `idempotency_key` único;
- `user_id`;
- `command_type` e `command_version`;
- `source`;
- `flow_id`, `graph_thread_id`, `correlation_id`;
- `status` (`received`, `awaiting_confirmation`, `executed`, `rejected`, `failed`);
- `effect_payload` JSON com o efeito confirmado da execução, quando houver;
- `target_summary` sem conteúdo excessivo;
- `result_summary`;
- `created_at`, `completed_at`.

### ProcessedUpdate

Deduplicação de eventos do Telegram.

Campos mínimos:

- `update_id` único;
- `user_id` ou `telegram_chat_id`;
- `event_type`;
- `received_at`;
- `processed_at`;
- `status`.

O registro deve ser gravado de forma segura contra corrida. Falha ao deduplicar não deve ser tratada como se a atualização tivesse sido processada.

## Relações

```text
User
├── Tasks
│   └── Reminders
├── PlanningSessions
├── DailyReviews
├── ConversationSessions
│   └── ConversationMessages
├── ConfirmationRequests
└── CommandExecutions
```

## Índices e restrições essenciais

- `tasks(user_id, status, due_date)`;
- `tasks(user_id, updated_at)`;
- `reminders(user_id, status, remind_at)`;
- `conversation_sessions(user_id, channel, status)`;
- `confirmation_requests(user_id, status, expires_at)`;
- `command_executions(idempotency_key)` único;
- `processed_updates(update_id)` único;
- foreign keys sempre acompanhadas de filtro por `user_id` na camada de aplicação.

## Migrações

Cada alteração persistente exige:

1. atualização do model;
2. migration Alembic reversível quando possível;
3. atualização do repository e schemas;
4. teste em banco vazio;
5. teste de compatibilidade com dados relevantes existentes.
