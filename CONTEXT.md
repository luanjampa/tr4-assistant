# Contexto pra próxima sessão

Leia isso primeiro. Detalhe técnico/arquitetura fica em `CLAUDE.md`; passo a passo de infra em `docs/DEPLOY.md`.

## Estado atual

**No ar e funcionando de ponta a ponta**: https://tr4-assistant.onrender.com

Stack: Render (API) + Neon (Postgres+pgvector) + Cloudflare (embeddings + AI Gateway com
spend limit) + Groq (chat). Testado com pergunta real, respondeu certo, citou fonte.

Base de conhecimento: 1685 chunks (WhatsApp filtrado, manual oficial 2014, pesquisa web,
1 relato de dono). Guardrails, budget cap, captcha (código pronto), prompt-injection
testado (10/10, ver `scripts/injection_tests.py`).

Contas usadas (todas de `luansouza.jampa@gmail.com` / GitHub `luanjampa`): Render, Neon,
Cloudflare, Groq, GitHub (`github.com/luanjampa/tr4-assistant`, privado). Credenciais
reais ficam nos dashboards/`.env` — não duplicadas aqui.

## O que FALTA (nessa ordem, provavelmente)

1. ~~Frontend de chat~~ — **construído, no ar em produção, testado em browser real**
   (`frontend/index.html`+`app.js`+`style.css`). Servido pelo FastAPI na **raiz do
   domínio** (`GET /`, `StaticFiles` montado em `/` — registrado *depois* das rotas de
   API pra não conflitar; ver `app.py`). Mostra `/terms` antes do primeiro uso (aceite
   fica em `localStorage`, mas quem garante o consent de verdade é o backend via
   `accepted_terms:true` em toda request). `GET /config` devolve `TR4_API_KEY`/
   `TURNSTILE_SITE_KEY` pro JS montar o header `X-API-Key` e o widget.
   3 bugs reais só apareceram testando em browser de verdade (não pegariam em code
   review nem em teste local com curl):
   - CSS `.overlay[hidden]` faltando — atributo `hidden` do HTML perdia pra `.overlay{display:flex}`
     no cascade, termos nunca escondiam de verdade, cliques ficavam bloqueados por trás.
   - `size: "invisible"` no Turnstile não é mais valor válido da API (só compact/flexible/normal) —
     `render()` lançava exceção, widget nunca existia.
   - Faltava `execution: "execute"` no Turnstile — sem isso o widget auto-executa no
     render, e o `reset()+execute()` manual do app.js batia numa execução já rolando e
     travava pra sempre (`getTurnstileToken()` nunca resolvia, `/chat` nunca era chamado).
   Também corrigido um bug **só em produção** (Docker, `pip install .` não-editável):
   `FRONTEND_DIR` calculado via `__file__` apontava pro site-packages, não pro repo —
   trocado por `Path.cwd()` (Makefile e `CMD` do Dockerfile sempre rodam da raiz do repo).
2. ~~Turnstile~~ — **configurado de verdade**. Site "tr4-assistant" criado no Cloudflare
   Turnstile (hosts: `tr4-assistant.onrender.com` + `localhost`), `TURNSTILE_SITE_KEY`/
   `TURNSTILE_SECRET_KEY` setados local e em produção (Render). `/chat` já exige
   `captcha_token` válido.
3. **PII fix**: `/chat` devolvia `context_previews` (trechos brutos recuperados da base,
   até 280 char, sem redigir) — pra chunks `whatsapp_window` isso incluía nome real de
   gente do grupo, visível a qualquer visitante da web (não só no frontend — no corpo da
   resposta da API). Removido do contrato público (`ChatResponse` não tem mais esse campo;
   `rag.py`/`answer_question` segue retornando as previews internamente pra quem quiser
   usar por script, mas `app.py` não repassa mais pro cliente). Frontend não mostra mais
   "Fontes usadas".
4. `tr4-sync` não está agendado — ingestão é manual até agora. Rodar de novo periodicamente
   (cron local, GitHub Actions, ou Render Cron Job) pra manter a base atualizada.
5. Grupo Facebook: só o caminho manual (`--facebook-manual`) existe. Sem app Meta aprovado,
   sem Graph API.
6. Testado por mim (curl + browser real, local e produção). Ninguém do grupo usou ainda —
   vale validar com gente de verdade agora que o link (`https://tr4-assistant.onrender.com`)
   já é diretamente o chat.

## Decisões/achados importantes que não são óbvios lendo só o código

- Railway foi descartado: hard spend-limit lá é por workspace inteiro, não por projeto —
  misturaria com outros 2 projetos do usuário na mesma conta.
- Groq: modelo mais barato (`llama-3.1-8b-instant`) escolhido de propósito pelo usuário,
  mesmo sabendo que é mais fraco em seguir instrução complexa — testado 10/10 contra
  prompt injection depois da troca, aguentou.
- Embeddings saíram do Ollama (self-hosted) pro Cloudflare Workers AI especificamente pra
  não precisar de nenhum servidor sempre ligado no novo stack sem Railway.
- Bug real de produção corrigido: pooler do Neon não garante `search_path=public` em toda
  conexão — `store.py` força isso manualmente agora (ver comentário no código).
- Conteúdo do WhatsApp é filtrado por relevância (keyword + classificador Groq) antes de
  indexar — grupo tem muito assunto que não é sobre TR4, isso já foi tratado.
