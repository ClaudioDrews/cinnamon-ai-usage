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
