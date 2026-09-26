'use strict';
// Teste comportamental do applet em CJS real, com dublês só do que é externo.
//
// O gettext não é dublê: o applet lê o .mo do próprio disco (é o que `parseMo` faz), e
// aqui o dublê de GLib entrega os bytes do catálogo versionado. Assim o teste prova o
// que a revisão apontou como faltando: idioma da sessão e preferência da instância
// cruzados, com texto E formatação no mesmo idioma — sem tocar no locale do processo.
//
// O que este arquivo NÃO prova: que o catálogo pt_BR está completo e compilado, nem que
// o .po e o .mo concordam — isso é tests/test_i18n.py.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let next = 1;
const timers = new Map(), subprocesses = [], launcherUses = [];
// Ambiente da sessão: as variáveis que o gettext lê, não a lista do GLib. O applet resolve
// idioma pelas mesmas variáveis e na mesma ordem do backend — é isso que faz painel e janela
// concordarem; `GLib.get_language_names()` dava outro resultado num ambiente misto.
let sessionEnv = {LANG: 'pt_BR.UTF-8'};
class Actor {
    constructor(props = {}) { Object.assign(this, props); this.children = []; }
    add_actor(a) { this.children.push(a); }
    add_style_class_name(name) { (this.classes = this.classes || []).push(name); }
    set_style(style) { this.style = style; }
    set_child(a) { this.children = [a]; }
    connect(name, cb) { this[name] = cb; }
    get_width() { return this.width; }
    set_width(width) { this.width = width; }
}
class Item {
    constructor(label, opts) { this.label = new Actor({text: label}); this.actor = new Actor(); }
    connect(name, cb) { this[name] = cb; }
    addActor(a) { this.actor.add_actor(a); }
}
class Menu {
    constructor() { this.items = []; this.isOpen = false; }
    addMenuItem(i) { this.items.push(i); }
    removeAll() { this.items = []; }
    toggle() { this.isOpen = !this.isOpen; }
    close() { this.isOpen = false; }
    destroy() { this.destroyed = true; }
}
function timeout(delay, cb) {
    assert.equal(typeof delay, 'number'); assert.equal(typeof cb, 'function');
    timers.set(next, cb); return next++;
}
function spawnProcess(argv, flags) {
    assert(Array.isArray(argv)); assert.equal(typeof flags, 'number');
    const p = {argv, flags, communicate_utf8_async(_a, _b, cb) { this.cb = cb; },
        communicate_utf8_finish() { return [true, this.output, null]; },
        get_successful() { return true; }, send_signal(n) { this.signal = n; },
        force_exit() { this.killed = true; }};
    subprocesses.push(p); return p;
}
// Caminho do catálogo: o applet procura junto do xlet, no diretório de dados do usuário e
// no sistema. Só o que existe responde — é assim que a ordem de busca é exercitada — e
// arquivo ausente lança, como o `file_get_contents` do GJS faz de verdade (o dublê que
// devolvia [false, null] escondia isso).
function readFile(path) {
    const bytes = fs.readFileSync(path);
    if (!bytes) throw new Error('vazio');
    return [true, bytes];
}
const context = {
    imports: {
        byteArray: {toString: bytes => Buffer.from(bytes).toString('utf8')},
        ui: {
            applet: { IconApplet: class {
                constructor() { this.actor = new Actor(); this._applet_icon_box = new Actor(); }
                setAllowedLayout() {}
                set_applet_icon_path(path) { this.iconPath = path; }
                set_applet_icon_symbolic_path(path) { this.iconPath = path; this.symbolic = true;
                    this._applet_icon = new Actor(); }
                set_applet_tooltip(text) { this.tooltip = text; }
            }, AllowedLayout: {BOTH: 1}, AppletPopupMenu: Menu },
            popupMenu: {PopupMenuManager: class { addMenu() {} }, PopupMenuItem: Item,
                PopupBaseMenuItem: Item, PopupSeparatorMenuItem: Item},
            settings: {AppletSettings: class {
                constructor(owner) { this.owner = owner; }
                bind(key, prop) {
                    this.owner[prop] = key === 'collect-enabled' ? true
                        : key === 'language' ? 'auto' : 120;
                }
                finalize() { this.finalized = true; }
            }},
        },
        mainloop: {timeout_add: timeout, timeout_add_seconds: timeout, source_remove: id => timers.delete(id)},
        gi: {
            St: {BoxLayout: Actor, Label: Actor, Bin: Actor, Align: {START: 0}},
            Clutter: {EventType: {KEY_PRESS: 'key'}},
            GLib: {build_filenamev: a => a.join('/'), file_test: path => fs.existsSync(path),
                   // As constantes que o applet devolve nos callbacks de timer, com o mesmo
                   // valor do GLib real: o harness trata o retorno pela veracidade.
                   SOURCE_CONTINUE: true, SOURCE_REMOVE: false,
                   file_get_contents: readFile,
                   FileTest: {IS_DIR: 1, IS_REGULAR: 2},
                   getenv: name => (Object.prototype.hasOwnProperty.call(sessionEnv, name)
                       ? sessionEnv[name] : null),
                   get_home_dir: () => '/tmp/home'},
            Gio: {
                Settings: class { get_int() { return 400; } },
                SubprocessFlags: {NONE: 0, STDOUT_PIPE: 1, STDERR_SILENCE: 2, STDOUT_SILENCE: 4},
                Subprocess: {new: spawnProcess},
                SubprocessLauncher: class {
                    constructor(props) { this.flags = props.flags; this.env = {}; }
                    setenv(name, value, overwrite) { this.env[name] = value; }
                    spawnv(argv) { launcherUses.push({argv, env: this.env});
                                   return spawnProcess(argv, this.flags); }
                },
            },
        },
    },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('applet/applet.js', 'utf8') +
    '\nglobalThis.createApplet = main;' +
    '\nglobalThis.text = t => _(t);' +
    '\nglobalThis.recordText = _recordText;' +
    '\nglobalThis.fill = _f;' +
    '\nglobalThis.language = () => _language;' +
    '\nglobalThis.catalogFor = catalogFor;' +
    '\nglobalThis.parseMo = parseMo;' +
    '\nglobalThis.plural = _n;', context);
const UUID = 'ai-usage@claudio.drews';

// Fecha a leitura de arranque que a construção dispara, para o próximo comando falar com a
// coleta de verdade.
function closeStartup() {
    const inicio = subprocesses.at(-1);
    inicio.output = JSON.stringify({schema_version: 1, services: []});
    inicio.cb(inicio, {});
    return inicio;
}

const applet = context.createApplet({uuid: UUID, path: 'applet'}, 0, 32, 1);
assert.equal(subprocesses.length, 1);
closeStartup();
assert.equal(applet._error, null); // Gio tuple decoded, not treated as a string
assert(applet.iconPath.endsWith('/assets/robot-head-symbolic.svg'));
assert(applet.symbolic); // Ícone simbólico herda a cor do tema.
// Sessão em português sem preferência: o texto sai do catálogo pt_BR lido do disco.
assert.equal(applet._language, 'pt_BR');
assert.equal(context.text('Update'), 'Atualizar');
assert.equal(context.text('Critical quota'), 'Cota crítica');
assert.equal(applet._languageOverride, null);
assert.equal(launcherUses.length, 0, 'sem idioma fixado o filho herda o ambiente');

for (const [percent, color] of [[69.9, null], [70, '#e5a50a'], [89.9, '#e5a50a'], [90, '#e01b24']]) {
    const agora = new Date().toISOString();
    applet._snapshot.services = [
        {id: 'codex', label: 'Codex', status: 'ok', read_at: agora, metrics: [
            {kind: 'quota', label: 'Semana', used_percent: percent},
            {kind: 'quota', label: '5 h', used_percent: 10},
        ]},
        {id: 'old', label: 'Antigo', status: 'stale', metrics: [
            {kind: 'quota', label: 'Semana', used_percent: 100},
        ]},
        {id: 'cash', label: 'Saldo', status: 'ok', read_at: agora, metrics: [
            {kind: 'balance', label: 'Disponível', value: 999, currency: 'USD'},
        ]},
    ];
    applet._refreshIcon();
    if (color) assert(applet._applet_icon.style.includes(color));
    else assert.equal(applet._applet_icon.style, null); // Sem alerta: estilo nulo, não vazio.
    assert.equal(applet._applet_icon_box.style, undefined); // Sem borda: o alerta é a cor do robô.
    // Texto vindo do catálogo e número no separador do idioma: os dois no mesmo idioma.
    assert(applet.tooltip.includes(`Codex — Semana: ${percent.toFixed(1).replace('.', ',')}% usado`),
        `tooltip em pt_BR com vírgula decimal: ${applet.tooltip}`);
    assert(applet.tooltip.includes('Disponível: 999,00 USD'));
    assert(applet.tooltip.includes('(leitura antiga)'));
    assert.equal(applet._recent().length, 3); // Menu filled with what has a reading, not only usage.
}
applet._snapshot.services = [];
applet._refreshIcon();
applet._serviceRow({id: 'test', status: 'ok', metrics: [
    {kind: 'quota', label: 'Cota', used_percent: 25},
]});
const track = applet.menu.items.at(-1).actor.children[0].children[2];
track.width = 413; // Theme allocation can exceed the requested 290 pixels.
track['notify::allocation']();
assert.equal(track.children[0].width / track.width, 0.25);
applet.on_applet_clicked();
assert.equal(applet.menu.isOpen, false);
let cb = timers.get(applet._click); timers.delete(applet._click); cb();
assert.equal(applet.menu.isOpen, true);
applet.menu.close();
applet.on_applet_clicked();
applet.on_applet_clicked();
assert.equal(applet._click, 0);
assert.equal(applet.menu.isOpen, false);
assert(subprocesses.at(-1).argv.at(-1).endsWith('window.py'));
applet._renderMenu();
const credentialsItem = applet.menu.items.find(i => i.label && i.label.text === 'Credenciais…');
assert(credentialsItem, 'menu deve oferecer Credenciais…');
credentialsItem.activate();
assert(subprocesses.at(-1).argv.at(-1).endsWith('credentials_window.py'));
applet._snapshot.services = Array.from({length: 8}, (_,i) => ({id: String(i), status: 'ok',
    last_used_at: new Date(2026, 0, i+1).toISOString(), metrics: []}));
assert.equal(applet._recent().length, 5);
assert.equal(applet._recent()[0].id, '7');
applet._snapshot.services[7].last_used_at = null;
assert.equal(applet._recent()[0].id, '6');
// Sem uso observado, o menu continua com cinco linhas, pelas leituras mais recentes.
applet._snapshot.services = Array.from({length: 7}, (_,i) => ({id: String(i), status: 'ok',
    read_at: new Date(2026, 1, i+1).toISOString(),
    metrics: [{kind: 'balance', label: 'Saldo', value: 1, currency: 'USD'}]}));
assert.equal(applet._recent().length, 5);
assert.equal(applet._recent()[0].id, '6');
assert.equal(applet._recent()[4].id, '2');
// Quem não tem leitura não ocupa linha do menu.
applet._snapshot.services.push({id: 'sem', status: 'unconfigured', metrics: []});
assert(!applet._recent().some(s => s.id === 'sem'));
assert.equal(applet._recent().length, 5);
// Uso observado tem prioridade sobre leitura recente.
applet._snapshot.services[0].last_used_at = new Date(2026, 3, 1).toISOString();
assert.equal(applet._recent()[0].id, '0');
applet._renderMenu();
const menuBefore = applet.menu.items;
applet.menu.isOpen = true;
applet._collect(true);
const proc = subprocesses.at(-1);
proc.output = JSON.stringify({schema_version:1,services:[]}); proc.cb(proc, {});
assert.equal(applet.menu.items, menuBefore); // no reorder while open
applet._collect(true);
const bad = subprocesses.at(-1), saved = applet._snapshot;
bad.output = 'invalid'; bad.cb(bad,{});
assert.equal(applet._snapshot, saved);
assert(applet._error);
// Aviso público do coletor (coleta pulada por já haver outra em andamento) aparece no menu e no balão.
const notice = 'Atualização ignorada: já há uma coleta em andamento; os valores são os últimos lidos.';
applet._snapshot = {schema_version: 1, generated_at: new Date().toISOString(), services: [],
    notice};
applet._renderMenu();
assert(applet.menu.items.some(i => i.label && i.label.text === notice));
applet._refreshIcon();
assert(applet.tooltip.includes('coleta em andamento'));
applet._snapshot.notice = null;
applet._renderMenu();
assert(!applet.menu.items.some(i => i.label && i.label.text === 'null'));
// Indicador de erro separado de cota: nomeia quem falhou, com estilo próprio, sem mexer na cota.
applet._snapshot = {schema_version: 1, generated_at: new Date().toISOString(), services: [
    {id: 'codex', label: 'Codex', status: 'error', message: 'HTTP 500', source: 'teste',
     read_at: null, last_used_at: null, recency_basis: 'unknown', metrics: []},
    {id: 'grok', label: 'Grok / xAI', status: 'stale', message: '', source: 'teste',
     read_at: null, last_used_at: null, recency_basis: 'unknown',
     metrics: [{id: 'balance:USD', label: 'Saldo pré-pago da API', kind: 'balance', value: 7.02,
                currency: 'USD', used_percent: null, window_seconds: null, reset_at: null}]}]};
applet._renderMenu();
const linhaErro = applet.menu.items.find(i => i.label && i.label.text === 'Falha na leitura: Codex');
assert(linhaErro, 'o menu precisa nomear o serviço que falhou');
assert(linhaErro.label.classes.includes('ai-usage-menu-error'));
assert(applet.menu.items.some(i => i.label && i.label.text === 'Leitura antiga: Grok / xAI'));
applet._refreshIcon();
assert(applet.tooltip.includes('Falha na leitura: Codex'));
assert(applet.tooltip.includes('Leitura antiga: Grok / xAI'));
assert(!/service\(s\)/.test(applet.tooltip), 'o balão não deve agregar falha sem nomear');
// Leitura antiga com status ok não colore o robô: o applet confere a idade, não só o status.
const vencida = {id: 'meta', label: 'Meta', status: 'ok',
    read_at: new Date(Date.now() - 3600000).toISOString(),
    metrics: [{kind: 'quota', label: 'Janela', used_percent: 99}]};
assert.equal(applet._aged(vencida), true);
assert.equal(applet._aged({status: 'ok', read_at: new Date(Date.now() - 60000).toISOString()}), false);
applet._snapshot = {schema_version: 1, generated_at: new Date().toISOString(), services: [vencida]};
applet._refreshIcon();
assert.equal(applet._applet_icon.style, null); // uma hora de idade não mantém o ícone vermelho
assert(applet.tooltip.includes('(leitura antiga)'));
assert(applet.tooltip.includes('Leitura antiga: Meta'));
applet._renderMenu();
assert(applet.menu.items.some(i => i.label && i.label.text === 'Leitura antiga: Meta'));
// Pausar a coleta não congela o estado: o laço de idade continua reavaliando o que está na tela.
applet.collectEnabled = false;
applet._configure();
assert(applet._ageLoop, 'pausar precisa manter a reavaliação da idade');
assert(!applet._loop, 'com a coleta pausada não há laço de coleta');
applet._snapshot = {schema_version: 1, generated_at: new Date().toISOString(),
    services: [{id: 'meta', label: 'Meta', status: 'ok', read_at: new Date().toISOString(),
                metrics: [{kind: 'quota', label: 'Janela', used_percent: 95}]}]};
applet._refreshIcon();
assert(applet._applet_icon.style.includes('#e01b24')); // leitura de agora: alerta continua
const reavaliar = timers.get(applet._ageLoop);
const consultas = subprocesses.length;
applet._snapshot.services[0].read_at = new Date(Date.now() - 3600000).toISOString();
reavaliar(); // é isto que o laço de 60 s faz, sem consultar serviço nenhum
assert.equal(applet._applet_icon.style, null);
assert(applet.tooltip.includes('Leitura antiga: Meta'));
assert.equal(subprocesses.length, consultas); // reavaliar idade não dispara consulta
applet.collectEnabled = true;

// Idioma da sessão e preferência da instância são eixos diferentes, e nenhum dos dois mexe no
// locale do processo: o catálogo é lido por instância. Os quatro cruzamentos, com texto e
// formatação no mesmo idioma — a revisão reproduziu justamente o caso 'en' com sessão pt_BR.
const extras = [];
function instance(preference, env) {
    sessionEnv = env;
    const created = context.createApplet({uuid: UUID, path: 'applet'}, 0, 32, next);
    created.language = preference;
    created.collectEnabled = false;
    created._configure();
    closeStartup();
    created._snapshot = {schema_version: 1, generated_at: new Date().toISOString(), services: [
        {id: 'cash', label: 'Saldo', status: 'ok', read_at: new Date().toISOString(),
         metrics: [{kind: 'balance', label: 'Disponível', value: 999, currency: 'USD'}]}]};
    created._refreshIcon();
    extras.push(created);
    return created;
}

const ptSession = {LANG: 'pt_BR.UTF-8'};
const enSession = {LANG: 'en_US.UTF-8'};

const inglesSobSessaoPt = instance('en', ptSession);
assert.equal(inglesSobSessaoPt._language, 'en');
assert.equal(context.text('Update'), 'Update', 'preferência em inglês sobre sessão pt_BR');
assert(inglesSobSessaoPt.tooltip.includes('Disponível: USD 999.00'),
    'formatação em inglês junto do texto em inglês: ' + inglesSobSessaoPt.tooltip);
assert(inglesSobSessaoPt.tooltip.includes('Last collection: '));

const portuguesSobSessaoEn = instance('pt_BR', enSession);
assert.equal(portuguesSobSessaoEn._language, 'pt_BR');
assert.equal(context.text('Update'), 'Atualizar', 'preferência em pt_BR sobre sessão en_US');
assert(portuguesSobSessaoEn.tooltip.includes('Disponível: 999,00 USD'),
    'formatação em pt_BR junto do texto em pt_BR: ' + portuguesSobSessaoEn.tooltip);
assert(portuguesSobSessaoEn.tooltip.includes('Última coleta: '));

const automaticoSobSessaoEn = instance('auto', enSession);
assert.equal(automaticoSobSessaoEn._language, 'en');
assert.equal(context.text('Update'), 'Update');

const semCatalogo = instance('fr_FR', ptSession);
assert.equal(semCatalogo._language, 'en', 'preferência sem catálogo cai no inglês, não na sessão');
assert.equal(context.text('Update'), 'Update');

// Ambiente misto, a divergência que o revisor reproduziu: `LANGUAGE=fr_FR` com LC_ALL e LANG
// em pt_BR. O gettext é claro — LANGUAGE manda sozinha —, então a resposta é inglês nos dois
// runtimes, e o painel concorda com a janela e com a tela de preferências do shell.
const misto = instance('auto', {LANGUAGE: 'fr_FR', LC_ALL: 'pt_BR.UTF-8', LANG: 'pt_BR.UTF-8'});
assert.equal(misto._language, 'en', 'LANGUAGE sem catálogo não volta para o LC_ALL');
assert.equal(context.text('Update'), 'Update');

// Lista em LANGUAGE, como o gettext aceita: o primeiro idioma com catálogo vence.
const lista = instance('auto', {LANGUAGE: 'fr_FR:pt_BR', LANG: 'en_US.UTF-8'});
assert.equal(lista._language, 'pt_BR', 'lista em LANGUAGE é percorrida na ordem');
assert.equal(context.text('Update'), 'Atualizar');

// Sem LANGUAGE, vale a primeira variável definida entre LC_ALL, LC_MESSAGES e LANG.
assert.equal(instance('auto', {LC_ALL: 'pt_BR.UTF-8', LANG: 'en_US.UTF-8'})._language, 'pt_BR');
assert.equal(instance('auto', {LC_MESSAGES: 'pt_BR.UTF-8', LANG: 'en_US.UTF-8'})._language, 'pt_BR');
assert.equal(instance('auto', {LANGUAGE: '  ', LANG: 'pt_BR.UTF-8'})._language, 'pt_BR',
    'LANGUAGE vazia não esconde o resto do ambiente');
assert.equal(instance('auto', {})._language, 'en', 'ambiente sem variável nenhuma é inglês');
assert.equal(instance('auto', {LANG: 'C'})._language, 'en', 'locale C não tem tradução');
// Desvio deliberado, documentado em docs/i18n.md: LANGUAGE vale mesmo com LC_ALL=C, porque é
// por LANGUAGE que o applet fixa o idioma dos filhos.
assert.equal(instance('auto', {LANGUAGE: 'pt_BR', LC_ALL: 'C', LANG: 'C'})._language, 'pt_BR',
    'LANGUAGE vence LC_ALL=C no nosso contrato');
assert.equal(instance('auto', {LANG: 'pt_BR.UTF-8@euro'})._language, 'pt_BR',
    'modificador @euro não esconde o idioma');

// O idioma fixado vai para os filhos (coleta e janelas): o filho herda LANGUAGE.
const fixado = instance('en', ptSession);
fixado.collectEnabled = false;
fixado._collect(true);
assert.equal(launcherUses.at(-1).env.LANGUAGE, 'en');
closeStartup();

// Texto do cache: o identificador manda. Leitura gravada em português aparece em inglês sem
// recolher nada, e o rótulo sem identificador sai como está (é dado da coleta, não texto nosso).
// O idioma em vigor é o da instância (a última que aplicou a preferência), então o teste troca
// de instância em vez de mexer no estado à mão.
instance('pt_BR', ptSession);
const salvoEmPortugues = {
    message_id: 'Last reading available; refresh pending.',
    message: 'Última leitura disponível; atualização pendente.',
    message_args: {}};
assert.equal(context.recordText(salvoEmPortugues, 'message_id', 'message_args', 'message'),
             'Última leitura disponível; atualização pendente.');
assert.equal(context.recordText({label_id: 'Update', label: 'Atualizar'},
                                'label_id', 'label_args', 'label'), 'Atualizar');
// Identificador que este catálogo não conhece cai no texto gravado (snapshot antigo, frase de
// conector novo): melhor o texto da coleta do que a chave crua na tela.
assert.equal(context.recordText({label_id: 'Não está no catálogo', label: 'Semana'},
                                'label_id', 'label_args', 'label'), 'Semana');
instance('en', enSession);
assert.equal(context.recordText(salvoEmPortugues, 'message_id', 'message_args', 'message'),
             'Last reading available; refresh pending.');
// Rótulo de métrica: com identificador sai no idioma em vigor; sem ele (snapshot antigo ou
// rótulo que é nome próprio) sai o texto gravado, e nunca vazio.
assert.equal(context.recordText({label_id: 'Update', label: 'Atualizar'},
                                'label_id', 'label_args', 'label'), 'Update');
assert.equal(context.recordText({label: 'Semana · Opus'}, 'label_id', 'label_args', 'label'),
             'Semana · Opus');
assert.equal(context.recordText({}, 'label_id', 'label_args', 'label'), '');
// Arg de **texto** entra como está: o que uma coleta antiga gravou formatado não é
// reinterpretado. Por isso número formatado não vai para msgid de rótulo, e por isso a forma
// nova de gravar não invalida o snapshot que já está no disco.
assert.equal(context.recordText({label_id: '{label}: {percent} used',
                                 label_args: {label: 'Janela', percent: '42,0%'},
                                 label: 'Janela: 42,0% usado'},
                                'label_id', 'label_args', 'label'), 'Janela: 42,0% used');
// Arg de **número** é escrito aqui, com o separador do idioma em vigor: é a mesma regra de
// `i18n.arg_text` no backend. Gravado como texto, `1,5` atravessava a troca de idioma e a tela
// em inglês dizia "Window of 1,5 h".
instance('pt_BR', ptSession);
const janelaFracionaria = {label_id: 'Window of {hours} h', label_args: {hours: 1.5},
                           label: 'Janela de 1,5 h'};
assert.equal(context.recordText(janelaFracionaria, 'label_id', 'label_args', 'label'),
             'Janela de 1,5 h');
instance('en', enSession);
assert.equal(context.recordText(janelaFracionaria, 'label_id', 'label_args', 'label'),
             'Window of 1.5 h');
assert.equal(context.fill('{hours} h', {hours: 5}), '5 h');         // inteiro sem casa decimal
assert.equal(context.fill('{hours} h', {hours: 1.5}), '1.5 h');
assert.equal(context.fill('{hours} h', {hours: '1,5'}), '1,5 h');   // texto passa como veio
const balde = {label_id: '{name} · {hours} h window', label_args: {name: 'Outro balde',
                                                                  hours: 168},
               label: 'antigo'};
assert.equal(context.recordText(balde, 'label_id', 'label_args', 'label'),
             'Outro balde · 168 h window');
instance('pt_BR', ptSession);
assert.equal(context.fill('{hours} h', {hours: 1.5}), '1,5 h');
assert.equal(context.recordText(balde, 'label_id', 'label_args', 'label'),
             'Outro balde · janela de 168 h');
// Trecho da nota: identificador + valores crus por trecho, compostos no idioma em vigor, com o
// espaço que separa o bloco da frase. A nota era montada em português **na coleta** e aparecia
// assim numa tela em inglês ("Plano: Pro … 125,5% de uso").
const notaDaMeta = {
    message_id: 'Application subscription; not API usage billing.{details}',
    message: 'nota da coleta',
    message_args: {details: [
        {id: 'Plan: {plan}.', args: {plan: 'Pro'}, text: 'Plano: Pro.'},
        {id: 'Meta reported {percent}% usage; the applet bar stops at 100%.',
         args: {percent: 125.5}, text: 'A Meta relatou 125,5% de uso; a barra do applet vai até 100%.'}]}};
assert.equal(context.recordText(notaDaMeta, 'message_id', 'message_args', 'message'),
             'Assinatura do aplicativo; não é a cobrança por uso da API. Plano: Pro. '
             + 'A Meta relatou 125,5% de uso; a barra do applet vai até 100%.');
instance('en', enSession);
assert.equal(context.recordText(notaDaMeta, 'message_id', 'message_args', 'message'),
             'Application subscription; not API usage billing. Plan: Pro. '
             + 'Meta reported 125.5% usage; the applet bar stops at 100%.');
// Nota sem trecho opcional: nenhum espaço sobra no fim da frase.
assert.equal(context.recordText(
    {message_id: 'Application subscription; not API usage billing.{details}',
     message_args: {details: []}, message: 'nota'},
    'message_id', 'message_args', 'message'), 'Application subscription; not API usage billing.');
// Trecho sem identificador no catálogo cai no texto gravado; sem texto e sem catálogo, no
// próprio msgid — o trecho nunca desaparece da frase em silêncio.
assert.equal(context.fill('nota.{details}', {details: [
    {id: 'Frase de conector novo.', args: {}, text: 'Frase gravada.'}]}), 'nota. Frase de conector novo.');
// O aviso da coleta pulada também é texto do cache: com identificador, o aviso de uma coleta
// feita em português sai em inglês no painel em inglês, sem recolher nada (a janela já lia
// `notice_id`; o painel lia o texto direto).
const noticias = {notice_id: 'Refresh skipped: a collection is already running;'
                              + ' the values are the last reading.',
                  notice_args: {},
                  notice: 'Atualização ignorada: já há uma coleta em andamento;'
                          + ' os valores são os últimos lidos.'};
instance('pt_BR', ptSession);
assert.equal(context.recordText(noticias, 'notice_id', 'notice_args', 'notice'),
             'Atualização ignorada: já há uma coleta em andamento; os valores são os últimos lidos.');
instance('en', enSession);
assert.equal(context.recordText(noticias, 'notice_id', 'notice_args', 'notice'),
             'Refresh skipped: a collection is already running; the values are the last reading.');
// Tradução idêntica ao original é entrada presente, não entrada ausente: `{hours} h` está no
// catálogo com o mesmo texto, e comparar tradução com msgid classificaria essa entrada como
// falta — o rótulo `99 h` da coleta antiga venceria o identificador com `hours=3`. É o caso
// que o revisor reproduziu, e o que decide é a presença da entrada, não a igualdade do texto.
assert.equal(context.recordText({label_id: '{hours} h', label_args: {hours: 3}, label: '99 h'},
                                'label_id', 'label_args', 'label'), '3 h');
assert.equal(context.recordText({label_id: '{hours} h', label_args: {hours: 1}, label: '99 h'},
                                'label_id', 'label_args', 'label'), '1 h');
// Entrada com plural não vale como identificador — falta o número para escolher a forma —, e
// o painel decide igual ao backend: em português mostra o texto da coleta, não a primeira
// forma do catálogo ("{days} dia" diria 1 dia no lugar de 3). Em inglês o identificador é a
// própria frase, e é o que sai.
instance('pt_BR', ptSession);
assert.equal(context.recordText({label_id: '{days} day', label_args: {}, label: '3 dias'},
                                'label_id', 'label_args', 'label'), '3 dias');
instance('en', enSession);
assert.equal(context.recordText({label_id: '{days} day', label_args: {}, label: '3 dias'},
                                'label_id', 'label_args', 'label'), '{days} day');
// Catálogo é lido uma vez por idioma e o de outro idioma não vaza para este.
const ptCatalog = context.catalogFor('pt_BR');
assert(ptCatalog !== null);
assert.equal(context.catalogFor('fr_FR'), null);
// Plural: a entrada é "singular\0plural" no .mo, e o ByteArray.toString corta no NUL — o
// parser separa nos bytes antes de decodificar, e é isto que trava esse caminho.
assert.equal(ptCatalog.plurals['{days} day'].join(' | '), '{days} dia | {days} dias');
assert.equal(ptCatalog.singles['{days} day'], undefined);
assert.equal(ptCatalog.singles['Update'], 'Atualizar');
// A forma plural segue a expressão do cabeçalho do catálogo (`plural=(n > 1)` em pt_BR), não
// um `n === 1` genérico: em português zero é singular, em inglês é plural.
instance('pt_BR', ptSession);
assert.equal(context.plural('{days} day', '{days} days', 0), '{days} dia');
assert.equal(context.plural('{days} day', '{days} days', 1), '{days} dia');
assert.equal(context.plural('{days} day', '{days} days', 2), '{days} dias');
instance('en', enSession);
assert.equal(context.plural('{days} day', '{days} days', 0), '{days} days');
assert.equal(context.plural('{days} day', '{days} days', 1), '{days} day');
assert.equal(context.plural('{days} day', '{days} days', 2), '{days} days');
// Arquivo ausente lança no GJS de verdade: sem catálogo o idioma não vale, e o applet não
// pode morrer por causa disso.
assert.equal(context.parseMo('/tmp/nao-existe.mo'), null);
assert.equal(context.parseMo('package.json'), null); // existe, mas não é catálogo

// Prosa presa no código do painel: literal que uma pessoa lê tem de passar por `_()`. A
// conta ignora (a) o que é argumento dos helpers de tradução, (b) pedaço de concatenação,
// (c) token técnico — nome de propriedade, classe de estilo, caminho de ícone, código de
// status — e (d) molde só de marcadores. Sobra texto que ficaria no idioma do código, e a
// dívida declarada é zero: o mesmo crivo que o Python usa em tests/test_i18n.py, aqui sem
// depender de acento (o detector antigo não via "Saldo" nem "Refresh").
function jsLiterals(source) {
    const out = [];
    let i = 0, quote = null, start = -1;
    while (i < source.length) {
        const ch = source[i];
        if (quote) {
            if (ch === '\\') { i += 2; continue; }
            if (ch === quote) { out.push({text: source.slice(start + 1, i), start, end: i + 1}); quote = null; }
            i++; continue;
        }
        if (ch === "'" || ch === '"' || ch === '`') { quote = ch; start = i; i++; continue; }
        if (ch === '/' && source[i + 1] === '/') { i = source.indexOf('\n', i); if (i < 0) break; continue; }
        if (ch === '/' && source[i + 1] === '*') { i = source.indexOf('*/', i); if (i < 0) break; i += 2; continue; }
        i++;
    }
    return out;
}

function looksLikeProse(text) {
    if (text.length < 4 || /[\n\t]/.test(text)) return false;
    if (!/[A-Za-zÀ-ÿ]/.test(text)) return false;
    if (/^[\w.\-/:@\[\]{}<>*+=#$%~^|]+$/.test(text.trim())) return false;
    const semMarcadores = text.replace(/\{[^}]*\}/g, '').replace(/\$\{[^}]*\}/g, '');
    if (!/[A-Za-zÀ-ÿ]{2,}/.test(semMarcadores)) return false;
    // Declaração de estilo ('color: ${color};') tem dois-pontos e ponto-e-vírgula, não frase.
    if (/^[a-z-]+\s*:[^;]+;$/.test(semMarcadores.trim())) return false;
    return text.trim().split(/\s+/).filter(w => /[A-Za-zÀ-ÿ]{2,}/.test(w)).length >= 2;
}

const fonteApplet = fs.readFileSync('applet/applet.js', 'utf8');
const presos = [];
for (const {text, start, end} of jsLiterals(fonteApplet)) {
    const antes = fonteApplet.slice(Math.max(0, start - 24), start).replace(/\s+$/, '');
    if (/(?:^|[^\w$])_(?:t|n|f)?\($|(?:^|[^\w$])N_\($/.test(antes)) continue;  // argumento de helper
    const depois = fonteApplet.slice(end).replace(/^\s+/, '');
    if (/[+]$/.test(antes) || depois.startsWith('+')) continue;                  // pedaço de concatenação
    if (looksLikeProse(text)) presos.push(text);
}
assert.deepEqual(presos, [], 'prosa do painel fora do catálogo: ' + JSON.stringify(presos));
// Testemunhas do crivo: sem elas o teste poderia estar vendo nada e passar por engano.
assert(looksLikeProse('Saldo total disponivel'));
assert(looksLikeProse('Refresh skipped'));
assert(!looksLikeProse('balance'));
assert(!looksLikeProse('{value} {currency}'));
assert(!looksLikeProse('icon-symbolic'));
assert(!looksLikeProse('Gtk.Settings'));
console.log('Painel: nenhuma prosa fora do catálogo (' + jsLiterals(fonteApplet).length + ' literais conferidos)');

// As instâncias do cruzamento de idioma também são removidas: cada uma tem o laço de idade.
for (const extra of extras) extra.on_applet_removed_from_panel();
applet.on_applet_clicked();
applet.on_applet_removed_from_panel();
assert.equal(timers.size, 0);
assert(applet.settings.finalized);
console.log('Applet: construction, subprocess tuple, clicks, top five, frozen menu, errors, '
    + 'language crossing, cached text (raw numbers, note parts, notice), cleanup OK');
