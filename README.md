# Uso de IA para Cinnamon

Applet local para consultar cotas, gastos e saldos de serviços de IA no Linux Mint Cinnamon.

- **Clique simples:** até cinco serviços, primeiro os com uso observado e depois os de leitura mais recente (quem não tem leitura não ocupa linha).
- **Passe o mouse:** balão com resumo por serviço, horário da coleta e avisos.
- **Clique duplo:** janela completa, com todas as métricas disponíveis.
- **Ver todos os serviços…:** alternativa visível ao clique duplo.
- **Credenciais…:** guarda chaves no cofre do sistema e aponta arquivos de credenciais.
- **Atualizar:** consulta manual. A atualização automática usa 120 segundos por padrão.

O menu não muda de ordem enquanto estiver aberto. A janela usa o tema GTK do sistema, tem rolagem e separa os serviços sem leitura.

O robô aparece no painel como ícone simbólico: em uso normal ele segue a cor do tema, fica **amarelo a partir de 70% usado** e **vermelho a partir de 90%**, considerando a maior porcentagem entre todas as janelas de todos os serviços com leitura válida. Saldos e gastos sem teto conhecido não acionam a cor; leituras antigas são identificadas no balão e excluídas do cálculo. O SVG está em `assets/robot-head-symbolic.svg` (fundo transparente, `fill:currentColor`).

## Estado da primeira versão

Verificado em 25/09/2026, Mint 22.3 / Cinnamon 6.6.9:

| Serviço | Leitura implementada | Verificação local |
|---|---|---|
| Codex | Todas as janelas devolvidas pelo app-server, com renovação | Consulta autenticada OK, duas janelas |
| OpenCode Go | Janela móvel, semanal e mensal | Consulta autenticada OK, três janelas |
| Nous Portal | Saldo total, saldo do plano e recargas; renovação do plano | Consulta autenticada OK via login OAuth do Hermes |
| DeepSeek | Saldo por moeda | Consulta autenticada OK |
| OpenRouter | Gasto mensal/acumulado; percentual se a chave tiver limite | Consulta autenticada OK; chave local sem limite |
| Antigravity | Créditos do plano e cotas por modelo, via servidor local | Consulta autenticada OK com o IDE aberto: dois créditos e três modelos |
| Grok / xAI | Saldo pré-pago da API de gerenciamento | Consulta autenticada OK com management key e team_id; a assinatura Grok não aparece aqui |

O conector Grok monitora **a API xAI**, não a assinatura SuperGrok/Grok Build. Esses planos exigem outra fonte. Antigravity e Go usam interfaces que podem mudar; alterações são tratadas como indisponibilidade, sem transformar ausência de dado em zero.

[Prévia da janela com dados fictícios](docs/demo.png)

## Executar sem instalar

Requer Python 3, PyGObject/GTK3 e Cinnamon/CJS, já disponíveis no Mint deste projeto. Node serve apenas à verificação de JavaScript, não à execução do applet. Não há pacotes pip/npm.

```bash
cd /caminho/do/repositorio
python3 backend/window.py --demo   # janela com dados fictícios
python3 backend/window.py          # consultas reais de uso/saldo
python3 backend/credentials_window.py  # chaves no cofre e caminhos de arquivo
python3 backend/collector.py collect
python3 backend/collector.py read  # cache, sem consultas de rede
python3 backend/collector.py worker <serviço>  # testa um provedor só
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

As preferências do Cinnamon não guardam segredos. Cada variável é procurada nesta ordem:

1. **Cofre do sistema** (Secret Service / gnome-keyring) — é onde a janela **Credenciais…** grava o que a pessoa digita. Nada é exibido de volta: a janela só informa de onde o valor viria.
2. **Arquivo indicado por você** em `config.json`, na chave `credentials_path`, no formato `NOME=VALOR` — qualquer caminho (`~/.env`, `~/.config/secrets.env`, o que você usar). O arquivo é lido sem shell: `$(...)` e crases ficam literais.
3. **Variáveis de ambiente** do processo.

Para serviços que autenticam por login, e não por chave, `token_files` aponta um JSON; o primeiro `access_token` encontrado, em qualquer nível, é usado (nunca copiado para o cache).

Variáveis reconhecidas: `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `OPENCODE_GO_API_KEY` (ou `OPENCODE_API_KEY`), `XAI_MANAGEMENT_API_KEY` (saldo da API xAI; a chave de inferência não serve) e `NOUS_PORTAL_TOKEN`.

### Chave da xAI (Grok)

O saldo não está na chave de inferência: ele vive na **Management API**, que exige uma **management key** — uma credencial separada, criada em `console.x.ai` → *Settings* → *Management Keys*. Para criá-la e usá-la, o usuário da conta precisa da permissão `Management Keys` **Read + Write** na página *Users* do Console; sem ela o item não aparece e quem habilita é o administrador do time. Os ACLs (`api-key:model`, `api-key:endpoint`) valem para as chaves de inferência e não substituem essa permissão.

O conector usa dois dados:

- `XAI_MANAGEMENT_KEY` (aceito também como `XAI_MANAGEMENT_API_KEY`) — a management key (Bearer). Coloque-a pelo botão **Credenciais…** do applet, que grava no cofre do sistema.
- `XAI_TEAM_ID` no próprio arquivo de credenciais, ou `grok.team_id` em `~/.config/cinnamon-ai-usage/config.json`, ou o campo correspondente na janela **Credenciais…** — o identificador do time, visível na URL do Console (`console.x.ai/team/<team_id>/…`). O valor da configuração tem precedência.

Endpoints que interessam para um painel:

| Uso | Endpoint |
| --- | --- |
| Saldo pré-pago e mudanças (usado hoje) | `GET /v1/billing/teams/{team_id}/prepaid/balance` |
| Conferir se a chave é uma management key válida (não exige ACL) | `GET /auth/management-keys/validation` |
| Gasto do período e teto vigente (dá percentual real) | `GET /v1/billing/teams/{team_id}/postpaid/invoice/preview` |
| Limites de gasto configurados | `GET /v1/billing/teams/{team_id}/postpaid/spending-limits` |
| Uso por modelo e período | `POST /v1/billing/teams/{team_id}/usage` |

Base de todos: `https://management-api.x.ai`. O saldo vem em `total.val`, em centavos, e **com o sinal invertido**: a xAI registra a recarga como valor negativo no razão e o total é a soma das mudanças, de modo que o crédito disponível é o módulo desse total. O applet exibe o crédito disponível e registra a convenção na nota do serviço.

Quando houver consumo de crédito pré-pago, a segunda linha do serviço mostra o percentual usado sobre o total recarregado (a soma das recargas), porque a chave não traz teto próprio. Enquanto não há consumo, aparece só o saldo — nada de barra em zero inventada.

A management key é uma credencial poderosa: ela cria e revoga chaves de API e mexe em cobrança. Guarde-a no cofre, não em arquivo versionado.

Codex usa o login do próprio CLI (`codex login`) em `~/.codex/auth.json`. Antigravity é sondado somente no loopback e exige o servidor da IDE em execução; não confunda `ANTIGRAVITY_API_KEY` com o login da IDE.

Configuração opcional **sem segredos** em `~/.config/cinnamon-ai-usage/config.json`:

```json
{
  "refresh_seconds": 120,
  "credentials_path": "~/.config/secrets.env",
  "token_files": {"nous": "~/.local/share/meu-login/auth.json"},
  "enabled": {"grok": false},
  "grok": {"team_id": "SEU_TEAM_ID"}
}
```

A gravação do arquivo é atômica e em modo 0600. O intervalo selecionado no applet vale para suas consultas. A janela independente usa o TTL do arquivo acima (120 segundos se ausente). O botão Atualizar força a coleta em ambos. Desativar um provedor no arquivo o remove das próximas coletas; uma alteração pode aguardar o TTL ou Atualizar.

O cache fica em `~/.cache/cinnamon-ai-usage/` (diretório 0700, snapshot 0600), com gravação atômica e trava para impedir consultas duplicadas. Guarda métricas e histórico, sem tokens nem respostas brutas. Campos privados de identificação usam digest SHA-256 para evitar comparar contas diferentes e são omitidos da saída pública.

## O que significa “recente”

A primeira consulta cria a referência. Só uma mudança posterior de consumo ou saldo atribui recência aproximada. Atualizar o saldo não conta como utilizar o serviço. Por isso o clique abre com até cinco linhas: primeiro as que têm uso observado e, para completar, as de leitura mais recente — cada linha diz se há uso observado. Serviços sem leitura alguma não ocupam linha do menu; eles aparecem no balão e na janela.

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
