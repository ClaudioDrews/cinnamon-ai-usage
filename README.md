# Uso de IA para Cinnamon

Applet local para consultar cotas, gastos e saldos de serviços de IA no Linux Mint Cinnamon.

- **Clique simples:** até cinco serviços com atividade recente detectada.
- **Passe o mouse:** balão com resumo por serviço, horário da coleta e avisos.
- **Clique duplo:** janela completa, com todas as métricas disponíveis.
- **Ver todos os serviços…:** alternativa visível ao clique duplo.
- **Atualizar:** consulta manual. A atualização automática usa 120 segundos por padrão.

O menu não muda de ordem enquanto estiver aberto. A janela usa o tema GTK do sistema, tem rolagem e separa os serviços sem leitura.

O robô fornecido pelo usuário aparece no painel e na janela. Seu contorno fica amarelo a partir de **70% usado** e vermelho a partir de **90% usado**, considerando a maior porcentagem entre todas as janelas de todos os serviços com leitura válida, inclusive fora dos cinco recentes. O balão identifica a cota responsável. Saldos e gastos sem teto conhecido não acionam esse alerta; leituras antigas são identificadas no balão e excluídas do cálculo da cor. O PNG original é preservado em `assets/robot-head.png`.

## Estado da primeira versão

Verificado em 25/09/2026, Mint 22.3 / Cinnamon 6.6.9:

| Serviço | Leitura implementada | Verificação local |
|---|---|---|
| Codex | Todas as janelas devolvidas pelo app-server, com renovação | Consulta autenticada OK, duas janelas |
| OpenCode Go | Janela móvel, semanal e mensal | Consulta autenticada OK, três janelas |
| Nous Portal | Saldo total, saldo do plano e recargas; renovação do plano | Consulta autenticada OK via login OAuth do Hermes |
| DeepSeek | Saldo por moeda | Consulta autenticada OK |
| OpenRouter | Gasto mensal/acumulado; percentual se a chave tiver limite | Consulta autenticada OK; chave local sem limite |
| Antigravity | Cotas por modelo ou créditos, via servidor local | Parser testado; IDE fechada, consulta real pendente |
| Grok / xAI | Saldo pré-pago da API de gerenciamento | Falta chave de gerenciamento e team_id |

O conector Grok monitora **a API xAI**, não a assinatura SuperGrok/Grok Build. Esses planos exigem outra fonte. Antigravity e Go usam interfaces que podem mudar; alterações são tratadas como indisponibilidade, sem transformar ausência de dado em zero.

[Prévia da janela com dados fictícios](docs/demo.png)

## Executar sem instalar

Requer Python 3, PyGObject/GTK3 e Cinnamon/CJS, já disponíveis no Mint deste projeto. Node serve apenas à verificação de JavaScript, não à execução do applet. Não há pacotes pip/npm.

```bash
cd /caminho/do/repositorio
python3 backend/window.py --demo   # janela com dados fictícios
python3 backend/window.py          # consultas reais de uso/saldo
python3 backend/collector.py collect
python3 backend/collector.py read  # cache, sem consultas de rede
```

Demo não lê credenciais nem altera o cache. A coleta real não faz inferência, compras, recargas ou mudanças de plano.

## Instalar para o usuário

```bash
python3 install.py
```

O instalador copia o applet e o backend para `~/.local/share/cinnamon/applets/ai-usage@claudio.local/`. Preserve o código fonte neste repositório. Uma versão anterior é movida para `~/.local/share/cinnamon/ai-usage-backups/` antes da substituição.

Depois, abra **Configurações do sistema → Applets → Gerenciar**, procure **Uso de IA** e adicione ao painel. O instalador não ativa applets nem reinicia Cinnamon. Após atualização, remova e adicione o applet para carregar a nova versão. Preferências de intervalo e pausa ficam em **Configurar**, no menu de contexto.

Para desinstalar, remova primeiro o applet do painel e apague somente o diretório `ai-usage@claudio.local` da pasta de applets. Cache e preferências são separados e podem ser preservados.

## Credenciais e configurações

As preferências do Cinnamon não guardam segredos. O backend lê, sem executar como shell, somente os nomes necessários em `~/.config/agentes/credenciais.env`, ou usa as variáveis de ambiente correspondentes:

- `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`.
- `OPENCODE_GO_API_KEY`, com alternativa `OPENCODE_API_KEY`.
- `XAI_MANAGEMENT_API_KEY` para saldo da API xAI. A chave comum de inferência não substitui essa chave.

Codex usa o login existente por `codex app-server`; Nous usa o access token de `~/.hermes/auth.json`. Não alteramos nem renovamos credenciais do Hermes: se expirarem, renove o login no próprio Hermes. Antigravity é sondado somente no loopback e exige o servidor da IDE em execução. Não confunda a variável `ANTIGRAVITY_API_KEY` com o login da IDE.

Configuração opcional **sem segredos** em `~/.config/cinnamon-ai-usage/config.json`:

```json
{
  "refresh_seconds": 120,
  "enabled": {"grok": false},
  "grok": {"team_id": "SEU_TEAM_ID"}
}
```

O intervalo selecionado no applet vale para suas consultas. A janela independente usa o TTL do arquivo acima (120 segundos se ausente). O botão Atualizar força a coleta em ambos. Desativar um provedor no arquivo o remove das próximas coletas; uma alteração pode aguardar o TTL ou Atualizar.

O cache fica em `~/.cache/cinnamon-ai-usage/` (diretório 0700, snapshot 0600), com gravação atômica e trava para impedir consultas duplicadas. Guarda métricas e histórico, sem tokens nem respostas brutas. Campos privados de identificação usam digest SHA-256 para evitar comparar contas diferentes e são omitidos da saída pública.

## O que significa “recente”

A primeira consulta cria a referência. Só uma mudança posterior de consumo ou saldo atribui recência aproximada. Atualizar o saldo não conta como utilizar o serviço. Por isso o menu pode começar vazio, oferecendo **Ver todos**.

A ordem registra **atividade observada**, não o horário exato de cada chamada. Coletas simultâneas podem produzir empates; usos fora desta máquina também podem afetar o consumo da conta. Expiração de créditos pode parecer consumo, e uma recarga simultânea pode ocultá-lo. Não associamos esse horário a um agente específico. Mudanças de conta ou de janela reiniciam a comparação. Falhas preservam a última leitura, marcada como antiga.

O saldo do DeepSeek e do Nous não vira consumo mensal por divisão por um orçamento. Créditos de recarga e rollover precisam ser considerados; nesta versão exibimos valores monetários.

## Desenvolvimento e verificação

```bash
python3 -m unittest discover -s tests -v
node --check applet/applet.js
node tests/test_applet.js
GI_TYPELIB_PATH=/usr/lib/x86_64-linux-gnu/cinnamon:/usr/lib/x86_64-linux-gnu/muffin \
LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/cinnamon:/usr/lib/x86_64-linux-gnu/muffin \
cjs tests/check_cjs_api.js
python3 -m compileall -q backend
python3 tests/smoke_gtk.py /tmp/ai-usage-demo.png  # requer sessão gráfica
```

Os testes offline cobrem parsers, ausência versus zero, renovação, recência, troca de conta, falha preservando cache e isolamento de segredos. O teste JS simula o ambiente do applet para conferir cliques, timers, coleta e limite de cinco; não substitui a validação no painel real. O teste GTK abre e fecha uma janela de demonstração.

Arquitetura e formato: [docs/contract.md](docs/contract.md). Evidências, fontes e limitações: [docs/validation.md](docs/validation.md).

Referência de projeto: [omarchy-ai-usage](https://github.com/rodrigo-sntg/omarchy-ai-usage), de Rodrigo Santiago, licença MIT. Esta implementação usa um contrato próprio para preservar janelas e modelos distintos.
