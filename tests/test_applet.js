'use strict';
// Teste comportamental do applet em CJS real, com dublês só do que é externo.
//
// O que este arquivo NÃO prova: que o catálogo pt_BR está completo e compilado —
// isso é tests/test_i18n.py, que lê o .po e o .mo. Aqui o dublê do gettext devolve
// o próprio msgid, de propósito: a asserção de texto é a do idioma base (inglês) e
// o que se mede é comportamento. A formatação, essa sim, é conferida nos dois
// idiomas, porque depende do idioma resolvido e não do texto traduzido.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let next = 1;
const timers = new Map(), subprocesses = [], gettextCalls = [], launcherUses = [];
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
const context = {
    imports: {
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
        // O shell do Cinnamon liga o domínio do xlet a ~/.local/share/locale; aqui o
        // dublê devolve o msgid e registra o domínio pedido.
        gettext: {dgettext(domain, text) { gettextCalls.push({domain, text}); return text; },
                  bindtextdomain() {}},
        gi: {
            St: {BoxLayout: Actor, Label: Actor, Bin: Actor, Align: {START: 0}},
            Clutter: {EventType: {KEY_PRESS: 'key'}},
            GLib: {build_filenamev: a => a.join('/'), file_test: () => true,
                   FileTest: {IS_DIR: 1, IS_REGULAR: 2},
                   getenv: () => null, get_home_dir: () => '/tmp/home',
                   // Sessão em português: é o idioma que o 'auto' deve resolver sozinho.
                   get_language_names: () => ['pt_BR.UTF-8', 'pt_BR', 'pt', 'C']},
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
vm.runInContext(fs.readFileSync('applet/applet.js', 'utf8') + '\nglobalThis.createApplet=main;', context);
const UUID = 'ai-usage@claudio.drews';
const applet = context.createApplet({uuid: UUID, path: '/tmp/applet'}, 0, 32, 1);
assert.equal(subprocesses.length, 1);
const first = subprocesses[0];
first.output = JSON.stringify({schema_version: 1, generated_at: new Date().toISOString(), services: []});
first.cb(first, {});
assert.equal(applet._error, null); // Gio tuple decoded, not treated as a string
assert(applet.iconPath.endsWith('/assets/robot-head-symbolic.svg'));
assert(applet.symbolic); // Ícone simbólico herda a cor do tema.
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
    // Texto no idioma base e número no idioma resolvido (pt_BR): as duas coisas são independentes.
    assert(applet.tooltip.includes(`Codex — Semana: ${percent.toFixed(1).replace('.', ',')}% used`));
    assert(applet.tooltip.includes('Disponível: 999,00 USD'));
    assert(applet.tooltip.includes('(stale reading)'));
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
const credentialsItem = applet.menu.items.find(i => i.label && i.label.text === 'Credentials…');
assert(credentialsItem, 'menu deve oferecer Credentials…');
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
applet._snapshot = {schema_version: 1, generated_at: new Date().toISOString(), services: [],
    notice: 'Atualização ignorada: já há uma coleta em andamento; os valores são os últimos lidos.'};
applet._renderMenu();
assert(applet.menu.items.some(i => i.label && i.label.text === applet._snapshot.notice));
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
const linhaErro = applet.menu.items.find(i => i.label && i.label.text === 'Reading failed: Codex');
assert(linhaErro, 'o menu precisa nomear o serviço que falhou');
assert(linhaErro.label.classes.includes('ai-usage-menu-error'));
assert(applet.menu.items.some(i => i.label && i.label.text === 'Stale reading: Grok / xAI'));
applet._refreshIcon();
assert(applet.tooltip.includes('Reading failed: Codex'));
assert(applet.tooltip.includes('Stale reading: Grok / xAI'));
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
assert(applet.tooltip.includes('(stale reading)'));
assert(applet.tooltip.includes('Stale reading: Meta'));
applet._renderMenu();
assert(applet.menu.items.some(i => i.label && i.label.text === 'Stale reading: Meta'));
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
assert(applet.tooltip.includes('Stale reading: Meta'));
assert.equal(subprocesses.length, consultas); // reavaliar idade não dispara consulta
applet.collectEnabled = true;

// Idioma 'auto': resolve sozinho pelo idioma da sessão, e todo pedido sai no domínio do xlet
// — é o domínio que o shell ligou a ~/.local/share/locale (appletManager.js).
assert.equal(applet._language, 'pt_BR');
assert.equal(applet._languageOverride, null);
assert(gettextCalls.length > 0);
assert(gettextCalls.every(call => call.domain === UUID), 'o domínio gettext é o uuid do xlet');
assert(gettextCalls.some(call => call.text === 'Update'));
assert.equal(launcherUses.length, 0, 'sem idioma fixado o filho herda o ambiente');

// Idioma fixado na configuração: o filho recebe LANGUAGE (coleta e janelas no mesmo idioma do
// painel) e a formatação passa a ser a do inglês.
const english = context.createApplet({uuid: UUID, path: '/tmp/applet'}, 0, 32, 2);
english.language = 'en';
english.collectEnabled = false;
english._configure();
assert.equal(english._language, 'en');
assert.equal(english._languageOverride, 'en');
// Fecha a leitura de arranque para o próximo comando falar com a coleta de verdade.
const inicio = subprocesses.at(-1);
inicio.output = JSON.stringify({schema_version: 1, services: []});
inicio.cb(inicio, {});
english._collect(true);
assert.equal(launcherUses.at(-1).env.LANGUAGE, 'en');
english._snapshot = {schema_version: 1, generated_at: new Date().toISOString(), services: [
    {id: 'cash', label: 'Balance', status: 'ok', read_at: new Date().toISOString(),
     metrics: [{kind: 'balance', label: 'Available', value: 999, currency: 'USD'}]}]};
english._refreshIcon();
assert(english.tooltip.includes('Available: USD 999.00'));
assert(english.tooltip.includes('Last collection: '));
assert(/\d{1,2}:\d{2} (AM|PM)/.test(english.tooltip));
english.on_applet_removed_from_panel();

applet.on_applet_clicked();
applet.on_applet_removed_from_panel();
assert.equal(timers.size, 0);
assert(applet.settings.finalized);
console.log('Applet: construction, subprocess tuple, clicks, top five, frozen menu, errors, language and cleanup OK');
