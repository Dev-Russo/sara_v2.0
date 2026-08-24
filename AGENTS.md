# AGENTS.md — SARA 2.0

## Contexto do sistema

SARA 2.0 é uma assistente pessoal conversacional, inicialmente integrada ao
Telegram, que transforma linguagem natural em comandos estruturados para
gerenciar tarefas. O sistema deve distinguir claramente entre o que foi
interpretado, proposto e realmente executado.

Características principais:

- monólito modular orientado a domínio; não transformar a aplicação em
  microsserviços sem uma decisão explícita;
- Python 3.12+, FastAPI, LangGraph, SQLAlchemy assíncrono e PostgreSQL;
- adapter de LLM isolado por interface, com Anthropic como implementação atual;
- execução assíncrona de ponta a ponta; não bloquear o event loop com I/O
  síncrono;
- CLI e Telegram devem reutilizar o mesmo Graph, Harness e casos de uso;
- documentação funcional e arquitetural em `docs/`.

O domínio atual é gerenciamento pessoal de tarefas: criação, consulta,
conclusão, edição, organização por data/prioridade/status, planejamento,
revisão diária e lembretes vinculados a tarefas. Finanças, pagamentos,
calendário externo, colaboração, mensagens para terceiros, RAG e automações
fora desse domínio estão fora do escopo atual.

## Estado real da implementação

Use o código e os testes para saber o que já funciona; use os documentos em
`docs/` para entender as decisões e o alvo arquitetural. A fatia vertical
implementada e coberta hoje concentra-se em:

- entrada de health check e CLI;
- `TaskAgent` com validação do retorno do LLM;
- Graph de tarefas com roteamento, fluxo ativo, resolução de referências
  ambíguas e seleção de candidato;
- comandos `tasks.create`, `tasks.list`, `tasks.complete` e `tasks.update`,
  incluindo os comandos internos resolvidos por ID;
- `TaskService`, repositories SQLAlchemy assíncronos, idempotência e efeito
  estruturado para o `ResponseAgent`;
- resposta determinística baseada no `HarnessResult`, além de testes unitários
  e de integração.

Há contratos e pastas para planejamento, revisão, lembretes, operações em lote,
Scheduler e confirmações, mas nem todos esses fluxos estão completos. O
processamento do corpo do webhook Telegram, a entrega externa e a retomada
persistida de confirmações ainda não devem ser tratados como funcionalidades
prontas apenas porque seus schemas ou interfaces existem.

## Arquitetura e fluxo de execução

O caminho normal é:

```text
entrada/adaptador
  → router
  → LangGraph
  → Supervisor ou agente do fluxo ativo
  → AgentDecision
  → Harness
  → service/caso de uso
  → repository
  → banco
  → HarnessResult
  → ResponseAgent
  → adaptador de saída
```

O roteamento respeita esta ordem:

1. confirmação pendente, quando o fluxo estiver implementado;
2. agente do fluxo ativo;
3. Supervisor somente quando não houver fluxo ativo.

Uma mensagem de um fluxo ativo não deve voltar ao Supervisor sem uma troca de
contexto inequívoca. Confirmações devem resolver o snapshot persistido
diretamente no `ConfirmationResolver`/Harness, sem nova interpretação do LLM.

Responsabilidades por módulo:

- `app/api/routers/`: transporte, autenticação da entrada, contexto confiável,
  deduplicação e chamada do Graph; não aplicar regra de negócio;
- `app/schemas/`: contratos tipados de comandos, eventos, decisões e
  resultados; não persistir nem chamar integrações;
- `app/graph/`: estado, sequência, roteamento, pausa, retomada e transições;
  não duplicar regras dos services;
- `app/agents/`: interpretar mensagens dentro de um fluxo e retornar
  `AgentDecision`; não acessar banco, Telegram, Scheduler ou executar comandos;
- `app/harness/`: validar comandos, ownership, policy, confirmação,
  idempotência, auditoria e delegação ao caso de uso; é a única porta para
  mutações iniciadas por agentes;
- `app/services/`: casos de uso e regras de domínio; devem devolver resultados
  estruturados e controlar a unidade transacional;
- `app/repositories/`: esconder persistência atrás de interfaces assíncronas,
  sempre filtrando por `user_id`; não fazer `commit` escondido;
- `app/models/` e `app/db/`: modelo persistido, engine, sessões e migrações;
- `app/integrations/`: adapters de Telegram, LLM e provedores externos; tipos
  de SDK não devem vazar para o domínio;
- `app/scheduler/`: disparar eventos idempotentes para o Graph; não reimplementar
  services;
- `app/observability/`: logs, métricas e correlação, sem alterar resultados.

Direção esperada das dependências:

```text
routers → graph → agents/harness/services → repositories → db
scheduler → graph
integrations → interfaces internas
schemas/models → não dependem de routers ou integrações
```

Arquivos de composição (`main.py`, routers, `graph/builder.py` e adapters)
devem permanecer pequenos. Se uma regra crescer neles, extraia-a para um
módulo com interface própria.

## Regras obrigatórias de modularização

### Não duplicar responsabilidades

Cada função e cada módulo deve ter uma responsabilidade principal e uma razão
principal para mudar. Não copie a mesma regra para duas funções, camadas ou
entradas diferentes.

Quando duas funções precisarem executar a mesma responsabilidade:

1. identifique o conceito comum e extraia um método ou módulo compartilhado;
2. coloque-o na camada mais baixa que realmente possui essa regra, sem criar
   dependência circular;
3. dê ao método parâmetros e retorno tipados, uma interface pequena e um nome
   que expresse o comportamento;
4. faça as duas funções delegarem para esse método comum;
5. teste o método na sua seam e teste em cada caller somente a orquestração
   específica.

Exemplos:

- regra de negócio de tarefa pertence ao `TaskService`, não ao Graph, router e
  CLI ao mesmo tempo;
- normalização e validação de payload pertencem ao schema ou ao módulo de
  domínio apropriado, não a cada agent;
- conversão de protocolo pertence ao adapter, não aos agents e services;
- sequência e roteamento pertencem ao Graph, não ao service;
- policy de segurança pertence ao Harness, não ao prompt do LLM.

Não extraia um `utils.py` genérico apenas porque duas funções têm linhas
parecidas. Compartilhe quando a responsabilidade e a semântica forem as
mesmas; se forem regras distintas, mantenha-as separadas e documente a
diferença. Prefira um módulo profundo: interface pequena, dependências
explícitas, implementação concentrada e seam fácil de testar ou substituir.

### Contratos, segurança e efeitos

- Todo comando aceito pelo Harness tem `type`, payload validado e handler
  explícito; não criar fallback genérico para comandos inventados.
- `user_id` vem do contexto confiável, nunca do payload produzido pelo LLM.
- Toda consulta e mutação deve respeitar ownership por `user_id`.
- Nenhuma mutação iniciada por agente contorna o Harness.
- Exclusões e alterações em massa exigem confirmação humana persistida e
  consumida no máximo uma vez.
- `HarnessResult.effect` é a fonte de verdade da resposta final; nunca afirmar
  sucesso antes da persistência confirmada nem inventar efeitos no
  `ResponseAgent`.
- Operações repetíveis recebem `idempotency_key` e não podem criar duplicatas.
- Erros esperados viram códigos/resultados controlados; SQL, stack traces,
  tokens e respostas completas de provedores não chegam ao usuário.
- Estado de fluxo e confirmações importantes devem ser duráveis; memória local
  pode ser apenas otimização.

## Como implementar mudanças

Antes de alterar código, leia os documentos relevantes, especialmente:

- `docs/PROJECT_CONTEXT.md` para escopo e vocabulário;
- `docs/ARCHITECTURE.md` para seams e responsabilidades;
- `docs/CONVENTIONS.md` para contratos, transações e observabilidade;
- `docs/HARNESS.md` para execução, confirmação e idempotência;
- `docs/DEVELOPMENT.md`, `docs/TESTING.md` e `docs/DATA_MODEL.md` quando a
  mudança envolver desenvolvimento, testes ou persistência.

Ordem recomendada para uma nova capacidade:

```text
schema/policy
  → service
  → model/repository/migration
  → handler do Harness
  → Graph
  → agent
  → integração/interface de usuário
```

Para um novo comando: defina o schema, registre o handler, reutilize ou crie o
caso de uso, aplique policy de confirmação, conecte o agente adequado e cubra a
seam do Harness e o fluxo completo. Para mudanças de banco, altere model,
migration, repository e testes juntos; não edite migration já aplicada em
ambiente compartilhado.

Atualize a documentação quando uma mudança alterar escopo, vocabulário,
contrato ou decisão arquitetural. Não use prompt como substituto para policy,
validação, autorização ou idempotência.

### Fluxo recomendado para qualquer implementação

Toda mudança de comportamento deve seguir este fluxo, usando as skills
correspondentes quando estiverem disponíveis:

1. **Contexto e contrato:** confirme o escopo, leia a documentação relevante,
   defina a interface/seam e registre decisões arquiteturais quando necessário.
2. **`tdd`:** escreva primeiro um teste de comportamento na seam pública
   acordada. Execute o ciclo red → green em fatias verticais, um comportamento
   por vez, sem testar detalhes internos.
3. **`implement`:** implemente somente o necessário para fazer o teste passar,
   mantendo as responsabilidades na camada correta. Repita o ciclo para cada
   fatia e evite funcionalidades especulativas.
4. **`code-review`:** revise o diff completo contra os padrões do repositório e
   contra o comportamento solicitado. Procure especialmente lógica duplicada,
   responsabilidades divergentes, seams rasas, dependências indevidas e
   alterações fora do escopo. Refatorações pertencem a esta etapa depois que
   os testes estiverem verdes.
5. **Verificação e entrega:** execute testes, lint e demais checks aplicáveis,
   revise `git diff`/`git status` e informe limitações ou verificações que não
   puderam ser executadas.

O fluxo `implement` deve deixar explícito o que foi alterado e conduzir a
execução de TDD e code review; não encerrar uma implementação apenas porque o
código compila. Se o code review encontrar a mesma responsabilidade em duas
funções, extraia o método comum, faça ambas delegarem a ele e repita os testes
da seam antes de concluir.

## Desenvolvimento e verificação

Ambiente local típico:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d postgres
.venv\Scripts\python.exe -m alembic upgrade head
```

Comandos principais:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app tests alembic
.venv\Scripts\python.exe -m compileall app
uvicorn app.main:app --reload
```

O CLI usa o mesmo Graph e exige `LLM_API_KEY`, `LLM_MODEL` e banco acessível:

```powershell
.venv\Scripts\python.exe -m app.cli
.venv\Scripts\python.exe -m app.cli --debug
```

Use fakes nos testes; não chamar Telegram ou LLM reais para validar regra de
domínio. Em testes, atravesse a mesma interface usada em produção. Priorize
invariantes de ownership, confirmação, idempotência, transação, fluxo ativo e
resposta grounded no `HarnessResult`.

## Arquivos protegidos e higiene do repositório

- Todo arquivo em `sources/` é material de referência sincronizado: tratar como
  somente leitura; não editar, renomear, mover ou excluir.
- Não sobrescrever alterações pré-existentes de outros arquivos durante a
  tarefa.
- Não versionar `.env`, tokens, chaves, prompts completos ou dados pessoais.
- Antes de concluir, revisar `git diff` e `git status` e confirmar que a mudança
  ficou limitada ao escopo solicitado.
