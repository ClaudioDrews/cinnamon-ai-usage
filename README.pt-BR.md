[Português do Brasil](README.pt-BR.md) | [English](README.md)

# Uso de IA para Cinnamon

![Banner em pixel art do Cinnamon AI Usage: um robô de tela verde numa mesa à noite, três monitores com consultas de cota, gráfico de uso e código, um menu com Uso de IA selecionado e uma barra do painel com a porcentagem de cada serviço](docs/banner.png)

Versão 0.2.0. Applet local para consultar cotas, gastos e saldos de serviços de IA no Linux Mint Cinnamon.

- **Clique simples:** até cinco serviços, primeiro os com uso observado e depois os de leitura mais recente (quem não tem leitura não ocupa linha).
- **Passe o mouse:** balão com resumo por serviço, horário da coleta e avisos.
- **Clique duplo:** janela completa, com todas as métricas disponíveis.
- **Ver todos os serviços…:** alternativa visível ao clique duplo.
- **Credenciais…:** guarda chaves no cofre do sistema e aponta arquivos de credenciais.
- **Atualizar:** consulta manual. A atualização automática usa 120 segundos por padrão.

O menu não muda de ordem enquanto estiver aberto. A janela usa o tema GTK do sistema, tem rolagem e separa os serviços sem leitura.

Falha e leitura antiga aparecem nomeadas, separadas da cota: `Falha na leitura: Codex, Grok` em vermelho no menu e no balão, e `Leitura antiga: Antigravity` sem destaque — a cor do robô continua respondendo só a percentual de cota, e o applet confere a **idade** da leitura, não só o estado: uma cota de uma hora atrás não colore o ícone nem com a coleta pausada. Na janela, o aviso de leitura antiga diz o que aconteceu — intervalo vencido é diferente de atualização que falhou.

O robô aparece no painel como ícone simbólico: em uso normal ele segue a cor do tema, fica **amarelo a partir de 70% usado** e **vermelho a partir de 90%**, considerando a maior porcentagem entre todas as janelas de todos os serviços com leitura válida. Saldos e gastos sem teto conhecido não acionam a cor; leituras antigas são identificadas no balão e excluídas do cálculo. O SVG está em `assets/robot-head-symbolic.svg` (fundo transparente, `fill:currentColor`).

## Idioma

- A interface segue o idioma da sessão; em Preferências dá para fixar um idioma ou deixar `auto`.
- Idioma fixado só vale se o catálogo dele existir; sem catálogo, a interface responde em inglês.
- Trocar o idioma não descarta leitura, não força coleta e não marca nada como antigo.
- Os textos ficam em `locale/`; `sh scripts/i18n.sh` reconstrói o catálogo. Detalhes em [docs/i18n.md](docs/i18n.md).

## Estado da primeira versão

Verificado em 25/09/2026, Mint 22.3 / Cinnamon 6.6.9:

| Serviço | Leitura implementada | Verificação local |
|---|---|---|
| Codex | Todas as janelas devolvidas pelo app-server, com renovação | Consulta autenticada OK, duas janelas |
| OpenCode Go | Janela móvel, semanal e mensal | Consulta autenticada OK, três janelas |
| Nous Portal | Saldo total, saldo do plano e recargas; renovação do plano | Consulta autenticada OK via login OAuth do Hermes |
| DeepSeek | Saldo por moeda | Consulta autenticada OK |
| OpenRouter | Gasto mensal/acumulado; percentual se a chave tiver limite | Consulta autenticada OK; sem teto na chave, nenhuma barra inventada |
| Antigravity | Créditos do plano e cotas por modelo, via servidor local | Consulta autenticada OK com o IDE aberto: créditos do plano e modelos nomeados |
| Grok / xAI | Saldo pré-pago da API de gerenciamento | Consulta autenticada OK com management key e team_id; a assinatura Grok não aparece aqui |
| Meta AI (Muse Code) | Janela corrente e semanal da assinatura | Consulta autenticada OK, as duas janelas; em 26/09/2026 a rota falhou uma vez e devolveu os metadados da conta **sem** o bloco de uso (leitura anterior preservada), voltando a responder nas leituras seguintes. Veja a seção do serviço |
| Claude Code | Janela de 5 h e semanal da assinatura (e janelas por modelo, quando vierem) | **Não verificada**: sem conta Anthropic nesta máquina; rota, cabeçalho, campo de credencial e escala 0–100 coincidem com os de um applet já aceito na loja (`claude-usage@mtwebster`), o que não é o mesmo que medir aqui |

O conector Grok monitora **a API xAI**, não a assinatura SuperGrok/Grok Build. Esses planos exigem outra fonte. Antigravity e Go usam interfaces que podem mudar; alterações são tratadas como indisponibilidade, sem transformar ausência de dado em zero. O conector Meta lê a **assinatura** do Muse Code (janela corrente e semanal), não a cobrança por uso da API da Meta. O conector do Claude Code é o único publicado **sem verificação em conta real** — está implementado, testado contra o formato que um applet já aceito na loja usa e rotulado como não verificado; a seção dele explica o que falta e como relatar.

[Prévia da janela com dados fictícios](docs/demo.pt-BR.png)

## Executar sem instalar

Requer Python 3, PyGObject/GTK3 e Cinnamon/CJS. Em distribuições derivadas do Debian/Ubuntu (Mint incluído):

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 librsvg2-common
```

`librsvg2-common` é quem rasteriza o SVG do robô na janela. Sem ele a janela continua abrindo, com um ícone do tema no lugar e um aviso no balão do ícone. O cofre do sistema é opcional (`gir1.2-secret-1`, já presente no Mint): sem ele, as chaves vêm do arquivo indicado ou do ambiente. Node serve apenas à verificação de JavaScript, não à execução do applet. Não há pacotes pip/npm.

```bash
cd /caminho/do/repositorio
python3 backend/window.py --demo   # janela com dados fictícios
python3 backend/window.py          # consultas reais de uso/saldo
python3 backend/credentials_window.py  # chaves no cofre e caminhos de arquivo
python3 backend/collector.py collect
python3 backend/collector.py read  # cache, sem consultas de rede
python3 backend/collector.py worker <serviço>  # testa um provedor só
python3 backend/collector.py diag <serviço>    # nomes de campos e faixas, sem valores
```

Demo não lê credenciais nem altera o cache. A coleta real não faz inferência, compras, recargas ou mudanças de plano.

## Spices

**Ainda não está na loja.** O pacote está pronto e passa no validador da própria loja; o pull request é o próximo passo. Enquanto ele não for aceito, instale por este repositório — seção seguinte.

O que espera lá:

- o applet aparece em **Configurações do sistema → Applets**, aba **Download**, como *Uso de IA*, com o ícone do robô e a descrição no idioma da sessão;
- a tradução é serviço do instalador da loja: ele compila `po/pt_BR.po` para `~/.local/share/locale`, que é onde o applet procura quando o `locale/` do próprio projeto não está lá. É isso que coloca a janela de Preferências e a lista de applets no idioma da sessão;
- as chaves continuam vindo da janela **Credenciais…** (cofre do sistema) ou do arquivo que você indicar — nada muda no caminho das credenciais.

O pacote é montado por `sh scripts/spices.sh`, com saída em `build/spice/`, seguindo o que o validador oficial da loja (`validate-spice`) exige: só `files/<uuid>/` é instalado, `icon` é campo proibido no `metadata.json`, `icon.png` é PNG quadrado, e o catálogo vai como fonte — o `.mo` compilado é recusado, porque quem compila é o instalador da loja.

Uma ressalva para quem baixar o ZIP do site da loja e copiar à mão, sem deixar o Cinnamon instalar: nesse caminho nada compila o `.po`, então a janela de Preferências e a lista de applets ficam em inglês. Instalando pelo Cinnamon — ou rodando `python3 install.py` — isso não acontece.

## Instalar para o usuário

```bash
python3 install.py
```

O instalador copia o applet e o backend para `~/.local/share/cinnamon/applets/ai-usage@claudio.drews/`. Preserve o código fonte neste repositório. Uma versão anterior é movida para `~/.local/share/cinnamon/ai-usage-backups/` antes da substituição.

Depois, abra **Configurações do sistema → Applets → Gerenciar**, procure **Uso de IA** e adicione ao painel. O instalador não ativa applets nem reinicia Cinnamon. Após atualização, remova e adicione o applet para carregar a nova versão. Preferências de intervalo e pausa ficam em **Configurar**, no menu de contexto.

Para desinstalar, remova primeiro o applet do painel e apague somente o diretório `ai-usage@claudio.drews` da pasta de applets. Cache e preferências são separados e podem ser preservados.

## Credenciais e configurações

As preferências do Cinnamon não guardam segredos. Cada credencial é procurada nesta ordem:

1. **Cofre do sistema** (Secret Service / gnome-keyring) — é onde a janela **Credenciais…** grava o que a pessoa digita. O cofre vale para qualquer um dos nomes aceitos da credencial e vence o arquivo e o ambiente, de modo que salvar uma chave nova sempre substitui a que a coleta vinha usando. Nada é exibido de volta: a janela só informa de onde o valor viria.
2. **Arquivo indicado por você** em `config.json`, na chave `credentials_path`, no formato `NOME=VALOR` — qualquer caminho (`~/.env`, `~/.config/secrets.env`, o que você usar). O arquivo é lido sem shell: `$(...)` e crases ficam literais. Sem aspas, o valor vale exatamente como está escrito — `KEY=sk-abc#def` guarda `sk-abc#def`, porque `#` só começa comentário depois de espaço. Com aspas, valem as regras do shell, inclusive escape (`KEY="com # dentro"`, `KEY="aspa\"dupla"`). Linha sem `=` ou com aspas não fechada é ignorada — e a janela de credenciais lista quais foram ignoradas e por quê, para "não configurado" nunca aparecer sem causa.
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

Codex usa o login do próprio CLI (`codex login`) em `~/.codex/auth.json`, o Muse Code usa o dele (`muse login`) em `~/.config/muse/auth.json` e o Claude Code usa o do `claude /login` em `~/.claude/.credentials.json`; nenhum dos três aparece na janela de credenciais, porque o arquivo é encontrado pelo caminho padrão do próprio aplicativo. Antigravity é sondado somente no loopback e exige o servidor da IDE em execução; não confunda `ANTIGRAVITY_API_KEY` com o login da IDE. A sondagem é local e vale saber o que ela faz: lê o `--csrf_token` da IDE na linha de comando do processo (`/proc/<pid>/cmdline`), descobre a porta de escuta com `ss` e fala HTTPS com o loopback **sem verificar o certificado** — só `127.0.0.1`, e sem proxy, para o token não vazar por um. Para um servidor da sua própria IDE na sua própria máquina isso é defensável, e é também por isso que este é o conector mais frágil do conjunto: ele depende de uma interface que a IDE não publica e que pode mudar.

### Assinatura do Muse Code (Meta)

A Meta não expõe rota de leitura de quota: nem `GET /muse-code/usage`, nem `used_percent` no arquivo local — o painel `/cost` vive só na memória do cliente. O que funciona é a chamada que o próprio cliente faz ao subir, `POST https://api.meta.ai/muse-code/key`, com o token OAuth do `muse login`. Ela devolvia `subs_usage` com a janela corrente (`used_percent`, `window_duration_mins`, `resets_at` em epoch) e a semanal — veja o estado atual logo abaixo.

**Estado em 26/09/2026 — a rota oscilou e voltou a responder.** A leitura das 16:59:16Z trouxe as duas janelas com percentuais; a tentativa das 17:17:48Z, na mesma rota, devolveu só os metadados da conta e da assinatura (chave, e-mail, tier, situação da assinatura — `is_subs_active` verdadeiro, sem exigência de pagamento) e **nenhum** `subs_usage`; as leituras seguintes trouxeram as duas janelas de novo — a que está no cache é das 21:05:51Z, e o `diag meta` responde `"consulta": "ok"` com as duas janelas reconhecidas. Ou seja: uma tentativa que falhou, não uma rota que parou de funcionar.

No meio disso o conector fez o que devia: marcou a tentativa como falha, preservou a leitura anterior e a mostrou como leitura antiga por falha, em vez de reaproveitá-la como leitura boa. Se voltar a acontecer, vai parecer assim de novo — e o relatório do `diag meta` (abaixo) é o que diz quais campos vieram e quais dos esperados faltaram.

Duas coisas que você deve saber antes de habilitar:

- A chamada **emite credencial**, e não apenas lê. Verificamos em 26/09/2026 que ela é **idempotente**: devolve exatamente a mesma `api_key` que o cliente já guarda, sem tocar no `auth.json`. Nada foi rotacionado e o CLI continuou funcionando.
- Mesmo assim o applet consulta no máximo a cada 15 minutos (`meta.min_interval_seconds`), guarda a última leitura em cache privado e mostra o horário real dela. Entre uma consulta e outra a linha aparece como leitura antiga, com o aviso — é intencional: preferimos um dado velho identificado a martelar uma rota sem documentação de limite. O intervalo conta a última **tentativa**: depois de uma falha (um HTTP 429, por exemplo) a próxima consulta espera o intervalo em vez de repetir a chamada; sem leitura a reaproveitar o serviço fica `unavailable` com "Consulta adiada", e com leitura anterior a linha continua marcada como falha, com a mensagem daquela tentativa — reaproveitar a leitura não apaga o que aconteceu, e só uma resposta nova devolve o serviço a `ok`.

A linha mostra percentual das duas janelas. Não há gasto em dólar para este serviço: a API de modelos não publica preços, e inventar denominador é justamente o que este projeto evita.

### Compatibilidade com versões do Muse Code

Verificado com o Muse Code **1.4.0** (`1.4.0-R4161.1`) e `auth.json` em `schema_version` 1. O conector usa duas coisas:

- O **arquivo de login**, procurado na mesma ordem que o próprio cliente resolve no seu launcher: `token_files.meta` na configuração do applet, depois `$MUSE_AUTH_PATH`, depois `$XDG_CONFIG_HOME/muse/auth.json` e, sem ele, `~/.config/muse/auth.json`. Basta existir um `access_token` em qualquer nível do JSON — quando o arquivo passou a agrupar por `providers.meta`, em 26/09/2026, a leitura continuou funcionando sem alteração.
- A **rota** `POST https://api.meta.ai/muse-code/key`, com `subs_usage.window` e `subs_usage.weekly`.

O conector não executa o binário do Muse Code — nem precisa que ele esteja instalado para ler o arquivo, nem que esteja em execução —, então a versão do CLI instalada não muda o comportamento do applet. O que depende de versão é o formato do arquivo e a rota.

Quando a Meta mudar algo, o esperado é degradar e nunca inventar: arquivo ausente ou sem token → `unconfigured` (a mensagem pede `muse login`); resposta sem `subs_usage` → `unavailable`, com o último valor preservado; falha de rede → `error`, com o valor anterior marcado como leitura antiga. Nenhum desses casos vira 0%, e nenhum deles quebra o painel.

Se a resposta vier sem `subs_usage`, ou com os percentuais em outro nome, relate no GitHub com a saída de:

```bash
python3 backend/collector.py diag meta
```

Esse relatório traz **nomes de campos, tipos e faixa dos números**, mais a lista dos campos que o conector procura — dizendo quais estão ausentes, nulos ou com outro tipo. Nenhum valor, identificador de conta ou caminho da sua máquina. É um caminho que existe de verdade: o `diag` responde por qualquer serviço que as mensagens de falha sugiram, e um teste confere isso.

Se você mantém mais de uma versão do Muse Code com logins em arquivos diferentes, aponte o do seu uso atual em `token_files.meta` (veja a configuração abaixo).

### Assinatura do Claude Code

As janelas da assinatura do Claude Code vêm de `GET https://api.anthropic.com/api/oauth/usage`, com `Authorization: Bearer <token do login>` e `anthropic-beta: oauth-2025-04-20`. É a mesma rota que a CLI usa no comando `/usage`, e a que o applet [`claude-usage@mtwebster`](https://github.com/linuxmint/cinnamon-spices-applets/tree/master/claude-usage@mtwebster) — já aceito na loja — usa com exatamente estes cabeçalhos e este campo de credencial, lendo `utilization` como percentual de 0 a 100. A Anthropic não a publica como API, então ela é tratada como algo que pode mudar.

**Termos de uso.** A Anthropic diz que a autenticação por OAuth é destinada *exclusivamente* aos planos Free, Pro, Max, Team e Enterprise e a sustentar o uso comum do Claude Code e de outros aplicativos nativos dela; que desenvolvedores terceiros não podem rotear pedidos por essas credenciais; e que reserva o direito de aplicar isso [sem aviso prévio](https://code.claude.com/docs/en/legal-and-compliance). Os Termos de Consumo também proíbem o acesso automatizado aos serviços, exceto com chave de API ([§3.7](https://www.anthropic.com/legal/consumer-terms)). Este conector não oferece login, não guarda nem repassa o token — o pedido sai da sua máquina direto para a Anthropic — e não gasta cota. Ainda assim é uma ferramenta de terceiro lendo a sua conta com a credencial que a CLI já mantém, o que não é o uso previsto nesses termos: ativá-lo é decisão de quem ativa, na própria conta e por conta e risco próprios.

O que o conector **não** faz, e por quê:

- **Não faz requisição de inferência.** O rascunho que originou este conector pedia uma resposta em `/v1/messages`, com `max_tokens: 1`, só para ler os cabeçalhos `anthropic-ratelimit-unified-*`. Cada consulta consumiria um pouco da cota que o applet exibe: num applet que atualiza a cada dois minutos, seria o monitor comendo o que monitora. A rota de leitura devolve as duas janelas em JSON, sem custo de cota.
- **Não renova nem grava credencial.** O token do Claude Code vale cerca de uma hora e é a própria CLI que o renova. Com token vencido o serviço fica em `unconfigured` com o aviso "rode `claude` para renovar" — o applet não toca no `refreshToken`.
- **Não adivinha escala.** O percentual é usado como veio, na escala 0–100: nada de multiplicar por 100 quando o valor parece pequeno, o que transformaria 0,4% em 40%.

Na linha aparecem `five_hour` (ou `kind: session`) como **Janela de 5 h**, `seven_day` (ou `weekly_all`) como **Semana** e `weekly_scoped` como **Semana · <modelo>**. Entrada de tipo desconhecido é ignorada — nunca vira zero —, e sem nenhuma janela reconhecida o serviço fica em `unavailable`.

A rota é consultada no máximo a cada 5 minutos (`claude.min_interval_seconds`), com cache privado; entre uma consulta e outra a linha aparece como leitura antiga, com o horário real — e, como no conector da Meta, uma tentativa que falhou também segura o intervalo e mantém o aviso de falha até o serviço responder de novo. O arquivo de login é procurado em `token_files.claude`, depois em `$CLAUDE_CONFIG_DIR/.credentials.json` e por fim em `~/.claude/.credentials.json` — a ordem publicada pela Anthropic para quem roda mais de uma conta. No macOS o login fica no Keychain e não é lido daqui.

Isto serve a quem tem assinatura **Pro, Max, Team ou Enterprise**: quem usa só chave de API não tem essas janelas, e o serviço aparece sem leitura.

**O que ainda não foi verificado** — não há conta Anthropic nesta máquina:

- se a rota aceita `Bearer` com o token do login (a sondagem com token inválido devolveu 401 e o corpo reclamou de `x-api-key`, o que só um token real esclarece);
- se o `.credentials.json` atual mantém `claudeAiOauth.accessToken`, e se o pedido precisa de outro `anthropic-beta`;
- se o percentual vem mesmo em 0–100, premissa da decisão de não rescalar.

Nenhum dos três foi medido daqui: são o que um applet já aceito na loja exercita em produção, e é por isso que este conector os segue. O rótulo **não verificada** continua até que alguém meça em conta real — nenhuma referência externa substitui isso.

Se você tem conta e o serviço não mostrar nada, relate no GitHub com a saída de:

```bash
python3 backend/collector.py diag claude
```

Esse relatório traz só **nomes de campos, tipos, faixa dos números** e quais janelas o conector reconheceu: nenhum valor, nenhum caminho da sua máquina e nenhum pedaço de credencial. É o que um PR precisa para ajustar o parser.

Configuração opcional **sem segredos** em `~/.config/cinnamon-ai-usage/config.json`:

```json
{
  "refresh_seconds": 120,
  "credentials_path": "~/.config/secrets.env",
  "token_files": {"nous": "~/.local/share/meu-login/auth.json"},
  "enabled": {"grok": false},
  "grok": {"team_id": "SEU_TEAM_ID"},
  "meta": {"min_interval_seconds": 900},
  "claude": {"min_interval_seconds": 300}
}
```

`token_files.meta` só é necessário se o login do Muse Code estiver fora do caminho padrão (`~/.config/muse/auth.json`). `token_files.claude` só é necessário se o login do Claude Code estiver fora de `$CLAUDE_CONFIG_DIR` e de `~/.claude/.credentials.json`.

A gravação do arquivo é atômica e em modo 0600. O intervalo selecionado no applet vale para suas consultas. A janela independente usa o TTL do arquivo acima (120 segundos se ausente). O botão Atualizar força a coleta em ambos — e, se já houver uma coleta em andamento, avisa que a atualização foi ignorada em vez de mostrar falha: os valores exibidos seguem sendo os últimos lidos. Desativar um provedor no arquivo o remove das próximas coletas; uma alteração pode aguardar o TTL ou Atualizar.

O cache fica em `~/.cache/cinnamon-ai-usage/` (diretório 0700, snapshot 0600), com gravação atômica e trava para impedir consultas duplicadas. Guarda métricas e histórico, sem tokens nem respostas brutas. Campos privados de identificação usam digest SHA-256 para evitar comparar contas diferentes e são omitidos da saída pública.

## O que significa "recente"

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
sh scripts/spices.sh   # monta o pacote da loja de applets em build/spice/
PYTHON=/usr/bin/python3 VALIDATE_SPICE=/caminho/do/validate-spice sh scripts/spices.sh  # com o validador oficial da loja (exige PIL)
python3 tests/smoke_gtk.py /tmp/ai-usage-demo.png  # requer sessão gráfica
```

Os testes offline cobrem parsers, ausência versus zero, renovação, recência, troca de conta, falha preservando cache e isolamento de segredos. O teste JS simula o ambiente do applet para conferir cliques, timers, coleta e limite de cinco; não substitui a validação no painel real. O teste GTK abre e fecha uma janela de demonstração.

Arquitetura e formato: [docs/contract.md](docs/contract.md). Evidências, fontes e limitações: [docs/validation.md](docs/validation.md).

Para acrescentar um serviço: implemente o conector em `backend/providers.py` conforme as regras do contrato — somente leitura, sem inferência, sem renovar credencial e degradando em vez de inventar zero; registre o id em `SERVICES`; cubra o parser com fixtures em `tests/test_backend.py`; e diga no README o que foi verificado e o que não foi. Um PR é bem mais fácil de aceitar com a saída sem segredos de `python3 backend/collector.py worker <serviço>` (ou `diag <serviço>`, quando existir) no corpo.

Referência de projeto: [omarchy-ai-usage](https://github.com/rodrigo-sntg/omarchy-ai-usage), de Rodrigo Santiago, licença MIT. Esta implementação usa um contrato próprio para preservar janelas e modelos distintos.
