# Validação da versão 0.1.0 — 25 e 26/09/2026

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

O teste JS usa substitutos das APIs para exercitar comportamento. Uma tentativa anterior de criar um palco Clutter isolado falhou com Unknown input backend no fork do Muffin. A validação integrada abaixo foi feita posteriormente dentro do processo Cinnamon real.

## Teste no painel real

Em 25/09/2026, após pedido do usuário, instalamos e ativamos `ai-usage@claudio.local` no painel. A configuração anterior foi salva em `~/.local/share/cinnamon/ai-usage-backups/panel-before-20260925-190727.json`; a ativação acrescentou somente a nova instância e avançou o próximo identificador.

- Carregamento confirmado pelo Cinnamon e cinco fontes com status OK na instância do painel; Antigravity indisponível e Grok sem configuração.
- Eventos de mouse via XTest no ícone: clique simples abre/fecha o menu; duplo abre a janela GTK; outro duplo mantém uma única janela.
- Menu com sete serviços sintéticos identificados como demonstração exibiu somente os cinco mais recentes. Captura visual e medidas dos atores confirmaram as barras; o snapshot real foi restaurado imediatamente, sem gravar a demonstração no cache.
- Corrigidos dois problemas observados: estilo vazio gerava avisos do parser St (removido com `null`); largura pedida de 290 pixels podia ser ampliada pelo tema, distorcendo a proporção. O preenchimento agora acompanha a largura alocada. Barras de 25%, 33%, 41% e 57% ficaram dentro de 0,5 ponto percentual, incluindo arredondamento de pixels.
- Recarregado somente o applet, sem reiniciar Cinnamon. Nenhum novo aviso do applet apareceu no log após as correções. Teste JS inclui regressão para a largura ampliada pelo tema; 24 testes Python continuaram passando.

O applet permanece habilitado para uso. O menu real começa vazio até detectar mudança de consumo entre coletas; a janela completa já mostra os dados disponíveis. Imagens com dados reais não foram incorporadas ao repositório.

## Feedback: balão e ícone de robô

Em 25/09/2026, o PNG fornecido pelo usuário foi incorporado sem alterações em `assets/robot-head.png`. Instalador inclui o asset; painel, ícone da janela e cabeçalho GTK usam a mesma imagem. O alerta permanece como contorno amarelo (70% usado) ou vermelho (90%), sem substituir o robô. Considera todas as cotas válidas, excluindo leituras antigas e valores monetários sem percentual.

O balão nativo agora apresenta o resumo de cada serviço, horário de coleta, estado de atualização e a cota responsável pelo aviso. A entrada real do ponteiro, simulada por XTest, confirmou o balão visível sem clique. Uma primeira sondagem sem garantir saída/entrada do ponteiro não o encontrou visível; a verificação com entrada explícita passou. Captura visual confirmou resumo e robô no painel; imagem real descartada após conferência.

Teste JS cobre limites de 70/90%, cota fora do histórico recente, exclusão de leitura antiga do alerta e apresentação de saldo. Os 24 testes Python passam. Smoke GTK confirmou o ícone carregado, cabeçalho visível e encerramento limpo. Atualização instalada e recarregada somente no applet, mantendo a posição escolhida pelo usuário.

## Segunda rodada — credenciais, cinco linhas e ícone simbólico

Em 25/09/2026, a partir do retorno do usuário, cinco mudanças foram implementadas e verificadas na máquina real.

- **Menu de um clique:** até cinco linhas, primeiro as com uso observado e depois as de leitura mais recente; serviço sem leitura não ocupa linha. No painel real, o menu abriu com DeepSeek, Codex, Antigravity, Nous Portal e OpenCode Go (OpenRouter fora do corte), cada linha de cota com sua barra e as linhas sem uso observado identificadas; Grok apareceu no aviso “1 serviço(s) sem leitura” e as ações Ver todos/Atualizar/Credenciais…/Configurações… ficaram no rodapé. Texto conferido por leitura dos atores do menu e por captura de tela.
- **Nous sem duplicação:** quando saldo total e saldo do plano coincidem, resta uma linha; a de renovação e a de recargas (se diferentes de zero) permanecem.
- **Credenciais:** `backend/credentials.py` resolve na ordem cofre do sistema (Secret Service) → arquivo `NOME=VALOR` indicado em `config.json:credentials_path` → variáveis de ambiente, mais `token_files` para login OAuth em JSON. `backend/credentials_window.py` grava no cofre, mostra a origem de cada valor, limpa o campo após salvar, permite remover e permite escolher qualquer caminho. Nenhum caminho de credencial de máquina específica ficou no repositório; a configuração local desta máquina só aponta caminhos. Verificado: cofre disponível, `set`/`get`/`names`/`delete` em processos separados; janela montada com cinco campos, estados de origem corretos e gravação de `config.json` em modo 0600 em diretório temporário.
- **Antigravity:** o parser passou a ler os créditos do plano (`monthlyPromptCredits`/`availablePromptCredits` e o equivalente de fluxo) e o nome real de cada modelo em `label`, ignorando entradas sem fração válida. Consulta real com a IDE aberta devolveu os créditos do plano e os modelos nomeados; o desvio de semântica do projeto de referência (famílias de modelo tratadas como janelas de cinco horas/sete dias) não foi copiado.
- **Ícone:** `assets/robot-head-symbolic.svg` substituiu o PNG (removido); o applet usa `set_applet_icon_symbolic_path`, sem borda, e a cor do alerta é aplicada no próprio ícone. Três estados conferidos por contagem de pixels exatos na faixa do painel: 450 pixels `#e01b24` com a cota do Antigravity acima do limiar crítico, 369 pixels `#e5a50a` com uma cota de 75% injetada apenas em memória (snapshot real restaurado logo depois, sem gravar no cache) e 423 pixels `#e1e1e1`, a cor de primeiro plano do tema, quando nenhuma cota atingia o limiar. O nó de tema do ícone resolve `color` para (224, 27, 36) no estado crítico, confirmando que o ícone simbólico é recolorido pelo CSS.

Verificações desta rodada: 29 testes Python offline, teste JS do applet (limite de cinco incluindo o preenchimento por leitura recente, exclusão de serviço sem leitura, prioridade do uso observado, ações do menu incluindo Credenciais…), `node --check`, `compileall`, CJS real com as APIs St/Gio, instalação em diretório temporário com execução do backend instalado, consulta real dos sete provedores e recarga apenas do applet no painel sem reiniciar o Cinnamon e sem novos avisos no log.

Correção encontrada na própria verificação: sem alerta, `_paintIcon` passava string vazia ao `set_style` do ícone e o parser do St registrava dois `cr_parser_new_from_buf`. O estilo agora é `null` nesse caso; contagem de avisos no log antes e depois permaneceu igual (6), inclusive no estado sem alerta, e o teste JS passa a exigir `null` em vez de string vazia.

O aparelho de inspeção do painel merece registro: `imports.ui.appletManager.applets[uuid]` é o espaço de nomes do diretório do applet, não a lista de instâncias; a instância viva foi localizada percorrendo as caixas dos painéis e lendo `_delegate._uuid`. A cor aplicada por `set_style` aparece no `get_theme_node().get_color('color')` e nos pixels do painel.

## Painel completo: a chave da xAI entrou

Com a management key e o `team_id` colocados pelo usuário no arquivo de credenciais desta máquina, os sete serviços passaram a ter leitura — Grok inclusive, que era o único buraco. Ajustes feitos no mesmo dia:

- O conector passou a aceitar `XAI_MANAGEMENT_KEY` além de `XAI_MANAGEMENT_API_KEY`, e a ler o time de `XAI_TEAM_ID` no arquivo de credenciais quando não houver `grok.team_id` na configuração. `team_id` continua validado contra `[A-Za-z0-9_-]{1,100}` antes de entrar na URL.
- O sinal de `total.val` deixou de ser incerteza: a xAI registra a recarga como valor negativo no razão e o total é a soma das mudanças, de modo que o crédito disponível é o módulo desse total. O applet passou a exibir o crédito disponível e a registrar a convenção na nota do serviço.
- Com consumo, a segunda métrica mostra o percentual sobre os créditos recarregados (soma das recargas), que é o único denominador honesto da chave; sem consumo, nada de barra em zero. `GET /postpaid/invoice/preview` desta conta devolve `effectiveSpendingLimit` 0 e nenhuma linha de fatura, ou seja, o pós-pago está desligado e só os créditos pré-pagos serão usados.
- A janela de credenciais ganhou o campo não secreto do `team_id` e reconhece o nome alternativo da chave ao mostrar a origem do valor.

Verificado: 35 testes Python, `compileall`, smoke GTK da janela de credenciais (cinco campos de chave, origem de cada valor, `team_id` lido do arquivo, gravação 0600 em diretório temporário), consulta real dos sete provedores pelo coletor e menu do painel com Grok/xAI entre as cinco linhas, sem aviso novo no log. O Antigravity aparece como leitura antiga porque o servidor da IDE não estava no ar no momento da coleta.

## Oitava fonte: a assinatura do Muse Code (Meta)

Em 26/09/2026, a pedido do usuário, o applet passou a ler a assinatura do Muse Code. Antes de escrever o conector, a rota foi sondada com a credencial real da conta, em chamada única e com cópia de segurança do `auth.json`.

O que a sondagem mostrou:

- **Idempotência confirmada.** `POST https://api.meta.ai/muse-code/key` com o token OAuth devolveu HTTP 200 e a **mesma** `api_key` já guardada (sha256 idêntico), sem qualquer alteração no `auth.json` (bytes e mtime preservados). A chave continuou válida: `GET /muse-code/models` respondeu 200 com os quatro modelos depois da chamada.
- **A quota vem no retorno:** `subs_usage.window` (percentual usado, duração da janela em minutos e `resets_at` em epoch) e `subs_usage.weekly` (percentual da semana), mais `tier`. Os horários de renovação vieram coerentes com o painel `/cost` do documento de análise. O struct tem dezesseis campos; a lista anterior de quinze estava incompleta (`base_url`, `payment_method` e `show_subs_upsell` ficaram de fora).
- **Preço não é servido pela API.** `GET /muse-code/models` devolveu 3388 bytes e quatro modelos **sem nenhum campo de custo** (também sem resultado com `x-client-id: tbh:tui`, `?include=cost` e `?verbose=true`; a rota aceita apenas a chave de API, não o token OAuth). Sem preço verificável, o gasto em dólar saiu do escopo: a contagem de tokens não entra no contrato, que só conhece cota, saldo e gasto.
- **Consumo local é agregável** caso se volte ao assunto: cada registro de uso nos arquivos `session.jsonl` do CLI traz `owner.run_id`, e o modelo de cada execução está em `run.model.configured`; os registros marcados com `reported: true` casaram com um modelo na varredura feita.

O conector implementado faz uma coisa só: lê a assinatura, com intervalo mínimo próprio (`meta.min_interval_seconds`, padrão 900 s) e cache privado `~/.cache/cinnamon-ai-usage/meta.json` (0600, apenas o digest da conta). Dentro do intervalo não há nova chamada e a leitura reaproveitada mantém o `read_at` real, de modo que o applet a apresenta como leitura antiga quando passa o TTL. Sem login do Muse Code o serviço fica `unconfigured` e nenhuma chamada sai; falha de rede ou resposta sem percentual fica `error`/`unavailable`, nunca 0%.

O caminho do login não foi adivinhado: o script do launcher embutido no binário resolve `$MUSE_AUTH_PATH` e, sem ele, `$XDG_CONFIG_HOME/muse/auth.json` ou `$HOME/.config/muse/auth.json`. O conector segue essa mesma ordem, com `token_files.meta` da configuração à frente, e não executa o binário em momento algum — por isso a versão do CLI instalada não altera o comportamento do applet. O README traz a nota de compatibilidade; o conector foi exercitado da última vez com o Muse Code 1.4.0 (`1.4.0-R4161.1`) e `auth.json` em `schema_version` 1.

Verificado: 46 testes Python offline (11 novos só deste conector: duas janelas, percentual ausente, valor acima de 100 limitado na barra com o número real na nota, ausência de vazamento de credencial/conta na mensagem, POST com o token e o cabeçalho esperados, reaproveitamento dentro do intervalo, leitura vencida, ordem de resolução do arquivo de login, limites do intervalo, falha sem zero inventado), `compileall`, `node --check`, teste JS do applet, teste CJS real, leitura real pelo `worker meta` (0,7 s na primeira chamada com rede, 0,06 s na segunda, sem rede) e conferência do arquivo de cache em 0600.

## Nona fonte: a assinatura do Claude Code

Em 26/09/2026, a pedido do usuário, entrou o nono conector. O ponto de partida foi um rascunho de 307 linhas gerado por outro assistente (guardado fora do repositório), analisado linha a linha antes da integração. O rascunho serviu de mapa — encontrou o token OAuth local, o formato `claudeAiOauth.accessToken` com `expiresAt`, a checagem de token vencido e a intenção de falhar suave —, mas a mecânica de coleta foi recusada:

- **Consumia a cota que mede.** Para arrancar os cabeçalhos `anthropic-ratelimit-unified-*`, o rascunho fazia um POST em `/v1/messages` com `max_tokens: 1`. Com coleta a cada dois minutos, o applet gastaria a cota do usuário para exibi-la — o oposto do que o projeto se permite. O conector usa a rota de leitura `GET /api/oauth/usage`, a mesma que a CLI usa no `/usage`.
- **Nomes de cabeçalho adivinhados**, e um deles sem sentido: `anthropic-ratelimit-unified-5h-utilization` e `-7d-reset` não existem na documentação pública (o padrão é `-{claim}-utilization` e `-reset`), e havia fallback para `anthropic-ratelimit-unified-status`, que traz `allowed`/`rejected` e não percentual.
- **Heurística que inventa número:** `f * 100 if f <= 1 else f` converteria 0,4% em 40%. O conector usa o percentual como veio.
- **Cabeçalhos brutos dentro do resultado** (que iriam para o cache) e o caminho da máquina na mensagem de erro, ambos contra as regras do contrato; além de ramos de macOS e Windows sem função num applet do Cinnamon no Linux e de um User-Agent imitando a CLI.

O que foi verificado nesta máquina, e o que não:

- **A rota existe.** `GET https://api.anthropic.com/api/oauth/usage` com token inválido devolveu **401** (não 404), com erro JSON — o caminho é real e o modo de falha cai no mapeamento de 401 já existente. O corpo reclamou de `x-api-key`, não do `Bearer`; sem token válido não dá para saber se isso importa.
- **Sem conta, não há chamada.** Sem CLI `claude`, sem `~/.claude/.credentials.json` e sem variáveis Anthropic nesta máquina (verificado), o serviço fica `unconfigured`, com métricas vazias e nenhuma requisição — o estado de quem instalar o applet sem Claude Code.
- **Diagnóstico sem valores.** `collector.py diag claude` devolve origem do caminho, existência do arquivo, nomes dos campos do login, estrutura da resposta (nomes, tipos e faixa dos números) e as janelas reconhecidas — sem valores, sem caminho da máquina e sem credencial. É o que um relato de issue precisa.
- **61 testes offline** (15 novos: objetos planos e lista `limits`, tipo desconhecido ignorado, ausência de percentual, escala não rescalada, ordem de resolução do login, token vencido sem chamada, GET com `anthropic-beta` e sem corpo, reaproveitamento dentro do intervalo, cache 0600 só com digest, resposta desconhecida pedindo diagnóstico, 401 sem zero inventado, nota sem vazamento e diagnóstico sem valores).
- **Não verificado:** a consulta com conta real — não há assinatura nem chave da Anthropic aqui. Ficam em aberto a aceitação do `Bearer` nessa rota, o formato atual do `.credentials.json` e a escala do percentual. O README declara isso na tabela de estado e na seção do serviço.

A rota e o formato vieram de documentação pública de terceiros, não da Anthropic: o projeto `wakamex/ccusage`, as issues `anthropics/claude-code#27915` e `#18121` e a documentação da própria Anthropic sobre onde as credenciais ficam (`~/.claude/.credentials.json`, `CLAUDE_CONFIG_DIR`, Keychain no macOS).

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
- [Claude Code: onde ficam as credenciais](https://code.claude.com/docs/en/authentication) e [variáveis de ambiente](https://code.claude.com/docs/en/env-vars) — `~/.claude/.credentials.json`, `CLAUDE_CONFIG_DIR` e Keychain no macOS.
- Rota de uso do Claude Code e formato da resposta: [ccusage](https://pypi.org/project/ccusage/) (`wakamex/ccusage`) e [anthropics/claude-code#27915](https://github.com/anthropics/claude-code/issues/27915) — `GET /api/oauth/usage` com `anthropic-beta: oauth-2025-04-20`, objetos `five_hour`/`seven_day` e a lista `limits` com `kind`, `percent` e `resets_at`. Não usamos o POST em `/v1/messages` para raspar cabeçalhos de limite: consome a cota exibida.

## Limitações conhecidas

A recência deriva de mudanças entre coletas: é aproximada, começa sem histórico, inclui consumo da conta fora deste computador e não comprova qual agente fez a chamada. O conector Nous não renova tokens; o login é gerido pelo Hermes. Antigravity depende da IDE e de um protocolo local experimental. Go pode mudar seu endpoint. Alteração de formato mostra ausência/erro e preserva último valor válido, sem zerar cotas. O conector do **Claude Code** é o único publicado sem verificação em conta real: a rota e o formato seguem a documentação pública da comunidade, e o README declara isso na tabela e na seção do serviço. Interface completa não implementa notificações nem gráficos históricos nesta versão.
