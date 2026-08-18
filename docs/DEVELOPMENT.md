# SARA 2.0 — Desenvolvimento

## Pré-requisitos

- Python 3.12+;
- PostgreSQL compatível com o ambiente alvo;
- Docker e Docker Compose para desenvolvimento local;
- credenciais de Telegram e LLM apenas quando o fluxo local precisar de adapters reais;
- arquivos de ambiente separados de produção.

## Ambiente local

O banco local deve ser isolado do banco de produção. Use um arquivo como `.env.local` e uma porta/container próprios para desenvolvimento.

Variáveis mínimas esperadas, sem registrar valores neste documento:

```text
DATABASE_URL
TELEGRAM_BOT_TOKEN
TELEGRAM_WEBHOOK_SECRET
ALLOWED_CHAT_ID
LLM_API_KEY
LLM_MODEL
TIMEZONE
```

O Graph só é composto com o adapter real quando `LLM_API_KEY` e `LLM_MODEL` estão
preenchidos. Sem essas variáveis, o processo ainda inicia para health checks, mas
o fluxo conversacional não fica disponível.

O modo de teste deve conseguir iniciar sem chamar Telegram ou LLM reais, usando fakes.

## Inicialização típica

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
docker compose up -d postgres
alembic upgrade head
```

Na implementação Windows, substitua apenas o comando de ativação; mantenha a separação de ambiente e banco.

## Executar a aplicação

```bash
uvicorn app.main:app --reload
```

O endpoint de health deve estar disponível para indicar que a aplicação iniciou. O webhook local não deve ser registrado no bot de produção.

Para testar conversação local, prefira um adapter/fake ou CLI que use o mesmo Graph, Harness e services sem enviar mensagens reais.

## Ciclo de implementação

### 1. Especificar o comportamento

Atualizar primeiro `PROJECT_CONTEXT.md` se a decisão alterar escopo, vocabulário ou fluxo. Se for uma decisão arquitetural difícil de reverter, registrar o motivo no documento apropriado antes do código.

### 2. Definir o contrato

Criar ou atualizar:

- schema do comando;
- schema do resultado;
- estados e transições;
- policy do Harness;
- interface do service/repository quando necessário.

### 3. Implementar de dentro para fora

Ordem recomendada:

```text
schema/policy
→ service
→ repository/model/migration
→ Harness handler
→ Graph node/route
→ agent prompt/adapter
→ integration UI
```

### 4. Cobrir os invariantes

Adicionar testes unitários, Harness, persistência e fluxo conversacional conforme o risco. Para delete ou lote, o teste de “não executa sem confirmação” é obrigatório.

### 5. Verificar localmente

```bash
pytest
python -m compileall app
alembic upgrade head
```

Executar também o smoke test existente do projeto quando ele estiver mantido durante a migração.

## Migrations

Nunca editar uma migration já aplicada em ambiente compartilhado. Criar uma nova revisão, testar upgrade e downgrade quando suportado e validar autogenerate com todos os models importados.

Antes de aplicar uma migration destrutiva:

- confirmar que o escopo é explícito;
- fazer backup quando aplicável;
- verificar quantidade de registros afetados;
- documentar a impossibilidade de rollback, se existir.

## Operação do Graph

- `graph_thread_id` deve ser estável durante um fluxo;
- checkpoints devem ser persistidos antes de pausar;
- callbacks devem retomar o thread correto;
- expiração de sessão deve produzir uma resposta compreensível;
- não usar variável global para substituir o checkpointer.

## LLM local

Use um adapter fake para desenvolvimento de regra. O prompt real deve ser exercitado somente em testes controlados e nunca deve ser a única camada de segurança.

Ao alterar prompt ou schema:

1. testar comando válido;
2. testar payload ausente ou inválido;
3. testar tentativa de comando fora do escopo;
4. testar pedido de delete sem confirmação;
5. testar troca de contexto durante fluxo ativo.

## Scheduler local

Jobs devem ter uma forma manual de disparo em teste. Não aguardar o relógio real para testar lembretes, revisão ou planejamento.

O Scheduler deve usar o Graph público e as mesmas policies do Telegram. Não criar um caminho paralelo que altere tarefas diretamente.

## Observabilidade no desenvolvimento

Cada execução manual deve permitir localizar:

- usuário;
- evento recebido;
- fluxo e agente;
- comando;
- confirmação;
- resultado;
- erro ou retry.

Use dados fictícios ou anonimizados em logs compartilhados. Não copiar `.env`, tokens ou transcrições pessoais para tickets ou commits.

## Checklist antes de abrir uma mudança

- [ ] O comportamento está dentro do escopo de tarefas?
- [ ] O documento funcional ou arquitetural foi atualizado, se necessário?
- [ ] O caminho é assíncrono?
- [ ] O Supervisor respeita fluxo ativo?
- [ ] O comando tem schema e handler explícitos?
- [ ] Delete e lotes passam por confirmação persistida?
- [ ] A mudança filtra por `user_id`?
- [ ] Existe idempotência para reentrega?
- [ ] Migration e testes acompanham mudança de banco?
- [ ] O teste local não usa produção nem chama integrações reais por acidente?
