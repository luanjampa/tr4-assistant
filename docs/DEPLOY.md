# Hospedagem online (suporte TR4) — Render + Neon + Cloudflare

Substitui um plano anterior baseado em Railway: o hard spend-limit do Railway é por
**workspace inteiro**, não por projeto (confirmado na doc oficial e na própria UI) —
usar a mesma conta de outros projetos existentes significava que estourar o gasto do
TR4 derrubaria os outros também. Render + Neon + Cloudflare rodam com custo esperado
de **$0/mês** (free tier de cada um) e isolados de qualquer outra conta.

| Serviço | Função | Free tier |
|---------|--------|-----------|
| **Render** | `POST /chat`, `GET /health` — reaproveita o `Dockerfile` do repo, zero mudança de código | 750h/mês (1 serviço sempre ligado), 512MB RAM, dorme após 15min sem uso (~30-50s pra acordar) |
| **Neon** | Postgres + pgvector (tabela `tr4_kb` + `tr4_usage` + `tr4_gaps`) | 100 compute-hours/mês, 0.5GB storage, sem expiração por calendário, "acorda" em <500ms |
| **Cloudflare** | Embeddings (Workers AI `bge-m3`) + captcha (Turnstile) | Workers AI: $0.012/M tokens, geralmente dentro do free tier pro volume de um grupo pequeno |
| **Groq** | Chat (`llama-3.1-8b-instant`) — externo, não hospedado em lugar nenhum | Free tier próprio, ver `CLAUDE.md` sobre o limite de 6000 tokens/min |

## 1. Neon (Postgres + pgvector)

1. Cria conta em [console.neon.tech/signup](https://console.neon.tech/signup) (sem cartão) e um projeto.
2. `Connect` → copia a **connection string** (formato pooled, com `-pooler` no host — é o padrão e funciona bem, só um detalhe de `search_path` que o app já contorna, ver abaixo). Essa é a `DATABASE_URL`.
3. Não precisa rodar `CREATE EXTENSION vector` manualmente — a app faz isso sozinha no startup (`ensure_schema_async`), e o Neon já suporta `pgvector` nativamente.

**Gotcha real encontrado em produção**: o pooler do Neon (PgBouncer) não garante `public` no `search_path` de toda conexão nova, mesmo sendo o default do role — isso causava erro intermitente `relation "tr4_usage" does not exist` mesmo com a tabela existindo. `store.py` já força `SET search_path TO public` em toda conexão do pool (sync e async) — não precisa fazer nada a respeito, mas é bom saber que existe caso apareça de novo com outro provider pooled.

## 2. Render (API)

1. Cria conta em [dashboard.render.com/register](https://dashboard.render.com/register) (sem cartão).
2. `New` → `Web Service` → conecta o GitHub (autoriza o app Render só no repo `tr4-assistant`, não em todos) → seleciona o repo.
3. Render detecta o `Dockerfile` sozinho ("It looks like you're using Docker"). Nome do serviço, branch `master`, região à escolha.
4. **Instance Type**: `Free` ($0/mês).
5. **Environment Variables** — usa "Add from .env" pra colar tudo de uma vez (ver `.env.example` pra lista completa): `CLOUDFLARE_*`, `GROQ_*`, `DATABASE_URL` (do Neon), `TR4_API_KEY` (gera uma chave de produção nova, não reusa a de dev), `RATE_LIMIT_PER_MINUTE`, `MAX_MONTHLY_SPEND_USD`.
6. `Deploy Web Service`. Auto-deploy fica ligado por padrão — todo push na branch configurada reconstrói e sobe sozinho.

Healthcheck: `GET /health`. URL pública gerada automaticamente (`https://<nome>.onrender.com`), HTTPS já incluso.

## 3. Cloudflare (embeddings + spend limit)

1. `IA > Workers AI > Crie um token de API Workers AI` — gera `CLOUDFLARE_API_TOKEN`. Account ID fica na URL do dashboard.
2. **Recomendado**: `IA > Gateway de AI > Criar um gateway personalizado` — nomeia (ex. `tr4-assistant`), liga:
   - **Spend Limits** (beta): cost limit em USD, window "1 month", sliding — trava de verdade, bloqueia a chamada ao bater o valor.
   - **Solicitações de limite de taxa**: rate limit adicional (ex. 50 req/min).
   - **Gateway autenticado**: gera um token à parte (`Criar token de API` na seção) — vira `CLOUDFLARE_GATEWAY_TOKEN`.
   - **Respostas de cache**: seguro ligar pra embeddings (mesma entrada = mesmo vetor sempre, sem risco de dado desatualizado).
3. Sem o gateway (`CLOUDFLARE_GATEWAY_ID`/`TOKEN` vazios), o app chama Workers AI direto — funciona, mas **sem nenhum teto de gasto** nesse provider.

## 4. Ingestão (`tr4-sync`)

Rodar localmente apontando pro `DATABASE_URL` de produção (Neon):

```bash
tr4-sync --whatsapp ./data/raw/grupo.txt --facebook-json ./data/raw/fb.json \
         --facebook-manual ./data/facebook_manual --docs ./data/manuals \
         --owner-notes ./data/notes --web-seeds ./data/seeds/tr4_sources.txt --clear
```

**Se já tem dados indexados localmente e só quer levar pra produção** (ex. depois de trocar de embedding provider, ou pra não esperar a classificação de relevância do WhatsApp rodar de novo — pode levar 40-60min pelo rate limit do Groq): dump direto do Postgres local pro Neon, sem passar pela ingestão de novo.

```bash
docker exec tr4-postgres-1 pg_dump -U tr4 -d tr4 --data-only --no-owner --disable-triggers --table=tr4_kb > /tmp/tr4_kb_dump.sql
docker exec -i tr4-postgres-1 psql "$NEON_DATABASE_URL" < /tmp/tr4_kb_dump.sql
```

Repetir a ingestão periodicamente (cron local, GitHub Actions, ou um Render Cron Job separado) pra manter a base atualizada.

## 5. Segurança mínima antes de considerar "pronto"

- [x] `TR4_API_KEY` definido com uma chave de produção real (não a de dev) — sem isso `/chat` fica aberto sem autenticação.
- [x] `MAX_MONTHLY_SPEND_USD` definido (Groq) e **Spend Limit real configurado no Cloudflare AI Gateway** (embeddings) — dois provedores, dois tetos.
- [x] `RATE_LIMIT_PER_MINUTE` ajustado — limitador em memória, só protege 1 instância; Render free tier só roda 1 réplica mesmo, então tá OK por ora.
- [x] HTTPS (Render já fornece TLS no domínio `.onrender.com`).
- [x] Neon não exposto senão pela connection string (Render acessa via internet cifrada, `sslmode=require`).
- [x] Frontend em `frontend/` (servido pelo próprio backend em `GET /ui`) busca `GET /terms` antes do primeiro uso e só chama `/chat` com `accepted_terms: true` — sem isso a API recusa com 403 (ver `src/tr4/legal.py`). Precisa dar `git push`/deploy pra ir pro ar em produção.
- [ ] Turnstile de verdade: `app.js` e `GET /config` já sabem lidar com isso, só falta criar o site no Cloudflare Turnstile e definir `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET_KEY` em produção — sem isso, `/chat` aceita sem captcha.

## 6. Observabilidade

- Healthcheck: `GET /health`.
- Logs do serviço no painel Render (`Logs`, com Live Tail).
- Gasto Groq acumulado do mês: `SELECT SUM(cost_usd) FROM tr4_usage WHERE date_trunc('month', ts) = date_trunc('month', now());`
- Gasto Cloudflare: aba `Análise`/`Logs` do AI Gateway no dashboard Cloudflare.
- Perguntas mal respondidas: `SELECT * FROM tr4_gaps ORDER BY ts DESC;` ou `make gaps` local apontando pra `DATABASE_URL` de produção.
