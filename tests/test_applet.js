'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let next = 1;
const timers = new Map(), subprocesses = [];
class Actor {
    constructor(props = {}) { Object.assign(this, props); this.children = []; }
    add_actor(a) { this.children.push(a); }
    add_style_class_name() {}
    set_style() {}
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
const context = {
    imports: {
        ui: {
            applet: { IconApplet: class {
                constructor() { this.actor = new Actor(); }
                setAllowedLayout() {} set_applet_icon_symbolic_name() {} set_applet_tooltip() {}
            }, AllowedLayout: {BOTH: 1}, AppletPopupMenu: Menu },
            popupMenu: {PopupMenuManager: class { addMenu() {} }, PopupMenuItem: Item,
                PopupBaseMenuItem: Item, PopupSeparatorMenuItem: Item},
            settings: {AppletSettings: class {
                constructor(owner) { this.owner = owner; }
                bind(key, prop) { this.owner[prop] = key === 'collect-enabled' ? true : 120; }
                finalize() { this.finalized = true; }
            }},
        },
        mainloop: {timeout_add: timeout, timeout_add_seconds: timeout, source_remove: id => timers.delete(id)},
        gi: {
            St: {BoxLayout: Actor, Label: Actor, Bin: Actor, Align: {START: 0}},
            Clutter: {EventType: {KEY_PRESS: 'key'}},
            GLib: {build_filenamev: a => a.join('/'), file_test: () => true, FileTest: {IS_DIR: 1}},
            Gio: {
                Settings: class { get_int() { return 400; } },
                SubprocessFlags: {NONE: 0, STDOUT_PIPE: 1, STDERR_SILENCE: 2, STDOUT_SILENCE: 4},
                Subprocess: {new(argv, flags) {
                    assert(Array.isArray(argv)); assert.equal(typeof flags, 'number');
                    const p = {argv, flags, communicate_utf8_async(_a,_b,cb) { this.cb = cb; },
                        communicate_utf8_finish() { return [true, this.output, null]; },
                        get_successful() { return true; }, send_signal(n) { this.signal = n; }, force_exit() {this.killed = true;} };
                    subprocesses.push(p); return p;
                }},
            },
        },
    },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('applet/applet.js', 'utf8') + '\nglobalThis.createApplet=main;', context);
const applet = context.createApplet({uuid: 'test', path: '/tmp/applet'}, 0, 32, 1);
assert.equal(subprocesses.length, 1);
const first = subprocesses[0];
first.output = JSON.stringify({schema_version: 1, generated_at: new Date().toISOString(), services: []});
first.cb(first, {});
assert.equal(applet._error, null); // Gio tuple decoded, not treated as a string
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
applet._snapshot.services = Array.from({length: 8}, (_,i) => ({id: String(i), status: 'ok',
    last_used_at: new Date(2026, 0, i+1).toISOString(), metrics: []}));
assert.equal(applet._recent().length, 5);
assert.equal(applet._recent()[0].id, '7');
applet._snapshot.services[7].last_used_at = null;
assert.equal(applet._recent()[0].id, '6');
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
applet.on_applet_clicked();
applet.on_applet_removed_from_panel();
assert.equal(timers.size, 0);
assert(applet.settings.finalized);
console.log('Applet: construction, subprocess tuple, clicks, top five, frozen menu, errors and cleanup OK');
