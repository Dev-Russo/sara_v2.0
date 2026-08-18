# SARA 2.0 — Contexto do Projeto

## Propósito

SARA é uma assistente pessoal conversacional, inicialmente operada pelo Telegram, que ajuda o usuário a transformar mensagens naturais em tarefas executáveis. A SARA deve responder com clareza, manter o contexto do fluxo atual e nunca afirmar que uma ação foi executada quando ela não foi confirmada pelo sistema.

Este documento registra o contexto funcional e o vocabulário da SARA 2.0. A implementação descrita em `sources/` é referência histórica da SARA atual; estes documentos definem o alvo da 2.0.

## Escopo atual

O primeiro ciclo da SARA 2.0 cobre somente:

- criação, consulta, conclusão, edição e exclusão de tarefas;
- organização de tarefas por data, prioridade e status;
- planejamento do próximo dia;
- remanejamento de tarefas para outra data ou horário;
- revisão diária das tarefas do usuário;
- lembretes vinculados a tarefas;
- conversação necessária para executar esses fluxos;
- confirmação humana para exclusões e alterações em massa.

O sistema é multi-agent, mas continua sendo um modular monolith. O objetivo é separar responsabilidades e contratos, não distribuir o sistema em microserviços.

## Fora do escopo funcional

Não fazem parte desta versão:

- gastos, orçamento, controle financeiro ou qualquer recurso bancário;
- pagamentos, transferências ou ações financeiras externas;
- envio de mensagens ou e-mails para terceiros;
- cancelamento de compromissos externos;
- Google Calendar ou outras agendas externas;
- colaboração, times, workspaces compartilhados ou permissões complexas;
- hábitos, Pomodoro, notas, busca semântica, RAG ou automações não relacionadas a tarefas;
- integrações futuras que não sejam necessárias para os fluxos acima.

Esses temas podem aparecer em decisões de extensibilidade, mas não devem gerar tabelas, capabilities, policies, prompts ou agentes nesta etapa.

## Objetivos de produto

1. Capturar uma tarefa em linguagem natural com baixa fricção.
2. Deixar claro o que será feito, o que foi apenas proposto e o que foi realmente executado.
3. Manter um fluxo conversacional ativo sem reclassificar toda mensagem pelo Supervisor.
4. Permitir planejamento e remanejamento sem duplicar tarefas acidentalmente.
5. Tornar operações destrutivas previsíveis, auditáveis e sempre confirmadas.
6. Manter o estado recuperável após reinício do processo.

## Decisões consolidadas

### Roteamento e troca de agente

O Supervisor/Router classifica a intenção somente quando não há um fluxo ativo. Enquanto houver um fluxo ativo, a mensagem é entregue ao agente responsável por esse fluxo.

A troca ocorre apenas quando:

- o agente encerra o fluxo;
- o usuário cancela explicitamente;
- o usuário pede uma mudança inequívoca de contexto;
- uma confirmação pendente é resolvida.

Exemplo:

```text
Usuário: quero planejar amanhã
→ Supervisor → PlanningAgent

Usuário: vou à academia às 18h
→ PlanningAgent

Usuário: na verdade às 19h
→ PlanningAgent

Usuário: esquece o planejamento, quero ver minhas tarefas
→ encerra o planejamento → Supervisor → TaskAgent
```

### Contrato dos agentes

Todos os agentes retornam o mesmo envelope lógico:

```python
class AgentDecision:
    message: str | None
    command: Command | None
    transition: Transition | None
    metadata: dict
```

O agente pode conversar, propor um comando ou encerrar/transicionar o fluxo. Ele não executa diretamente operações de banco, Telegram ou scheduler.

### Harness como autoridade de execução

O Harness recebe comandos estruturados, valida autorização, escopo, argumentos, política de confirmação e idempotência, e só então chama o caso de uso correspondente.

O LLM pode sugerir uma ação, mas não pode decidir sozinho que uma ação de alto impacto está autorizada.

### Human-in-the-Loop

Exigem confirmação humana:

- `tasks.delete`;
- `tasks.delete_many`;
- qualquer alteração em massa, como `tasks.update_many`, `tasks.reschedule_many` ou `tasks.complete_many`;
- comandos futuros classificados pelo Harness como difíceis ou impossíveis de reverter.

Criação, consulta, conclusão individual, edição individual, remanejamento individual e criação de lembrete de tarefa não exigem confirmação nesta versão.

A confirmação pode ser feita por botões inline do Telegram ou por resposta textual curta. Em ambos os casos, a decisão final usa o estado de confirmação persistido, e não uma nova interpretação livre do LLM.

### Execução assíncrona

O caminho de execução é assíncrono desde a entrada até a persistência:

```text
FastAPI async
→ LangGraph async
→ Agents async
→ Harness async
→ Services async
→ Repositories async
→ SQLAlchemy AsyncSession
→ PostgreSQL com driver async
```

Nenhum módulo de aplicação deve bloquear o event loop com I/O síncrono.

## Vocabulário canônico

| Termo | Significado |
| --- | --- |
| Tarefa | Unidade de trabalho pertencente ao usuário. |
| Planejamento | Fluxo conversacional que escolhe, cria ou remaneja tarefas para uma data-alvo. |
| Prioridade | Indicador binário da tarefa: `0` significa não prioritária e `1` significa prioritária. O padrão é `0`. |
| Remanejamento | Alteração da data, horário ou prioridade de uma tarefa existente. |
| Revisão diária | Fluxo que revisa o estado das tarefas do dia e registra decisões do usuário. |
| Lembrete | Notificação agendada vinculada a uma tarefa. Não é uma entidade de agenda externa. |
| Fluxo ativo | Conversa que tem um agente responsável e estado persistido. |
| Comando | Intenção estruturada de leitura ou mutação produzida por um agente. |
| Harness | Módulo determinístico que valida e executa comandos. |
| Confirmação pendente | Estado persistido em que o comando aguarda uma decisão explícita do usuário. |
| Supervisor | Agente de roteamento; não é dono das regras de domínio nem executa comandos. |
| ResponseAgent | Agente final que transforma o resultado estruturado do Harness em resposta ao usuário. |

## Cenários principais

### Captura de tarefa

1. O usuário envia uma frase natural.
2. O Supervisor identifica que não há fluxo ativo e encaminha ao `TaskAgent`.
3. O `TaskAgent` pede os dados faltantes ou produz `tasks.create`.
4. O Harness valida o comando e chama o serviço de tarefas.
5. A resposta só confirma a criação após o commit bem-sucedido.

### Planejamento do próximo dia

1. O usuário inicia o planejamento.
2. O Graph cria ou recupera o fluxo de planejamento.
3. O `PlanningAgent` coleta tarefas, novas intenções, datas e horários.
4. O agente apresenta uma proposta consolidada.
5. Após o aceite, o Harness executa comandos individuais ou uma operação de lote conforme a policy.
6. Se houver alteração em massa, o Graph pausa em confirmação humana antes da execução.
7. Após a execução, o `ResponseAgent` recebe o payload do Harness e informa o que foi criado, alterado, remanejado ou excluído.

### Exclusão de tarefas

1. O agente produz `tasks.delete` ou `tasks.delete_many`.
2. O Harness valida o alvo e cria uma confirmação pendente.
3. O Telegram mostra resumo, quantidade e botões `Confirmar`/`Cancelar`.
4. O Graph pausa e salva o checkpoint.
5. O callback ou resposta textual resolve a confirmação.
6. O `ConfirmationResolver` chama o Harness diretamente; não há nova classificação pelo Supervisor nem nova autorização pelo agente.
7. Somente uma confirmação válida e não expirada libera a execução.
8. O Harness retorna o efeito executado e o `ResponseAgent` envia a confirmação final ao usuário.

## Critérios de pronto da base 2.0

- Os agentes não acessam diretamente modelos ORM ou APIs externas.
- O Supervisor respeita fluxos ativos.
- Todo comando tem schema e tipo explícito.
- O Harness bloqueia exclusões e operações em massa sem confirmação.
- O estado de confirmação sobrevive a reinício.
- Os casos de uso são chamáveis por Telegram, scheduler e testes sem duplicação de regra.
- As operações críticas possuem idempotency key e registro de execução.
- O código de domínio não conhece Telegram, Anthropic, LangGraph ou APScheduler.

## Referências de contexto

Os arquivos de referência da implementação anterior estão no diretório `sources/` do espelho do projeto ChatGPT: `CHATGPT_PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `STRUCTURE.md` e `SDD.md`. Eles não fazem parte da fonte de verdade da SARA 2.0 e não devem ser editados.
