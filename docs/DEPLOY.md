# Hospedagem online (suporte TR4) — Railway

Três serviços Railway no mesmo projeto:

| Serviço | Imagem/build | Função |
|---------|--------------|--------|
| **api** | Dockerfile deste repo | `POST /chat`, `GET /health` |
| **postgres** | addon Railway Postgres, ou imagem `pgvector/pgvector:pg16` se o addon não tiver a extensão `vector` | Base de conhecimento (tabela `tr4_kb`) + log de gasto (`tr4_usage`) |
| **ollama** | imagem `ollama/ollama` | Só embeddings (`nomic-embed-text`), CPU chega, **sem GPU** |

Chat (Groq) é um serviço externo — não roda no Railway, só precisa de `GROQ_API_KEY`.

## 1. Postgres + pgvector

- Cria o addon **Postgres** no projeto Railway.
- Conecta (`railway connect postgres` ou psql com a `DATABASE_URL`) e roda:
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  ```
  Se o addon recusar (extensão não disponível na imagem gerenciada), sobe um serviço próprio a partir da imagem `pgvector/pgvector:pg16` (Deploy from Docker Image) com um volume persistente — a app cria o resto do schema sozinha no startup (`ensure_schema_async`).
- Copia a `DATABASE_URL` do addon/serviço para as env vars do serviço **api**.

## 2. Ollama (só embeddings)

- Novo serviço Railway, **Deploy from Docker Image** → `ollama/ollama`.
- Volume persistente para os modelos baixados (evita re-download a cada deploy).
- Comando de start (ou job one-off após subir): `ollama pull nomic-embed-text`.
- Rede **privada** Railway (não expor porta pública) — a api acessa via hostname interno, ex.: `OLLAMA_BASE_URL=http://ollama.railway.internal:11434`.

## 3. API (`api`)

Variáveis de ambiente (ver `.env.example`):

- `DATABASE_URL` — do Postgres.
- `OLLAMA_BASE_URL` — hostname interno do serviço Ollama.
- `GROQ_API_KEY`, `GROQ_CHAT_MODEL` — conta Groq (console.groq.com), configurar **usage limit** lá também como rede de segurança extra.
- `TR4_API_KEY` — obrigatório antes de tornar o domínio público (ver seção 5).
- `MAX_MONTHLY_SPEND_USD`, `RATE_LIMIT_PER_MINUTE` — teto de gasto e abuso.

Deploy via Dockerfile do repo (Railway detecta automaticamente). Healthcheck: `GET /health`.

## 4. Ingestão (`tr4-sync`)

Rodar localmente (ou via `railway run`) apontando pro `DATABASE_URL`/`OLLAMA_BASE_URL` de produção:

```bash
tr4-sync --whatsapp ./data/raw/grupo.txt \
         --facebook-json ./data/raw/fb.json \
         --docs ./data/manuals \
         --web-seeds ./data/seeds/tr4_sources.txt \
         --clear
```

Repetir periodicamente (cron local, GitHub Actions, ou Railway Cron Job apontando pro mesmo comando) para manter a base atualizada. `--web-seeds` busca o conteúdo real das URLs em `data/seeds/tr4_sources.txt` — não depende de nenhum dado copiado manualmente, então uma fonte que mudar de conteúdo é refletida no próximo sync.

## 5. Segurança mínima antes de abrir ao público

- [ ] `TR4_API_KEY` definido — sem isso `/chat` fica aberto sem autenticação (ver `src/tr4/auth.py`).
- [ ] `MAX_MONTHLY_SPEND_USD` definido e usage limit configurado também no console Groq.
- [ ] `RATE_LIMIT_PER_MINUTE` ajustado ao tráfego esperado (limitador em memória — só protege 1 instância; se escalar horizontalmente, trocar por um store externo).
- [ ] HTTPS (Railway já fornece TLS no domínio gerado).
- [ ] Ollama e Postgres **não** expostos publicamente, só rede privada Railway.
- [ ] Volume do Postgres com backup (Railway oferece snapshots no addon gerenciado).
- [ ] Frontend/cliente que consumir a API busca `GET /terms` e só chama `/chat` com `accepted_terms: true` depois do usuário confirmar — sem isso a API recusa com 403 (ver `src/tr4/legal.py`).
- [ ] Se houver frontend público (widget web, etc.): configurar Cloudflare Turnstile (`TURNSTILE_SECRET_KEY` no backend + site key pública no frontend, renderizando o widget e mandando `captcha_token`) — sem isso, `/chat` aceita sem captcha e um bot pode gerar custo automatizando pergunta (ver `src/tr4/captcha.py`).

## 6. Observabilidade

- Healthcheck: `GET /health`.
- Logs do serviço `api` no painel Railway.
- Gasto acumulado do mês: `SELECT SUM(cost_usd) FROM tr4_usage WHERE date_trunc('month', ts) = date_trunc('month', now());`
