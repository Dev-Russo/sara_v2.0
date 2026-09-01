# Deploy na VM da OCI

Este procedimento prepara uma única VM Linux para executar a API da SARA e o
PostgreSQL em containers. O reverse proxy, TLS e o registro do webhook Telegram
serão configurados na etapa seguinte.

## Pré-requisitos da VM

- Docker Engine e Docker Compose Plugin instalados;
- repositório clonado em um diretório da aplicação;
- portas de entrada 22 e 443 liberadas no firewall da VM e nas regras de rede
  da OCI;
- DNS apontando para o IP público quando formos configurar o HTTPS;
- espaço suficiente para a imagem, dependências e volume do PostgreSQL.

## Primeiro start

```bash
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production

docker compose --env-file .env.production -f docker-compose.production.yaml up -d --build
docker compose --env-file .env.production -f docker-compose.production.yaml ps
curl http://127.0.0.1:8000/health
```

O container da API executa `alembic upgrade head` antes de iniciar o Uvicorn.
As migrations são aplicadas contra o serviço `postgres` da rede interna do
Compose. O volume `sara_postgres_data` preserva os dados entre recriações.

## Operação

```bash
docker compose --env-file .env.production -f docker-compose.production.yaml logs -f api
docker compose --env-file .env.production -f docker-compose.production.yaml restart api
docker compose --env-file .env.production -f docker-compose.production.yaml pull postgres
```

Para atualizar uma versão do código:

```bash
git pull --ff-only
docker compose --env-file .env.production -f docker-compose.production.yaml up -d --build
```

Para voltar à versão anterior, checkout do commit desejado e repita o comando
de build. Não usar `docker compose down -v`: isso remove o volume do banco.

## Segurança e limites desta etapa

- não versionar `.env.production`;
- usar senha forte e URL-safe no PostgreSQL, ou aplicar encoding URL na
  `DATABASE_URL`;
- não publicar a porta 5432;
- a API fica exposta somente em `127.0.0.1:8000` até o reverse proxy;
- não registrar o webhook Telegram antes de existir um endpoint HTTPS válido;
- configurar backup do volume antes de tratar a VM como produção.
