/* Cinnamon AI Usage — native CJS/St frontend; see docs/contract.md. */
const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Settings = imports.ui.settings;
const Mainloop = imports.mainloop;
const St = imports.gi.St;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Clutter = imports.gi.Clutter;

const WARNING_COLOR = '#e5a50a';
const CRITICAL_COLOR = '#e01b24';

class AIUsageApplet extends Applet.IconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this.setAllowedLayout(Applet.AllowedLayout.BOTH);
        this._stopped = false;
        this._snapshot = null;
        this._error = null;
        this._proc = null;
        this._loop = 0;
        this._click = 0;
        this._watchdog = 0;
        this._killTimer = 0;
        this._instance = instanceId;
        this._uuid = metadata.uuid;
        this._backend = GLib.build_filenamev([metadata.path, 'backend']);
        if (!GLib.file_test(this._backend, GLib.FileTest.IS_DIR))
            this._backend = GLib.build_filenamev([metadata.path, '..', 'backend']);
        this._assets = GLib.build_filenamev([this._backend, '..', 'assets']);
        // Ícone simbólico: herda a cor do tema e recebe a cor de alerta pela cota mais alta.
        this.set_applet_icon_symbolic_path(GLib.build_filenamev([this._assets, 'robot-head-symbolic.svg']));
        this._menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this._menuManager.addMenu(this.menu);
        this._doubleClickMs = 400;
        try {
            const mouse = new Gio.Settings({schema_id: 'org.cinnamon.desktop.peripherals.mouse'});
            this._doubleClickMs = Math.max(100, Math.min(1500, mouse.get_int('double-click')));
        } catch (_) { /* use conventional fallback */ }
        this._ready = false;
        this.settings = new Settings.AppletSettings(this, metadata.uuid, instanceId);
        this.settings.bind('collect-enabled', 'collectEnabled', () => this._configure());
        this.settings.bind('collect-interval', 'collectInterval', () => this._configure());
        this._ready = true;
        this._configure();
    }

    _configure() {
        if (!this._ready || this._stopped) return;
        if (this._loop) Mainloop.source_remove(this._loop);
        this._loop = 0;
        if (this.collectEnabled) {
            this._collect(false);
            this._loop = Mainloop.timeout_add_seconds(Math.max(30, this.collectInterval || 120), () => {
                this._collect(false);
                return true;
            });
        } else if (!this._snapshot) this._collect(false, true);
        this._refreshIcon();
    }

    on_applet_clicked(event) {
        if (this._stopped) return;
        // Keyboard activation opens immediately. Pointer clicks wait for the second click.
        if (event && event.type() === Clutter.EventType.KEY_PRESS) {
            this._toggleMenu();
            return;
        }
        if (this._click) {
            Mainloop.source_remove(this._click);
            this._click = 0;
            this._openWindow();
        } else {
            this._click = Mainloop.timeout_add(this._doubleClickMs, () => {
                this._click = 0;
                this._toggleMenu();
                return false;
            });
        }
    }

    _toggleMenu() {
        if (!this.menu.isOpen) this._renderMenu();
        this.menu.toggle();
    }

    _collect(force, readOnly = false) {
        if (this._stopped || this._proc) return;
        if (!force && !readOnly && !this.collectEnabled) return;
        const argv = ['/usr/bin/python3', GLib.build_filenamev([this._backend, 'collector.py']),
                      readOnly ? 'read' : 'collect'];
        if (!readOnly) argv.push('--ttl', String(Math.max(30, this.collectInterval || 120)));
        if (force) argv.push('--force');
        let proc;
        try {
            proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (_) {
            this._error = 'Não foi possível iniciar o coletor.';
            this._refreshIcon();
            return;
        }
        this._proc = proc;
        this._refreshIcon();
        let timedOut = false;
        this._watchdog = Mainloop.timeout_add_seconds(50, () => {
            this._watchdog = 0;
            timedOut = true;
            proc.send_signal(15);
            this._killTimer = Mainloop.timeout_add_seconds(3, () => {
                this._killTimer = 0;
                if (this._proc === proc) proc.force_exit();
                return false;
            });
            return false;
        });
        proc.communicate_utf8_async(null, null, (p, result) => {
            if (this._proc !== p) return;
            this._proc = null;
            for (const name of ['_watchdog', '_killTimer']) {
                if (this[name]) Mainloop.source_remove(this[name]);
                this[name] = 0;
            }
            if (this._stopped) return;
            try {
                const [ok, stdout] = p.communicate_utf8_finish(result);
                if (!ok || !p.get_successful() || timedOut) throw new Error();
                const snapshot = JSON.parse(stdout);
                if (snapshot.schema_version !== 1 || !Array.isArray(snapshot.services)) throw new Error();
                this._snapshot = snapshot;
                this._error = null;
            } catch (_) {
                this._error = timedOut ? 'Tempo limite da coleta excedido.' : 'Falha ao ler o coletor.';
            }
            this._refreshIcon();
            // Intentionally do not reorder/rebuild while the pointer is inside the menu.
        });
    }

    _quotas(services) {
        return services.filter(s => s.status === 'ok').flatMap(s =>
            (s.metrics || []).filter(m => m.kind === 'quota' && Number.isFinite(m.used_percent))
                .map(m => ({service: s.label || s.id, metric: m})))
            .sort((a, b) => b.metric.used_percent - a.metric.used_percent);
    }

    _paintIcon(highest) {
        if (!this._applet_icon) return;
        const color = highest >= 90 ? CRITICAL_COLOR : highest >= 70 ? WARNING_COLOR : null;
        // Sem cor de alerta o ícone simbólico volta à cor do tema: estilo nulo, nunca
        // string vazia — o parser do St avisa com buffer vazio.
        try {
            this._applet_icon.set_style(color ? `color: ${color};` : null);
        } catch (_) { /* tema sem suporte a cor de ícone */ }
    }

    _refreshIcon() {
        if (this._stopped) return;
        const services = this._snapshot ? this._snapshot.services : [];
        const failed = services.filter(s => ['error', 'stale'].includes(s.status)).length;
        const quotas = this._quotas(services);
        const highest = quotas.length ? quotas[0].metric.used_percent : 0;
        this._paintIcon(highest);
        const lines = ['Uso de IA'];
        for (const service of services.filter(s => s.status !== 'disabled')) {
            const metrics = service.metrics || [];
            const quota = metrics.filter(m => m.kind === 'quota' && Number.isFinite(m.used_percent))
                .sort((a, b) => b.used_percent - a.used_percent)[0];
            const money = metrics.find(m => Number.isFinite(m.value));
            let detail;
            if (quota) detail = `${quota.label}: ${quota.used_percent.toFixed(1).replace('.', ',')}% usado`;
            else if (money) detail = `${money.label}: ${money.value.toFixed(2).replace('.', ',')} ${money.currency || ''}`;
            else detail = {unconfigured: 'Não configurado', unavailable: 'Indisponível',
                          error: 'Falha na leitura'}[service.status] || 'Sem leitura';
            if (metrics.length && service.status !== 'ok') detail += ' (leitura antiga)';
            lines.push(`${service.label || service.id} — ${detail}`);
        }
        if (!services.length) lines.push('Aguardando a primeira leitura…');
        if (highest >= 70) lines.push(`\n${highest >= 90 ? 'Cota crítica' : 'Atenção'}: ${quotas[0].service} · ${quotas[0].metric.label}`);
        const generated = this._snapshot && this._snapshot.generated_at;
        if (generated && Number.isFinite(Date.parse(generated)))
            lines.push(`\nÚltima coleta: ${new Date(generated).toLocaleTimeString('pt-BR')}`);
        if (!this.collectEnabled) lines.push('Coleta automática pausada');
        if (this._proc) lines.push('Atualizando…');
        if (this._error) lines.push(this._error);
        if (failed) lines.push(`${failed} serviço(s) com falha ou leitura antiga`);
        lines.push('\nClique: recentes · clique duplo: todos');
        this.set_applet_tooltip(lines.join('\n'));
    }

    _hasReading(service) {
        return ['ok', 'stale'].includes(service.status) ||
            (Array.isArray(service.metrics) && service.metrics.length > 0);
    }

    _lastUsed(service) {
        return typeof service.last_used_at === 'string' && Number.isFinite(Date.parse(service.last_used_at))
            ? Date.parse(service.last_used_at) : null;
    }

    // Até cinco linhas: primeiro as com uso observado, depois as de leitura mais recente.
    _recent() {
        if (!this._snapshot) return [];
        const services = this._snapshot.services.filter(s => s && s.status !== 'disabled' && this._hasReading(s));
        const used = services.filter(s => this._lastUsed(s) !== null)
            .sort((a, b) => this._lastUsed(b) - this._lastUsed(a));
        const rest = services.filter(s => this._lastUsed(s) === null)
            .sort((a, b) => (Date.parse(b.read_at) || 0) - (Date.parse(a.read_at) || 0));
        return used.concat(rest).slice(0, 5);
    }

    _note(label) {
        const item = new PopupMenu.PopupMenuItem(label, {reactive: false});
        item.label.add_style_class_name('ai-usage-menu-note');
        this.menu.addMenuItem(item);
    }

    _renderMenu() {
        this.menu.removeAll();
        this._note('Cinco mais recentes · uso estimado');
        if (!this.collectEnabled) this._note('Coleta automática pausada');
        if (this._proc) this._note('Atualizando… Reabra para ver a nova leitura.');
        if (this._error) this._note(this._error + ' Últimos valores preservados.');
        const recent = this._recent();
        if (!recent.length) this._note('Sem leitura ainda; use Atualizar ou Ver todos.');
        for (const service of recent) this._serviceRow(service);
        const pending = (this._snapshot ? this._snapshot.services : [])
            .filter(s => ['unconfigured', 'unavailable'].includes(s.status)).length;
        if (pending) this._note(`${pending} serviço(s) sem leitura; veja Credenciais…`);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._action('Ver todos os serviços…', () => this._openWindow());
        this._action('Atualizar', () => this._collect(true));
        this._action('Credenciais…', () => this._openCredentials());
        this._action('Configurações…', () => {
            Gio.Subprocess.new(['xlet-settings', 'applet', this._uuid, '-i', String(this._instance)],
                               Gio.SubprocessFlags.NONE);
        });
    }

    _action(label, callback) {
        const item = new PopupMenu.PopupMenuItem(label);
        item.connect('activate', () => {
            try { callback(); } catch (_) { this._error = 'Não foi possível executar a ação.'; this._refreshIcon(); }
        });
        this.menu.addMenuItem(item);
    }

    _serviceRow(service) {
        const item = new PopupMenu.PopupBaseMenuItem({reactive: false});
        const box = new St.BoxLayout({vertical: true, style_class: 'ai-usage-service', width: 310});
        box.add_actor(new St.Label({text: service.label || service.id}));
        const metrics = service.metrics || [];
        // Most limiting quota first, with its actual label, not a fabricated common window.
        const quotas = metrics.filter(m => m.kind === 'quota' && Number.isFinite(m.used_percent));
        quotas.sort((a,b) => b.used_percent - a.used_percent);
        const m = quotas[0] || metrics[0];
        if (m && m.kind === 'quota' && Number.isFinite(m.used_percent)) {
            const value = Math.max(0, Math.min(100, m.used_percent));
            box.add_actor(new St.Label({text: `${m.label}: ${value.toFixed(1).replace('.', ',')}% usado`,
                                       style_class: 'ai-usage-service-note'}));
            const track = new St.Bin({style_class: 'ai-usage-bar-track', width: 290, height: 5,
                                      x_fill: false, x_align: St.Align.START});
            if (value > 0) {
                const fill = new St.Bin({height: 5, width: 290 * value / 100,
                    style_class: value >= 90 ? 'ai-usage-bar-fill-critical' :
                                 value >= 70 ? 'ai-usage-bar-fill-warning' : 'ai-usage-bar-fill'});
                track.set_child(fill);
                // Themes and display scaling may allocate more than the requested width.
                track.connect('notify::allocation', () => {
                    fill.set_width(track.get_width() * value / 100);
                });
            }
            box.add_actor(track);
        } else if (m && Number.isFinite(m.value)) {
            box.add_actor(new St.Label({text: `${m.label}: ${m.value.toFixed(2).replace('.', ',')} ${m.currency || ''}`,
                                       style_class: 'ai-usage-service-note'}));
        }
        if (service.status !== 'ok') box.add_actor(new St.Label({text: service.status === 'stale' ?
            'Leitura antiga — ver detalhes' : 'Sem leitura atual', style_class: 'ai-usage-service-note'}));
        else if (this._lastUsed(service) === null)
            box.add_actor(new St.Label({text: 'Sem uso observado desde a instalação',
                                       style_class: 'ai-usage-service-note'}));
        item.addActor(box, {expand: true, span: -1});
        this.menu.addMenuItem(item);
    }

    _openWindow() {
        this.menu.close();
        this._runBackend('window.py', 'Não foi possível abrir a janela.');
    }

    _openCredentials() {
        this.menu.close();
        this._runBackend('credentials_window.py', 'Não foi possível abrir as credenciais.');
    }

    _runBackend(script, errorMessage) {
        try {
            Gio.Subprocess.new(['/usr/bin/python3', GLib.build_filenamev([this._backend, script])],
                               Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (_) { this._error = errorMessage; this._refreshIcon(); }
    }

    on_applet_removed_from_panel() {
        this._stopped = true;
        for (const name of ['_click', '_loop', '_watchdog', '_killTimer']) {
            if (this[name]) Mainloop.source_remove(this[name]);
            this[name] = 0;
        }
        if (this._proc) this._proc.send_signal(15);
        this.settings.finalize();
        this.menu.destroy();
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new AIUsageApplet(metadata, orientation, panelHeight, instanceId);
}
