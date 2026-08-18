# SARA 2.0

Assistente pessoal conversacional, inicialmente operada pelo Telegram, para transformar linguagem natural em tarefas executáveis.

## Estado atual

Esta base cria o esqueleto do modular monolith e já possui a primeira fatia vertical
de captura de tarefas: Graph, TaskAgent, Harness, persistência e auditoria. O
Graph usa o adapter Anthropic quando `LLM_API_KEY` e `LLM_MODEL` estão configurados;
confirmações, planejamento, revisão e integração completa do webhook continuam
nas próximas fatias.

## Arquitetura

- `app/agents/`: interpretação de mensagens e decisões estruturadas;
- `app/graph/`: estado, roteamento, pausa e retomada do LangGraph;
- `app/harness/`: validação, policy, confirmação, idempotência e execução;
- `app/services/`: casos de uso do domínio de tarefas;
- `app/repositories/` e `app/db/`: persistência assíncrona;
- `app/integrations/`: adapters de Telegram e LLM;
- `tests/`: testes por seam e por fluxo.

As regras funcionais e decisões arquiteturais estão em [`docs/`](docs/PROJECT_CONTEXT.md).

## Desenvolvimento local

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
Copy-Item .env.example .env.local
docker compose up -d postgres
uvicorn app.main:app --reload
```

Health check: `GET http://localhost:8000/health`.

## Testes e qualidade

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app tests alembic
```

## Regras importantes

1. O agente interpreta; não executa.
2. Toda mutação iniciada por agente passa pelo Harness.
3. O `user_id` vem do contexto confiável, nunca do payload do LLM.
4. Exclusões e alterações em massa exigem confirmação persistida.
5. O `HarnessResult.effect` é a fonte de verdade da resposta final.
