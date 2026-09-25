/* Cinnamon AI Usage — native CJS/St frontend; see docs/contract.md. */
const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Settings = imports.ui.settings;
const Mainloop = imports.mainloop;
const St = imports.gi.St;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Clutter = imports.gi.Clutter;

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

    _refreshIcon() {
        if (this._stopped) return;
        const services = this._snapshot ? this._snapshot.services : [];
        const failed = services.filter(s => ['error', 'stale'].includes(s.status)).length;
        const quotas = services.filter(s => s.status === 'ok').flatMap(s => s.metrics || [])
            .filter(m => m.kind === 'quota' && Number.isFinite(m.used_percent));
        const highest = Math.max(0, ...quotas.map(m => m.used_percent));
        const icon = this._error || failed ? 'dialog-warning' : highest >= 90 ? 'battery-caution' : 'view-statistics';
        this.set_applet_icon_symbolic_name(icon);
        this.actor.set_style(highest >= 90 ? 'color: #e01b24;' : highest >= 70 ? 'color: #e5a50a;' : '');
        const note = this._proc ? 'Atualizando…' : this._error ||
            (failed ? `${failed} serviço(s) com falha ou leitura antiga` : 'Clique: recentes · clique duplo: todos');
        this.set_applet_tooltip(`Uso de IA\n${note}`);
    }

    _recent() {
        if (!this._snapshot) return [];
        return this._snapshot.services.filter(s => s && s.status !== 'disabled' &&
            typeof s.last_used_at === 'string' && Number.isFinite(Date.parse(s.last_used_at)))
            .sort((a, b) => Date.parse(b.last_used_at) - Date.parse(a.last_used_at)).slice(0, 5);
    }

    _note(label) {
        const item = new PopupMenu.PopupMenuItem(label, {reactive: false});
        item.label.add_style_class_name('ai-usage-menu-note');
        this.menu.addMenuItem(item);
    }

    _renderMenu() {
        this.menu.removeAll();
        this._note('Serviços recentes · atividade estimada');
        if (!this.collectEnabled) this._note('Coleta automática pausada');
        if (this._proc) this._note('Atualizando… Reabra para ver a nova leitura.');
        if (this._error) this._note(this._error + ' Últimos valores preservados.');
        const recent = this._recent();
        if (!recent.length) this._note('O histórico aparece após detectar uso.');
        for (const service of recent) this._serviceRow(service);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._action('Ver todos os serviços…', () => this._openWindow());
        this._action('Atualizar', () => this._collect(true));
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
            }
            box.add_actor(track);
        } else if (m && Number.isFinite(m.value)) {
            box.add_actor(new St.Label({text: `${m.label}: ${m.value.toFixed(2).replace('.', ',')} ${m.currency || ''}`,
                                       style_class: 'ai-usage-service-note'}));
        }
        if (service.status !== 'ok') box.add_actor(new St.Label({text: service.status === 'stale' ?
            'Leitura antiga — ver detalhes' : 'Sem leitura atual', style_class: 'ai-usage-service-note'}));
        item.addActor(box, {expand: true, span: -1});
        this.menu.addMenuItem(item);
    }

    _openWindow() {
        this.menu.close();
        try {
            Gio.Subprocess.new(['/usr/bin/python3', GLib.build_filenamev([this._backend, 'window.py'])],
                               Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE);
        } catch (_) { this._error = 'Não foi possível abrir a janela.'; this._refreshIcon(); }
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
