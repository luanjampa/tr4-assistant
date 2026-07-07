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

1. **Frontend de chat pra pessoas usarem** — decidido: página web simples (HTML+JS puro,
   chama `/chat` via fetch, mostra `/terms` antes, aceite explícito). **Ainda não construída.**
   Até isso existir, o backend está no ar mas ninguém do grupo consegue conversar com ele
   de verdade (só via curl/Postman).
2. Turnstile (captcha) só faz sentido quando o frontend acima existir — precisa criar o
   site (público) no Cloudflare Turnstile e configurar `TURNSTILE_SECRET_KEY` em produção
   (hoje vazio, captcha desligado).
3. `tr4-sync` não está agendado — ingestão é manual até agora. Rodar de novo periodicamente
   (cron local, GitHub Actions, ou Render Cron Job) pra manter a base atualizada.
4. Grupo Facebook: só o caminho manual (`--facebook-manual`) existe. Sem app Meta aprovado,
   sem Graph API.
5. Ninguém real testou o `/chat` em uso — só eu, via curl. Vale validar com gente do grupo
   depois que o frontend existir.

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
