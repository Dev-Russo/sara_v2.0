# SARA 2.0 — Convenções

## Linguagem e nomenclatura

- Documentação e mensagens voltadas ao usuário ficam em português.
- Nomes de módulos, classes, campos e comandos ficam em inglês quando forem parte do código ou contrato técnico.
- Funções de domínio usam verbos claros: `create_task`, `reschedule_task`, `confirm_command`.
- Tipos estruturados usam PascalCase: `Task`, `AgentDecision`, `HarnessResult`.
- Constantes usam UPPER_SNAKE_CASE: `ACTIVE_FLOW_STATES`, `CONFIRMATION_TTL`.
- Arquivos Python usam `snake_case` singular quando representam uma entidade: `task.py`, `confirmation_request.py`.
- Comandos usam namespace e verbo: `tasks.create`, `tasks.delete_many`, `reminders.create`.

## Separação de camadas

### Routers

Routers fazem apenas:

- parse e validação do evento de transporte;
- autenticação e autorização de entrada;
- criação de `RequestContext`;
- deduplicação de eventos;
- chamada do Graph;
- conversão do resultado para HTTP ou Telegram.

Routers não importam models para aplicar regra, não instanciam repositories para executar comandos e não chamam o LLM diretamente.

### Agents

Agentes recebem contexto e mensagem, usam o adapter de LLM quando necessário e retornam `AgentDecision`. Não possuem `AsyncSession`, não enviam mensagens e não executam comandos.

### Graph

O Graph controla estado, sequência, pausa, retomada e transição. A lógica de negócio continua em services e Harness.

### Harness

O Harness valida e executa comandos. Toda mutação iniciada por agente passa pela sua interface.

### ResponseAgent

O `ResponseAgent` recebe somente resultados estruturados do Harness e o contexto mínimo necessário para redigir a resposta final. Ele pode usar um LLM para dar naturalidade, mas deve ter fallback determinístico e não pode afirmar efeitos ausentes do `HarnessResult`.

### Services

Services implementam casos de uso de domínio. Recebem dependências por parâmetro ou composição, mantêm transações e devolvem resultados estruturados.

### Repositories

Repositories encapsulam persistência. Devem oferecer interfaces pequenas e assíncronas. Não devem esconder `commit`, disparar Telegram ou interpretar intenções.

### Integrations

Adapters traduzem interfaces internas para APIs externas. Telegram e LLM não devem vazar tipos de SDK para o domínio.

## Assíncrono

- Usar `async def` em routers, Graph, agentes, Harness, services, repositories, scheduler e adapters de rede.
- Usar `SQLAlchemy AsyncSession` e driver async do PostgreSQL.
- Não usar chamadas bloqueantes no event loop.
- Bibliotecas síncronas inevitáveis devem ser isoladas e executadas em mecanismo apropriado, com justificativa.
- Não misturar `Session` síncrona e `AsyncSession` no mesmo caminho de execução.

## Interfaces e módulos profundos

Uma interface inclui tipos, invariantes, erros, ordenação, transação e comportamento de retry. Não considerar apenas a assinatura da função.

Ao criar um módulo, aplicar a seguinte revisão:

- posso reduzir o número de métodos?
- posso esconder mais complexidade dentro do módulo?
- o caller precisa conhecer detalhes de SQL, Telegram ou do provedor de LLM?
- o módulo tem uma seam testável?
- o teste consegue usar a mesma interface que o código de produção?

Não criar uma abstração genérica sem variação real. Quando houver mais de um adapter ou uma necessidade clara de teste/substituição, registrar a seam.

## Schemas e contratos

- `tasks.delete` recebe uma referência textual de tarefa active e sempre cria uma confirmação persistida.
- `tasks.delete_by_id` é interno: o Graph o produz após a seleção e ele também permanece sujeito à confirmação.

- Comandos são discriminados por `type` e payload validado.
- Schemas de entrada e saída são explícitos.
- `dict[str, Any]` não substitui um schema quando o dado atravessa módulos.
- Campos opcionais têm semântica documentada; `null` não significa automaticamente “não alterar”.
- Em `TaskUpdatePayload`, `query` referencia uma tarefa ativa por título ou descrição.
  Campo de alteração omitido significa “não alterar”; `null` explícito limpa somente
  `description`, e título/prioridade não podem ser limpos.
- `tasks.update` altera somente `title`, `description` e `priority`. Datas e horários
  pertencem a `tasks.reschedule`.
- `tasks.update_by_id` é um comando interno do Harness para aplicar uma alteração depois
  que a resolução textual selecionou um único UUID; o agente não deve inventar IDs.
- Mensagens para o usuário não são usadas como fonte de verdade de sucesso.
- `HarnessResult.effect` é a fonte de verdade para a resposta pós-execução.
- Versões de comando devem ser consideradas quando o payload persistir.

## Estado e concorrência

- Estado de fluxo deve ser persistido.
- Contextos JSON precisam de schema e tamanho controlado.
- Uma confirmação pendente é consumida uma única vez.
- A mesma mensagem ou callback pode chegar mais de uma vez; handlers devem ser idempotentes.
- Locks em memória são otimização local, não requisito de correção.

## Banco e transações

- O service controla a unidade transacional.
- Repository não faz commit escondido.
- Toda consulta de domínio filtra por `user_id`.
- Timestamps armazenados devem preservar timezone.
- Mudança de modelo exige migration e teste de migração.
- Queries de lote devem evitar carregar todos os registros em memória sem necessidade.

## Erros

Definir erros de domínio ou códigos estáveis para situações esperadas, como `TASK_NOT_FOUND`, `INVALID_DATE`, `CONFIRMATION_REQUIRED` e `OWNERSHIP_VIOLATION`.

- Erros esperados viram resultados controlados para o usuário.
- Erros inesperados são registrados com `exc_info=True` na borda assíncrona.
- Nunca retornar stack trace, SQL, token ou resposta interna de provedor.
- Falha antes do commit não deve deixar mutação parcial.
- Falha de entrega depois do commit deve ser tratada como falha de entrega, não como falha de domínio.

## Logging e observabilidade

Cada entrada de processo deve carregar `correlation_id` e, quando aplicável, `flow_id`, `graph_thread_id`, `command_id` e `user_id` anonimizado.

Níveis sugeridos:

- `INFO`: início/fim de fluxo, comando aceito, job executado;
- `WARNING`: retry, confirmação expirada, evento duplicado, configuração incompleta;
- `ERROR`: falha inesperada com stack trace;
- `DEBUG`: payloads somente em ambiente local e com dados minimizados.

Não registrar tokens, headers secretos, prompt completo ou conteúdo pessoal completo por padrão.

## Prompts e LLM

- Prompt orienta interpretação e formato; não substitui policy de segurança.
- O schema do comando é a fonte de verdade do payload.
- O LLM não recebe ferramentas que não fazem parte do escopo atual.
- Respostas do LLM devem ser validadas antes de chegar ao Graph.
- Mudança de prompt exige testes de cenários, não apenas inspeção manual.

## Comentários e documentação

Comentar o motivo de uma regra não óbvia, especialmente:

- por que o Supervisor não roda em fluxo ativo;
- por que delete pausa;
- por que a confirmação é persistida;
- por que uma operação é idempotente;
- por que uma integração foi isolada numa seam.
- por que a confirmação entra diretamente no `ConfirmationResolver`/Harness;
- por que o `ResponseAgent` não executa nem autoriza comandos.

Evitar comentários que apenas repetem o nome da função.

## Checklist de revisão

- [ ] O escopo funcional continua restrito a tarefas?
- [ ] A mudança respeita o sentido de dependências?
- [ ] O caminho é async?
- [ ] Mutação passa pelo Harness?
- [ ] Delete/lote tem policy de confirmação?
- [ ] `user_id` vem do contexto confiável?
- [ ] Há idempotência para eventos repetíveis?
- [ ] Há testes na seam correta?
- [ ] Logs e mensagens não expõem dados sensíveis?
