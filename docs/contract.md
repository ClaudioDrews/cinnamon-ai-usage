# Contrato v1

Coletor: `python3 backend/collector.py collect [--force]`; imprime apenas JSON UTF-8. Sem argumentos usa collect. `read` devolve cache sem rede; `demo` devolve dados sintéticos SEM escrever cache. Janela: `python3 backend/window.py [--demo]`. Tudo funciona na árvore fonte e instalado: backend/ ao lado de applet/ na fonte; instalado o backend/ fica dentro do diretório do applet. Applet localiza backend/ dentro de metadata.path; instalação copia.

Configuração não secreta: ~/.config/cinnamon-ai-usage/config.json. Cache privado: ~/.cache/cinnamon-ai-usage/snapshot.json. TTL padrão 120 segundos. IDs: codex, antigravity, grok, nous, opencode, deepseek, openrouter.

Saída exemplo (nenhum segredo):
```json
{"schema_version":1,"generated_at":"2026-09-25T20:00:00Z","services":[{"id":"codex","label":"Codex","status":"ok","message":"","source":"codex app-server","read_at":"2026-09-25T20:00:00Z","last_used_at":null,"recency_basis":"unknown","metrics":[{"id":"primary","label":"Janela de 5 h","kind":"quota","used_percent":42.0,"value":null,"currency":null,"window_seconds":18000,"reset_at":"2026-09-25T22:00:00Z"}]}]}
```

Status: ok, stale (dados anteriores preservados após falha), unavailable (fonte ausente/serviço fechado), unconfigured (credencial ausente), error, disabled. Percentual ausente é null, nunca zero. kind: quota, balance, spend. value em unidade monetária com currency; somente quota tem used_percent. Podem existir várias métricas por serviço. source, message são textos públicos saneados, nunca resposta bruta ou exception de rede.

last_used_at NÃO é read_at. Só é preenchido quando consumo aumenta ou saldo diminui entre leituras comparáveis; recency_basis=observed_change, uma aproximação. Futuramente timestamps efetivos de uso podem usar reported. Primeira leitura tem recência desconhecida. Cache preserva a recência. Sem histórico não inventar: menu até 5 serviços com last_used_at conhecido; se vazio, explicar 'O histórico aparece após detectar uso' + Ver todos. Ordenar decrescente; não reordenar durante menu aberto. Incluir último valor stale com aviso se serviço recente falhar.

Applet: IconApplet; clique simples abre menu compacto; clique duplo no ícone abre janela (usar atraso curto baseado no double-click-time do sistema para distinguir com segurança; cancelar timeout ao remover). Menu também tem Ver todos, Atualizar, Configurações nativas se disponível. Snapshot carregado assincronamente via Gio.Subprocess.communicate_utf8_async, watchdog e limpeza. Sem spawn shell, sem rede síncrona, sem acesso a segredo no applet. Iniciar collect quando carrega e a cada TTL. Forçar apenas a pedido. Exibir indicador de erro separadamente de quota. Barra por composição St/CSS.

Janela GTK3: Gtk.Application id local.claudio.CinnamonAIUsage, instância única; janela rolável com todos os serviços configurados/consultáveis e estados dos demais, preferencialmente separando 'Sem leitura' em expander. Exibe todas as métricas, reset, última atualização, origem, recência aproximada. Atualizar executa coletor assíncrono; não bloquear GTK. Para demo, fixture do subcomando demo claramente marcada. Não acessar credenciais. Timeout global de coleta 50s; watchdog UI 60s. Locale pt-BR. Tema do sistema.

## Detalhes de implementação

`collect --ttl N` permite ao applet passar seu intervalo (30–3600 s). `worker ID` é um comando interno, limitado a 30 s, executado em paralelo pelo coletor. O snapshot privado tem `_identity` (digest da identidade da conta/chave) para reiniciar a comparação quando a conta muda; `collect/read` removem esse campo antes de imprimir. `demo` nunca usa cache ou credenciais.

Uma consulta de cota só produz recência quando o percentual aumenta na mesma janela/reset. Saldos só produzem recência aproximada quando diminuem; valores de gasto quando aumentam. Não há afirmação de horário exato nem atribuição a um agente. UI não altera ordenação durante o menu aberto; reabrir aplica a nova leitura. Credenciais são lidas somente pelos trabalhadores de seus respectivos provedores.
