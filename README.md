# SARA 2.0

Assistente virtual de IA para transformar linguagem natural em tarefas executáveis, com foco em automação confiável, confirmação explícita e rastreabilidade.

Este é um projeto autoral de [Murilo Russo](https://github.com/Dev-Russo), Engenheiro de Software com foco em IA aplicada, LLMs, RAG, agentes e desenvolvimento full stack.

## Sobre o projeto

O SARA 2.0 está sendo construído como um modular monolith orientado a domínio. A primeira fatia vertical já cobre captura de tarefas, interpretação por agente, planejamento do fluxo, persistência assíncrona e auditoria.

O projeto usa um Graph baseado em LangGraph e separa interpretação de execução: o agente propõe uma decisão estruturada, enquanto o Harness aplica políticas, confirmações, idempotência e handlers seguros. O adapter de LLM é ativado quando `LLM_API_KEY` e `LLM_MODEL` estão configurados.

## Foco técnico

- **IA aplicada:** LLMs, RAG, agentes, prompt engineering, heurísticas e aprendizado de máquina;
- **Engenharia de Software:** arquitetura modular, separação de responsabilidades, contratos tipados, testes por seam, observabilidade e auditoria;
- **Backend e integrações:** Python, FastAPI, APIs REST, Telegram, persistência assíncrona e integrações externas;
- **Desenvolvimento full stack:** React, Vite, JavaScript/TypeScript, HTML, CSS e Supabase;
- **Sistemas e infraestrutura:** Git, Bash, RabbitMQ, cache, load balancer, DNS, webhooks e práticas ágeis.

## Arquitetura

- `app/agents/`: interpretação de mensagens e decisões estruturadas;
- `app/graph/`: estado, roteamento, pausa e retomada do LangGraph;
- `app/harness/`: validação, políticas, confirmação, idempotência e execução;
- `app/services/`: casos de uso do domínio de tarefas;
- `app/repositories/` e `app/db/`: persistência assíncrona;
- `app/integrations/`: adapters de Telegram e LLM;
- `tests/`: testes por seam e por fluxo.

As decisões arquiteturais e regras funcionais estão documentadas em [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md).

## Projetos públicos selecionados

- [SARA 2.0](https://github.com/Dev-Russo/sara_v2.0) — assistente virtual de IA com LangGraph, agentes, políticas de execução e persistência;
- [rag-mitologia](https://github.com/Dev-Russo/rag-mitologia) — mapa mental vivo de mitologia grega com RAG, LangGraph, ChromaDB e fontes rastreáveis;
- [session-handoff-mcp](https://github.com/Dev-Russo/session-handoff-mcp) — servidor MCP local-first para handoff estruturado entre agentes de programação;
- [agregador-node-springboot](https://github.com/Dev-Russo/agregador-node-springboot) — agregador distribuído de dados com Java, Spring Boot, PostgreSQL, RabbitMQ e WebSocket;
- [mathquest-unity](https://github.com/Dev-Russo/mathquest-unity) — jogo educacional em C# e Unity com resolução por backtracking e notação polonesa reversa;
- [olist-analise](https://github.com/Dev-Russo/olist-analise) — análise de comportamento de compra em e-commerce com dados e recomendações acionáveis;
- [Dev-Russo](https://github.com/Dev-Russo) — portfólio principal e índice dos projetos públicos.

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

Depois de aplicar as migrations, o CLI permite testar o mesmo Graph e a mesma persistência da aplicação:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m app.cli
```

Use `--debug` para visualizar a decisão estruturada do agente, o payload do comando, o resultado do Harness e a resposta final:

```powershell
.venv\Scripts\python.exe -m app.cli --debug
```

Para gerar o diagrama do Graph compilado:

```powershell
.venv\Scripts\python.exe -m app.graph.visualization --png
```

## Testes e qualidade

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check app tests alembic
```

## Princípios de segurança

1. O agente interpreta; não executa diretamente.
2. Toda mutação iniciada por agente passa pelo Harness.
3. O `user_id` vem do contexto confiável, nunca do payload do LLM.
4. Exclusões e alterações em massa exigem confirmação persistida.
5. O `HarnessResult.effect` é a fonte de verdade da resposta final.

## Sobre o autor

Murilo Russo atua como Engenheiro de Software na Evolue Digital, trabalhando com aplicações web full stack, APIs, integrações externas, automação e IA aplicada. Também possui experiência em liderança técnica e gestão de projetos de software na InfoAlto, empresa júnior de TI da UFV.

- [LinkedIn](https://www.linkedin.com/in/murilo-russo)
- [GitHub](https://github.com/Dev-Russo)
