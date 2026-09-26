# Contrato v1

Coletor: `python3 backend/collector.py collect [--force]`; imprime apenas JSON UTF-8. Sem argumentos usa collect. `read` devolve cache sem rede; `demo` devolve dados sintéticos SEM escrever cache. Janela: `python3 backend/window.py [--demo]`. Tudo funciona na árvore fonte e instalado: backend/ ao lado de applet/ na fonte; instalado o backend/ fica dentro do diretório do applet. Applet localiza backend/ dentro de metadata.path; instalação copia.

Configuração não secreta: ~/.config/cinnamon-ai-usage/config.json. Cache privado: ~/.cache/cinnamon-ai-usage/snapshot.json. TTL padrão 120 segundos. IDs: codex, antigravity, grok, nous, opencode, deepseek, openrouter, meta.

Saída exemplo (nenhum segredo):
```json
{"schema_version":1,"generated_at":"2026-09-25T20:00:00Z","services":[{"id":"codex","label":"Codex","status":"ok","message":"","source":"codex app-server","read_at":"2026-09-25T20:00:00Z","last_used_at":null,"recency_basis":"unknown","metrics":[{"id":"primary","label":"Janela de 5 h","kind":"quota","used_percent":42.0,"value":null,"currency":null,"window_seconds":18000,"reset_at":"2026-09-25T22:00:00Z"}]}]}
```

Status: ok, stale (dados anteriores preservados após falha), unavailable (fonte ausente/serviço fechado), unconfigured (credencial ausente), error, disabled. Percentual ausente é null, nunca zero. kind: quota, balance, spend. value em unidade monetária com currency; somente quota tem used_percent. Podem existir várias métricas por serviço. source, message são textos públicos saneados, nunca resposta bruta ou exception de rede.

last_used_at NÃO é read_at. Só é preenchido quando consumo aumenta ou saldo diminui entre leituras comparáveis; recency_basis=observed_change, uma aproximação. Futuramente timestamps efetivos de uso podem usar reported. Primeira leitura tem recência desconhecida. Cache preserva a recência. Sem histórico não inventar: o menu mostra até cinco linhas, primeiro as com uso observado e depois as de leitura mais recente, sinalizando em cada linha quando não há uso observado; serviço sem leitura não entra no menu. Ordenar decrescente; não reordenar durante menu aberto. Incluir último valor stale com aviso se serviço recente falhar.

Applet: IconApplet com ícone simbólico (SVG de fundo transparente), sem borda; a cor de alerta vai no próprio ícone — amarelo a partir de 70% usado e vermelho a partir de 90%, pela maior cota válida, ignorando leituras antigas e métricas sem percentual; sem alerta o ícone volta à cor do tema. Clique simples abre menu com até cinco linhas: primeiro as com uso observado, depois as de leitura mais recente; serviço sem leitura não ocupa linha (aparece no balão e na janela). Clique duplo no ícone abre a janela (usar atraso curto baseado no double-click-time do sistema para distinguir com segurança; cancelar timeout ao remover). Menu também tem Ver todos, Atualizar, Credenciais…, Configurações nativas se disponível. Snapshot carregado assincronamente via Gio.Subprocess.communicate_utf8_async, watchdog e limpeza. Sem spawn shell, sem rede síncrona, sem acesso a segredo no applet. Iniciar collect quando carrega e a cada TTL. Forçar apenas a pedido. Exibir indicador de erro separadamente de quota. Barra por composição St/CSS.

Janela GTK3: Gtk.Application id local.claudio.CinnamonAIUsage, instância única; janela rolável com todos os serviços configurados/consultáveis e estados dos demais, preferencialmente separando 'Sem leitura' em expander. Exibe todas as métricas, reset, última atualização, origem, recência aproximada. Atualizar executa coletor assíncrono; não bloquear GTK. Para demo, fixture do subcomando demo claramente marcada. Não acessar credenciais. Timeout global de coleta 50s; watchdog UI 60s. Locale pt-BR. Tema do sistema.

## Credenciais

Ordem por variável, sempre sem shell: (1) cofre do sistema (Secret Service), onde a janela `credentials_window.py` grava o que a pessoa digita; (2) arquivo `NOME=VALOR` no caminho de `config.json:credentials_path`; (3) variáveis de ambiente. Serviços que autenticam por login usam `token_files` (JSON; primeiro `access_token` em qualquer nível). O programa não conhece caminho fixo de credencial de nenhuma máquina. Nenhum valor é impresso, registrado, exibido de volta ou escrito no cache; `config.json` guarda apenas caminhos, em modo 0600. Sem valor, o serviço fica `unconfigured`.

A janela de credenciais é processo separado, mostra de onde cada valor viria, limpa o campo depois de salvar e oferece remover do cofre. A janela de uso não lê segredo: só abre a de credenciais.

## Meta AI (Muse Code)

O id `meta` lê a assinatura do aplicativo Muse Code — janela corrente (`window`, com `window_duration_mins`) e `weekly` —, não a cobrança por uso da API. A única fonte é `POST https://api.meta.ai/muse-code/key`, a mesma chamada que o cliente faz ao subir: ela emite credencial, mas é idempotente (verificado em 26/09/2026: devolve a mesma `api_key` e o `auth.json` do cliente fica intacto). O token vem do login do próprio Muse Code, na ordem que o cliente usa: `token_files.meta` na configuração, `$MUSE_AUTH_PATH`, `$XDG_CONFIG_HOME/muse/auth.json` e `~/.config/muse/auth.json`; o arquivo é lido pelo primeiro `access_token` em qualquer nível do JSON. Sem token o serviço fica `unconfigured` e nenhuma chamada é feita. O conector não executa o binário do Muse Code.

Como não há documentação de limite de uso, o conector impõe intervalo mínimo próprio: `meta.min_interval_seconds`, padrão 900 s, aceitando de 300 s a 24 h. Dentro do intervalo não há nova chamada: a leitura anterior é reaproveitada do cache privado `~/.cache/cinnamon-ai-usage/meta.json` (0600, só o digest da conta, nunca o token) e mantém o `read_at` real, de modo que o serviço aparece como leitura antiga quando passa o TTL. Falha de rede ou resposta sem percentual não viram zero: o serviço fica `error`/`unavailable` e o valor anterior é preservado.

O percentual é inteiro e a Meta avisa que pode passar de 100: a barra vai até 100 e a nota do serviço informa o número relatado. Não há métrica de gasto em dólar para este serviço — a API de modelos não publica preço, e contagem de tokens sem preço não cabe neste contrato.

## Detalhes de implementação

`collect --ttl N` permite ao applet passar seu intervalo (30–3600 s). `worker ID` é um comando interno, limitado a 30 s, executado em paralelo pelo coletor. O snapshot privado tem `_identity` (digest da identidade da conta/chave) para reiniciar a comparação quando a conta muda; `collect/read` removem esse campo antes de imprimir. `demo` nunca usa cache ou credenciais.

Uma consulta de cota só produz recência quando o percentual aumenta na mesma janela/reset. Saldos só produzem recência aproximada quando diminuem; valores de gasto quando aumentam. Não há afirmação de horário exato nem atribuição a um agente. UI não altera ordenação durante o menu aberto; reabrir aplica a nova leitura. Credenciais são lidas somente pelos trabalhadores de seus respectivos provedores.
