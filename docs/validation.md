# Validação da versão 0.1.0 — 25/09/2026

## Resultado

Implementação local em Linux Mint 22.3, Cinnamon 6.6.9, Python 3.12 e CJS 115.1. Dados reais foram consultados apenas para leitura de uso/saldo; valores pessoais e credenciais não foram incorporados ao repositório.

- **Codex:** app-server retornou duas métricas de cota.
- **OpenCode Go:** a chave disponível retornou três métricas por `usage.rolling/weekly/monthly`, com `percent` e `resetsAt`. A primeira sondagem sem o User-Agent do aplicativo recebeu HTTP 403; as consultas do coletor passaram. Rótulo Zen no inventário não demonstrava ausência do Go.
- **Nous:** `GET /api/oauth/account` com OAuth existente no Hermes retornou três saldos. O campo `paid_service_access` fornece os valores; a renovação do plano vem de `subscription.current_period_end`. Nenhuma concessão de escopo, compra ou renovação de token foi feita pelo applet.
- **DeepSeek:** leitura de saldo válida.
- **OpenRouter:** leitura de gasto mensal/acumulado válida; sem teto na chave, nenhuma barra percentual é inventada.
- **Antigravity:** servidor da IDE ausente nesta sessão; conector e parser implementados, consulta real ainda não validada.
- **Grok/xAI:** chave de gerenciamento não disponível. Conector condicionado a `XAI_MANAGEMENT_API_KEY` e `grok.team_id`; não equivale a monitorar a assinatura do aplicativo Grok.

## Verificações

- 24 testes Python offline: formatos dos cinco provedores, parser Antigravity, ausência/zero, limites, rollover, recência, mudança de conta/janela, falhas e cache privado.
- Sintaxe dos módulos Python e JavaScript.
- Teste JS do applet: construção, argumentos Gio, retorno em tupla, clique simples/duplo, limite de cinco, ordenação estável enquanto aberto, erro preservando leitura e limpeza de timers.
- CJS real: propriedades e métodos St usados pelo applet e captura assíncrona de Gio.Subprocess conferidos.
- GTK real: janela de demonstração, sete serviços renderizados, consulta assíncrona finalizada, widgets visíveis e fechamento limpo.
- Instalação em diretório temporário: primeira instalação, execução do backend instalado e atualização preservando cópia anterior.

O teste JS usa substitutos das APIs para exercitar comportamento; não é uma carga do applet no processo Cinnamon. Uma tentativa de criar um palco Clutter isolado falhou com Unknown input backend no fork do Muffin; substituímos esse experimento por inspeção das APIs reais, sem afirmar teste visual do St. A ativação e interação no painel real permanecem pendentes. Não alteramos a lista de applets habilitados.

## Delegação e revisão

Hermes implementou a base da janela GTK em `backend/window.py`; OpenCode implementou a primeira versão de `applet/`. Codex definiu o contrato, implementou os conectores/cache/testes/instalador e revisou as entregas. A revisão corrigiu APIs do Cinnamon, assinatura e captura de saída de Gio.Subprocess, temporizadores, composição St, fechamento GTK e apresentação de renovação. Passar em `node --check` sozinho não teria detectado esses erros de integração.

Sessões de entrega: as sessões dos agentes que participaram ficaram de fora deste documento, junto com logs integrais, credenciais, bases SQLite e respostas de contas — nada disso pertence a um repositório publicado. O que fica registrado é o resultado verificável: comandos, testes e o que cada um mostrou.

## Fontes

- [Codex App Server](https://developers.openai.com/codex/app-server/) — initialize, initialized, account/rateLimits/read, usedPercent, windowDurationMins, resetsAt e rateLimitsByLimitId.
- [OpenRouter: chave atual](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key).
- [DeepSeek: saldo](https://api-docs.deepseek.com/api/get-user-balance/).
- [xAI: cobrança na Management API](https://docs.x.ai/developers/rest-api-reference/management/billing).
- [omarchy-ai-usage](https://github.com/rodrigo-sntg/omarchy-ai-usage), branch master, scripts ai-usage-codex.sh e ai-usage-antigravity.sh — referência de protocolo; não usamos o mapeamento de famílias Antigravity para janelas fictícias de cinco horas/sete dias.
- Código do Cinnamon instalado: `/usr/share/cinnamon/js/ui/applet.js`, `popupMenu.js`, `settings.js`, applets nativos e esquema `org.cinnamon.desktop.peripherals.mouse`.
- Código do Hermes instalado: `hermes_cli/nous_account.py`, `agent/billing_usage.py` e testes correspondentes — contrato de leitura OAuth do Nous; formato conferido com resposta real.

## Limitações conhecidas

A recência deriva de mudanças entre coletas: é aproximada, começa sem histórico, inclui consumo da conta fora deste computador e não comprova qual agente fez a chamada. O conector Nous não renova tokens; o login é gerido pelo Hermes. Antigravity depende da IDE e de um protocolo local experimental. Go pode mudar seu endpoint. Alteração de formato mostra ausência/erro e preserva último valor válido, sem zerar cotas. Interface completa não implementa notificações nem gráficos históricos nesta versão.
