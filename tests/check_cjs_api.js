// Runtime API check only: no stage, panel activation or Cinnamon restart.
imports.gi.versions.Clutter = '0';
imports.gi.versions.Cogl = '0';
const St = imports.gi.St;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const System = imports.system;
const properties = St.Bin.list_properties().map(p => p.name);
for (const name of ['x-fill', 'x-align', 'width', 'height'])
    if (!properties.includes(name)) throw new Error('Missing St.Bin property: '+name);
if (typeof St.Bin.prototype.set_child !== 'function') throw new Error('Missing set_child');
if (typeof St.BoxLayout.prototype.add_actor !== 'function') throw new Error('Missing add_actor');

function fail(msg) {
    printerr('FAIL: '+msg);
    System.exit(1);
}

function expectIOError(fn, code, label, next) {
    try {
        fn();
        fail(label+': expected Gio.IOErrorEnum.'+code+' was not thrown');
    } catch (e) {
        if (!e.matches(Gio.IOErrorEnum, Gio.IOErrorEnum[code]))
            fail(label+': wrong error: '+e);
        next();
    }
}

// Async file API evidence, chained after the subprocess check in the same main loop.
function checkFileApi() {
    const moPath = 'locale/pt_BR/LC_MESSAGES/ai-usage@claudio.drews.mo';
    const moFile = Gio.File.new_for_path(moPath);
    moFile.load_contents_async(null, (f, res) => {
        try {
            const [ok, bytes, etag] = f.load_contents_finish(res);
            if (ok !== true) fail('load_contents_finish: first element is not boolean true');
            if (!(bytes instanceof Uint8Array)) fail('load_contents_finish: contents not Uint8Array');
            if (typeof etag !== 'string') fail('load_contents_finish: etag not string');
            const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
            if (view.getUint32(0, true) !== 0x950412de) fail('wrong .mo magic');
            const count = view.getUint32(8, true);
            if (!(count > 0)) fail('string count not > 0');
            print('CJS: load_contents_async returned [boolean, Uint8Array, string]; .mo magic 0x950412de, '+count+' strings');
        } catch (e) { fail('load_contents .mo: '+e); }
        checkQueryInfo();
    });
}

function checkQueryInfo() {
    const dir = Gio.File.new_for_path('locale');
    dir.query_info_async('standard::type', Gio.FileQueryInfoFlags.NONE,
        GLib.PRIORITY_DEFAULT, null, (f, res) => {
        try {
            const info = f.query_info_finish(res);
            if (info.get_file_type() !== Gio.FileType.DIRECTORY)
                fail('query_info_finish: not a DIRECTORY');
            print('CJS: query_info_async on existing directory returned FileType.DIRECTORY');
        } catch (e) { fail('query_info dir: '+e); }
        checkNotFoundQuery();
    });
}

function checkNotFoundQuery() {
    const missing = Gio.File.new_for_path('locale/caminho-que-nao-existe-xyz');
    missing.query_info_async('standard::type', Gio.FileQueryInfoFlags.NONE,
        GLib.PRIORITY_DEFAULT, null, (f, res) => {
        expectIOError(() => f.query_info_finish(res), 'NOT_FOUND',
            'query_info_finish (missing path)', () => {
            print('CJS: query_info_finish on missing path throws IOErrorEnum.NOT_FOUND (e.matches true)');
            checkNotFoundLoad();
        });
    });
}

function checkNotFoundLoad() {
    const missing = Gio.File.new_for_path('locale/caminho-que-nao-existe-xyz.mo');
    missing.load_contents_async(null, (f, res) => {
        expectIOError(() => f.load_contents_finish(res), 'NOT_FOUND',
            'load_contents_finish (missing path)', () => {
            print('CJS: load_contents_finish on missing path throws IOErrorEnum.NOT_FOUND (e.matches true)');
            checkCancelBefore();
        });
    });
}

function checkCancelBefore() {
    const cancellable = new Gio.Cancellable();
    cancellable.cancel();
    const moFile = Gio.File.new_for_path('locale/pt_BR/LC_MESSAGES/ai-usage@claudio.drews.mo');
    moFile.load_contents_async(cancellable, (f, res) => {
        expectIOError(() => f.load_contents_finish(res), 'CANCELLED',
            'load_contents_finish (cancelled before)', () => {
            print('CJS: cancellable.cancel() before the read makes finish throw IOErrorEnum.CANCELLED');
            checkCancelDuring();
        });
    });
}

function checkCancelDuring() {
    const tmp = GLib.dir_make_tmp('cjs-api-XXXXXX');
    const fifo = GLib.build_filenamev([tmp, 'fifo']);
    const [okm] = GLib.spawn_command_line_sync('mkfifo '+fifo);
    if (!okm) fail('mkfifo failed');
    GLib.spawn_command_line_async("sh -c 'sleep 0.3; printf x > "+fifo+"'");
    const cancellable = new Gio.Cancellable();
    Gio.File.new_for_path(fifo).load_contents_async(cancellable, (f, res) => {
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 800, () => {
            GLib.spawn_command_line_sync('rm -rf '+tmp);
            return GLib.SOURCE_REMOVE;
        });
        expectIOError(() => f.load_contents_finish(res), 'CANCELLED',
            'load_contents_finish (cancelled during)', () => {
            print('CJS: cancellable.cancel() during the read makes finish throw IOErrorEnum.CANCELLED');
            print('CJS: async file API proven: load_contents_async/query_info_async, NOT_FOUND and CANCELLED match Gio.IOErrorEnum');
            loop.quit();
        });
    });
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
        cancellable.cancel();
        return GLib.SOURCE_REMOVE;
    });
}

const loop = GLib.MainLoop.new(null, false);
const proc = Gio.Subprocess.new(['/usr/bin/printf', '{"schema_version":1}'], Gio.SubprocessFlags.STDOUT_PIPE);
proc.communicate_utf8_async(null, null, (p, res) => {
    const [ok, stdout] = p.communicate_utf8_finish(res);
    if (!ok || JSON.parse(stdout).schema_version !== 1) throw new Error('subprocess output');
    print('CJS: St API properties/methods and actual asynchronous Gio subprocess OK');
    checkFileApi();
});
loop.run();
