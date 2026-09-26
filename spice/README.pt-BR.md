# AI usage

Suas cotas de IA, direto no painel do Cinnamon. Uma olhada basta para saber quanto de cada assinatura já foi usado — sem abas de navegador, sem CLIs, sem adivinhação.

![Prévia da janela completa](https://raw.githubusercontent.com/ClaudioDrews/cinnamon-ai-usage/main/docs/demo.png)

## O que mostra

Janelas de uso, saldos e gastos ao vivo de até nove serviços:

Codex · Claude Code · Antigravity · Grok / xAI · Nous Portal · OpenCode Go · DeepSeek · OpenRouter · Meta AI (Muse Code)

- **Um clique** — os cinco serviços mais recentes, cada um com sua barra.
- **Passar o mouse** — todos os serviços, horário da coleta e avisos na dica.
- **Clique duplo** — a janela completa, com todas as métricas, renovações e origens.
- **O ícone do robô** segue o seu tema, fica amarelo aos 70% usados e vermelho aos 90%.

## Privacidade desde o projeto

- As chaves ficam no cofre do sistema — nunca no applet, nunca exibidas de volta.
- Só leitura: nunca executa inferência, compra crédito ou muda um plano.
- Leituras antigas ou com falha vêm marcadas como tal; nada é inventado como zero.

## Detalhes

- Interface em Português (Brasil) e English; acompanha o idioma da sessão.
- Atualização automática a cada 2 minutos (configurável); Atualizar força uma na hora.
- Só precisa do que o Mint já traz: Cinnamon, Python 3 e as ligações GTK.
- **Primeira execução:** nada configurado ainda? O próprio menu diz quantos serviços estão sem leitura e aponta para **Credenciais…**, a janela onde as chaves entram.

[Código-fonte e documentação completa](https://github.com/ClaudioDrews/cinnamon-ai-usage) · [Reportar um problema](https://github.com/ClaudioDrews/cinnamon-ai-usage/issues) · [Read in English](https://github.com/ClaudioDrews/cinnamon-ai-usage/blob/main/spice/README.md)

Nota: o conector do Claude Code está implementado, mas ainda não verificado numa conta real — relatos de assinantes são bem-vindos.
