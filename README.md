# TR4 Assistant

Assistente com **RAG** sobre WhatsApp/Facebook, manuais (PDF) e pesquisa web, respostas via **Groq** (Llama). Embeddings via **Cloudflare Workers AI** (bge-m3) — sem servidor pra manter. Base vetorial em **Postgres + pgvector**. As mensagens dos utilizadores **não** são gravadas na base de conhecimento.

## Requisitos

- Python 3.11+
- Conta [Groq](https://console.groq.com) (API key) para o chat
- Conta [Cloudflare](https://dash.cloudflare.com) (Workers AI) para embeddings — `IA > Workers AI > Crie um token de API Workers AI`, mais o Account ID da conta
- (Recomendado) Um AI Gateway na mesma conta Cloudflare com Spend Limit configurado — `IA > Gateway de AI > Criar um gateway personalizado`, liga "Spend Limits" (valor/mês, ex. $5) e "Gateway autenticado" (gera um token à parte). Sem isso, `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN` sozinhos chamam Workers AI direto, sem nenhum teto de gasto nesse provider.
- Postgres com extensão `pgvector` (`docker compose up -d postgres` sobe um local)

Pra produção (ver seção Deploy online): conta [Render](https://render.com) (hospeda a API) e conta [Neon](https://neon.com) (Postgres+pgvector) — ambas grátis, sem cartão.

## Setup

```bash
cd /caminho/para/tr4
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # preencher GROQ_API_KEY, ajustar DATABASE_URL se preciso
docker compose up -d postgres
```

## 1. Indexar dados (batch)

```bash
# WhatsApp export (.txt) e/ou JSON Facebook (via Graph API, se/quando aprovado)
tr4-sync --whatsapp ./data/raw/grupo.txt --facebook-json ./data/raw/fb.json

# Posts do grupo Facebook colados à mão (ver seção abaixo)
tr4-sync --facebook-manual ./data/facebook_manual

# Manuais oficiais (PDF/txt/md)
tr4-sync --docs ./data/manuals

# Relatos do dono/preparador (experiência real, não é manual oficial)
tr4-sync --owner-notes ./data/notes

# Pesquisa web (busca o conteúdo real das URLs em data/seeds/tr4_sources.txt)
tr4-sync --web-seeds ./data/seeds/tr4_sources.txt

# Tudo junto, reindexando do zero — ou `make sync-clear`
tr4-sync --whatsapp ./data/raw/grupo.txt --facebook-json ./data/raw/fb.json \
         --facebook-manual ./data/facebook_manual --docs ./data/manuals \
         --owner-notes ./data/notes --web-seeds ./data/seeds/tr4_sources.txt --clear
```

Repete de tempos a tempos (`make sync`); sem `--clear`, faz upsert (mesmo `id` substitui o chunk).

### Como conseguir o export do WhatsApp

No app: abre o grupo → ⋮ (menu) → Mais → Exportar conversa → **Sem mídia** (menor, e mídia não é indexada mesmo). Isso gera um `.txt` no formato `[DD/MM/AAAA, HH:MM] Nome: mensagem`, que `ingest/whatsapp.py` já sabe ler. Copia pra `./data/raw/grupo.txt` e roda `tr4-sync --whatsapp`.

### Como catalogar o grupo Facebook (sem Graph API aprovada, sem scraping)

Sem app Meta aprovado, o caminho é manual: abre o post/comentário relevante no grupo, copia o texto pra um `.txt` em `./data/facebook_manual/` (um arquivo por post, ou vários no mesmo arquivo separados por linha em branco — o chunker cuida do resto). Não precisa formatar, mas ajuda incluir data/autor se lembrar: `[12/03/2024] João: troquei o coxim do motor, MR510312 serviu certinho`. Roda `tr4-sync --facebook-manual ./data/facebook_manual`. Esse conteúdo entra com `kind=facebook_post` — mesmo nível de confiança do Facebook via API (relato de grupo, não fonte oficial), nunca é tratado como manual.

## 2. API de chat

```bash
uvicorn tr4.app:app --reload --host 127.0.0.1 --port 8000
```

- `GET /health`
- `GET /terms` — texto de termos/disclaimer (mostrar ao usuário antes do primeiro uso)
- `POST /chat` — header `X-API-Key: <TR4_API_KEY>` (se configurada) + JSON `{"message": "...", "accepted_terms": true, "captcha_token": "..."}`. Sem `accepted_terms: true`, responde 403 com o texto dos termos. `captcha_token` só é exigido se `TURNSTILE_SECRET_KEY` estiver configurada (ver seção Guardrails). Toda resposta também traz um campo `disclaimer` fixo lembrando que os dados são coletados automaticamente e podem conter erro.

Pra testar fazendo perguntas direto no terminal (mostra os termos, pede aceite, depois vira um chat):

```bash
make chat
```

### Frontend web

A raiz do domínio (`GET /`) é o próprio chat — página HTML+JS estática em `frontend/`, servida pelo FastAPI via `StaticFiles` montado em `/` (mesma origem, sem CORS; rotas de API como `/health`/`/terms`/`/config`/`/chat` são registradas antes do mount e continuam funcionando normalmente). Mostra os termos antes do primeiro uso, aceite fica em `localStorage` mas quem garante o consent de verdade é o backend (`accepted_terms: true` em toda request). `GET /config` devolve `TR4_API_KEY`/`TURNSTILE_SITE_KEY` pro JS montar o header e o widget — deixam de ser segredo real assim que vão pro browser, rate limit + budget cap + Turnstile são os controles de abuso de verdade a partir daí. A resposta de `/chat` não traz os trechos brutos recuperados da base (`context_previews` foi removido do contrato público) — WhatsApp indexado tem nome real de gente do grupo, não faz sentido expor isso a qualquer visitante da web. Local: `make api` e abrir `http://127.0.0.1:8000/`. Em produção: `https://tr4-assistant.onrender.com/`.

## Configuração

Variáveis em `.env` (ver `.env.example`): Cloudflare (embeddings), Groq (chat), Postgres, API key, rate limit, teto de gasto mensal.

## Guardrails

- Prompt de sistema em `src/tr4/prompts/system.txt` — inclui defesa contra prompt injection via CONTEXT (conteúdo raspado é tratado como dado, nunca como instrução) e contra pedidos de segredo/off-topic disfarçados de "só uma pergunta rápida"/role-play.
- Escopo em `src/tr4/guardrails.py`: fast-path por palavra-chave pros casos óbvios (grátis) + classificador Groq (poucos tokens) pra zona cinzenta — nem lista de peça, nem lista de "assunto de fora" precisam cobrir tudo.
- Teto de gasto mensal em `src/tr4/budget.py` (`MAX_MONTHLY_SPEND_USD`) — acima do limite, `/chat` responde sem chamar o Groq (isso inclui o classificador de escopo)
- Rate limit por IP em `src/tr4/rate_limit.py` (`RATE_LIMIT_PER_MINUTE`)
- API key em `src/tr4/auth.py` (`TR4_API_KEY`) — obrigatório antes de expor publicamente
- Termos/disclaimer em `src/tr4/legal.py` — gate de aceite (`accepted_terms`) antes de responder, e aviso de "confira sempre" em toda resposta (`disclaimer`). Isento de responsabilidade por dado errado/desatualizado coletado automaticamente.
- Perguntas sem boa resposta ficam registradas em `tr4_gaps` (`src/tr4/gaps.py`) — `make gaps` mostra as mais repetidas, pra decidir o que pesquisar/ingerir a seguir.
- Captcha (Cloudflare Turnstile) em `src/tr4/captcha.py` (`TURNSTILE_SECRET_KEY`) + `frontend/app.js` (`TURNSTILE_SITE_KEY`, via `GET /config`) — barra bot automatizando pergunta e gerando custo. Widget em modo `interaction-only` (só aparece se o visitante for considerado arriscado). Sem `TURNSTILE_SECRET_KEY`, `/chat` aceita sem captcha. Site criado em [dash.cloudflare.com/?to=/:account/turnstile](https://dash.cloudflare.com/?to=/:account/turnstile) (widget "tr4-assistant", hosts `tr4-assistant.onrender.com` + `localhost`); chaves reais em `.env` local e nas env vars do Render — nunca commitadas. Testado também com as chaves de teste oficiais da Cloudflare (`1x0000...AA` sempre passa, `2x0000...AA` sempre falha).
- Teto de gasto real no Cloudflare (embeddings) via **AI Gateway** (`CLOUDFLARE_GATEWAY_ID`/`CLOUDFLARE_GATEWAY_TOKEN`) — diferente do budget do Groq (que é lógica no código), esse é um limite de verdade configurado no próprio dashboard Cloudflare (Spend Limits, beta), bloqueia a chamada ao bater o valor/mês. Gateway também tem rate limit (50 req/min) e cache de resposta (5min — seguro pra embeddings, mesma entrada sempre gera o mesmo vetor).

### Testar guardrails e prompt injection

```bash
make injection-test   # precisa de GROQ_API_KEY real — testa bypass de verdade, não só o fast-path
```

`scripts/injection_tests.py` cobre: burlar o escopo via menção a "tr4", override de instrução, base64/leetspeak, extração de system prompt/API key, role-play (DAN), e — o mais específico dessa arquitetura — injeção de instrução dentro do CONTEXT (simula uma página raspada ou post do grupo malicioso tentando sequestrar o bot). Resultado é lido manualmente (`FALHOU` = gap confirmado, `REVISAR` = ambíguo).

## Deploy online

**No ar**: Render (API) + Neon (Postgres+pgvector) + Cloudflare (embeddings/captcha) em vez de Railway, pra não misturar billing/limite com outros projetos na mesma conta. Custo real: **$0/mês**, dentro do free tier de cada um.

- **Render** ([render.com](https://render.com), signup: [dashboard.render.com/register](https://dashboard.render.com/register)) — free tier: 750h/mês, 512MB RAM, dorme após 15min sem uso (~30-50s pra acordar na próxima pergunta). Sem cartão.
- **Neon** ([neon.com](https://neon.com), signup: [console.neon.tech/signup](https://console.neon.tech/signup)) — free tier: 100 compute-hours/mês, 0.5GB de storage (nosso banco tem ~23MB, sobra bastante), sem expiração por calendário, "acorda" em <500ms. Sem cartão.
- **Cloudflare** — Workers AI + AI Gateway com Spend Limit real configurado (ver seção Guardrails).

Passo a passo completo, incluindo um gotcha real de produção (search_path do pooler do Neon) já corrigido no código: **[docs/DEPLOY.md](docs/DEPLOY.md)**.

Com Docker (dev local, sobe Postgres + API):

```bash
docker compose up -d
```

## Monitoramento de custo (checklist periódico)

Tudo hoje roda nos free tiers ($0/mês esperado), mas nenhum é infinito — depois que o
frontend for público, vale checar isso com alguma frequência (ex.: semanal no primeiro
mês, depois mensal):

- **Groq** ([console.groq.com](https://console.groq.com), aba Usage/Billing) — confirma
  que segue no free tier e que o rate limit (6000 tokens/min por API key) não está sendo
  estourado com frequência (`chat_groq.py` já faz retry em 429, mas retry constante é
  sinal de tráfego maior que o esperado). `MAX_MONTHLY_SPEND_USD` (`budget.py`) é um teto
  lógico no código — só protege se a tabela `tr4_usage` estiver de fato registrando uso;
  vale conferir com `make gaps` / uma query direta de vez em quando.
- **Cloudflare AI Gateway** ([dash.cloudflare.com](https://dash.cloudflare.com) > IA >
  Gateway de AI > `tr4-assistant`) — o Spend Limit ($5/mês) é uma feature **beta**
  configurada só no dashboard, não no código; vale olhar o gráfico de gasto real de vez
  em quando pra confirmar que está cortando de verdade, não só configurado.
- **Cloudflare Workers AI** (mesma conta, aba Workers AI > Uso) — free tier é por
  "neurons/dia"; conferir se o volume de embeddings (1 chamada por pergunta do chat) não
  está perto do limite diário.
- **Render** (dashboard do serviço `tr4-assistant`) — free tier é 750h/mês; com 1 serviço
  só e sleep automático após 15min idle, não deveria estourar, mas confirma no dashboard.
- **Neon** (dashboard do projeto) — free tier é 100 compute-hours/mês + 0.5GB storage
  (banco atual ~23MB); confirma que compute-hours não está subindo rápido demais com mais
  gente usando.
- **Cloudflare Turnstile** — sem custo (grátis, sem limite), só serve de filtro anti-bot;
  não precisa monitorar gasto, só checar que o widget continua passando gente real
  (poucos falsos positivos reclamados no grupo).

## Próximos passos sugeridos

- Implementar `fetch_group_feed_stub` em `facebook_batch.py` com Graph API após app Meta aprovado
- Agendar `tr4-sync` com cron ou Railway Cron Job
- Métricas e logs de ingestão
- Revisar periodicamente `data/seeds/tr4_sources.txt` (adicionar/remover fontes)
