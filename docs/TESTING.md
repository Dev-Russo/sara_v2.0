# SARA 2.0 — Estratégia de Testes

## Objetivo

Os testes devem proteger as decisões arquiteturais mais importantes: roteamento por fluxo ativo, execução async, isolamento por usuário, confirmação humana e idempotência.

O teste deve cruzar a mesma interface que um caller de produção cruza. Se for necessário conhecer tabelas, SDKs ou detalhes internos para testar um comportamento, revisar a seam do módulo.

## Stack de teste

Alvo inicial:

- `pytest` como runner;
- `pytest-asyncio` para corrotinas;
- `httpx` ou cliente equivalente para routers FastAPI;
- PostgreSQL de teste para testes de repository e integração;
- adapters fake para Telegram e LLM;
- fixtures async com escopo controlado.

O smoke test legado pode continuar existindo, mas não substitui a suíte automatizada da 2.0.

## Pirâmide

```text
                 E2E críticos
              /               \
       Graph + adapters + scheduler
        /                       \
 Harness + services + repositories
      /                           \
  domínio, schemas, policies, parsers
```

## Testes unitários

Cobrir sem banco ou rede:

- schemas de comandos e decisões;
- normalização de confirmação (`sim`, `confirmar`, `não`, `cancelar`);
- policy que classifica delete e lote como confirmação obrigatória;
- cálculo de backlog e atraso;
- validação de intervalos de data/horário;
- regras de transição do Supervisor;
- composição de resumo de confirmação;
- idempotency key;
- serialização/deserialização de estado do Graph.

Esses testes devem ser rápidos e determinísticos.

## Testes do Harness

O Harness é área de cobertura obrigatória.

Casos mínimos:

1. comando válido sem confirmação executa uma vez;
2. `tasks.delete` retorna `awaiting_confirmation`;
3. `tasks.delete_many` cria uma única pendência;
4. alteração em massa sem confirmação não altera o banco;
5. confirmação de outro usuário é rejeitada;
6. callback duplicado não repete a mutação;
7. confirmação expirada não executa;
8. lote com alvo de outro usuário falha inteiro;
9. erro de validação não chama o service;
10. repetição da mesma idempotency key devolve o resultado anterior;
11. falha antes do commit não deixa dados parciais;
12. resultado só é `executed` após persistência confirmada.
13. `executed` sempre contém `effect` suficiente para a resposta final.

## Testes de services e repositories

Usar PostgreSQL de teste para verificar:

- criação, consulta, conclusão, edição e remanejamento;
- filtros por usuário e por data;
- relação tarefa-lembrete;
- transação e rollback;
- exclusão em lote atômica;
- concorrência de confirmações;
- índices e migrations essenciais;
- comportamento quando um alvo desaparece entre validação e execução.

Repositories podem usar uma implementação fake em testes de agents e Graph. Testes que validam SQL, constraints ou transação devem usar banco real de teste.

## Testes de agentes

Usar um LLM fake que receba mensagem e devolva decisões estruturadas conhecidas. Não fazer chamadas reais ao provedor.

Verificar que:

- o agente produz `AgentDecision` válido;
- pergunta dados faltantes em vez de inventá-los;
- não acessa o banco diretamente;
- não executa delete;
- encerra ou transiciona quando o usuário cancela;
- mantém o contexto de planejamento em mensagens subsequentes;
- não inclui comandos fora do catálogo.

## Testes do ResponseAgent

Testar o agente final exclusivamente com `HarnessResult` fabricados:

- tarefa criada gera resposta de criação, com título e identificador quando permitido;
- tarefa excluída gera resposta de exclusão e quantidade correta;
- alteração ou remanejamento informa somente campos presentes em `effect`;
- falha e rejeição usam `error_code` e não afirmam sucesso;
- payload incompleto usa fallback seguro;
- o agente não inventa IDs, tarefas, efeitos ou confirmações;
- a resposta final é produzida depois de `executed`, nunca antes do commit.

## Testes do Graph

Verificar o ciclo completo do estado:

- sem fluxo ativo, Supervisor seleciona o agente correto;
- com fluxo ativo, a mensagem não passa pelo Supervisor novamente;
- troca explícita encerra o fluxo anterior;
- comando comum passa pelo Harness e volta ao agente;
- confirmação pausa o Graph;
- callback confirmado retoma o mesmo checkpoint;
- cancelamento limpa a pendência e encerra ou retoma o fluxo esperado;
- reinício com checkpoint persistido continua do ponto correto.

## Testes de routers e integrações

Adapters externos devem ser substituídos por fakes.

Cobrir:

- secret de webhook ausente ou inválido;
- chat não autorizado;
- `update_id` duplicado;
- callback de confirmação válido e inválido;
- callback confirmado chama `ConfirmationResolver`/Harness diretamente, sem Supervisor;
- conversão de `HarnessResult` para mensagem/keyboard;
- retry de envio sem repetir comando de domínio;
- limite de tamanho de mensagem;
- falhas do provedor de LLM sem corromper sessão.

## Testes do Scheduler

- job de lembrete seleciona somente itens vencidos e não enviados;
- reexecução não envia o mesmo lembrete duas vezes;
- job inicia revisão/planejamento apenas para usuários elegíveis;
- timezone do usuário é respeitado;
- falha de entrega não repete mutação de tarefa;
- dois workers não executam a mesma janela sem coordenação;
- confirmação ou fluxo iniciado por scheduler usa o mesmo Graph do Telegram.

## Testes de fluxo conversacional

Manter cenários legíveis, próximos do uso real:

```text
Usuário: planejar amanhã
Assistente: quais tarefas quer incluir?
Usuário: incluir revisar documentação às 10h
Assistente: plano proposto...
Usuário: sim
Assistente: planejamento salvo.
```

Também cobrir:

- “na verdade às 11h” durante planejamento;
- “cancela o planejamento”;
- “apague essas quatro” com confirmação por botão;
- “sim” sem confirmação pendente;
- “quero ver minhas tarefas” durante uma revisão;
- mensagem repetida após timeout.

## Fixtures e isolamento

- Cada teste de domínio usa um `TEST_USER` próprio ou fixture transacional.
- Nunca usar banco de produção.
- Resetar tabelas por fixture ou transação rollback.
- Criar tarefas por factory pequena e explícita.
- Fakes de Telegram devem capturar texto, callbacks e teclados.
- Fakes de LLM devem permitir respostas inválidas para testar rejeição.

## Cobertura e gates

Não perseguir percentual artificial. Os gates mínimos são:

- todos os testes do Harness;
- todos os fluxos de confirmação;
- todos os cenários de isolamento por usuário;
- migrations aplicadas do zero;
- smoke test de scheduler e Telegram fake;
- lint/type checking configurados para código novo.

## Testes que não devem existir

- teste que depende de API real do LLM ou Telegram;
- teste que confirma sucesso apenas olhando texto livre;
- teste que injeta `user_id` pelo payload do agente;
- teste que usa mock do banco para validar uma constraint SQL;
- teste que ignora o Harness para alcançar o service;
- teste que acessa estado privado em memória para simular persistência.
