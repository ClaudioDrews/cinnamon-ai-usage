// Mede, no cjs real, quanto uma leitura síncrona segura o laço principal
// versus a mesma leitura com Gio.File.load_contents_async. Sem painel, sem
// stage; temporários só em $TMPDIR e removidos no fim, inclusive em erro.
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const System = imports.system;

const TIMER_MS = 20;
const WRITER_DELAY = 0.3; // s

const tmp = GLib.dir_make_tmp('cjs-bloqueio-XXXXXX');
function cleanup() { GLib.spawn_command_line_sync('rm -rf ' + tmp); }

function fail(msg) { cleanup(); printerr('FAIL: ' + msg); System.exit(1); }

function makeFifo(name) {
    const path = GLib.build_filenamev([tmp, name]);
    const [ok] = GLib.spawn_command_line_sync('mkfifo ' + path);
    if (!ok) fail('mkfifo ' + path);
    return path;
}
function delayedWriter(fifo) {
    GLib.spawn_command_line_async("sh -c 'sleep " + WRITER_DELAY + "; printf x > " + fifo + "'");
}
function ms(us) { return (us / 1000).toFixed(1); }

const loop = GLib.MainLoop.new(null, false);
const results = {};

// (a) leitura síncrona: o timer de 20 ms só dispara depois do FIFO abrir (~300 ms).
function phaseSync() {
    const fifo = makeFifo('fifo-sync');
    delayedWriter(fifo);
    const t0 = GLib.get_monotonic_time();
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, TIMER_MS, () => {
        results.syncDelay = GLib.get_monotonic_time() - t0 - TIMER_MS * 1000;
        phaseAsync();
        return GLib.SOURCE_REMOVE;
    });
    const [ok] = GLib.file_get_contents(fifo); // bloqueia ~300 ms
    if (!ok) fail('leitura síncrona do FIFO falhou');
    results.syncReadUs = GLib.get_monotonic_time() - t0;
}

// (b) mesma leitura, assíncrona: o timer dispara na hora marcada.
function phaseAsync() {
    const fifo = makeFifo('fifo-async');
    delayedWriter(fifo);
    const t0 = GLib.get_monotonic_time();
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, TIMER_MS, () => {
        results.asyncDelay = GLib.get_monotonic_time() - t0 - TIMER_MS * 1000;
        return GLib.SOURCE_REMOVE;
    });
    Gio.File.new_for_path(fifo).load_contents_async(null, (f, res) => {
        const [ok] = f.load_contents_finish(res);
        if (!ok) fail('leitura assíncrona do FIFO falhou');
        results.asyncReadUs = GLib.get_monotonic_time() - t0;
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => { catalogProbe(); return GLib.SOURCE_REMOVE; });
    });
}

// Custo real das 4 sondagens de caminho do catálogo, na forma síncrona que o applet
// usava antes desta rodada — é a linha de base do contraste com a assíncrona
// (file_get_contents até o primeiro que existe).
function catalogPaths(code) {
    const rel = ['LC_MESSAGES', 'ai-usage@claudio.drews.mo'];
    const appletPath = GLib.get_current_dir();
    const dataHome = GLib.getenv('XDG_DATA_HOME') || GLib.build_filenamev([GLib.get_home_dir(), '.local', 'share']);
    return [
        GLib.build_filenamev([appletPath, 'locale', code].concat(rel)),
        GLib.build_filenamev([appletPath, '..', 'locale', code].concat(rel)),
        GLib.build_filenamev([dataHome, 'locale', code].concat(rel)),
        GLib.build_filenamev(['/usr/share/locale', code].concat(rel)),
    ];
}
function catalogProbe() {
    const paths = catalogPaths('pt_BR');
    let hit = -1, firstUs = 0;
    let t0 = GLib.get_monotonic_time();
    for (let i = 0; i < paths.length; i++) {
        try {
            const [ok] = GLib.file_get_contents(paths[i]);
            if (ok) { hit = i; break; }
        } catch (e) { /* ausente: próxima sondagem */ }
    }
    firstUs = GLib.get_monotonic_time() - t0;
    const N = 200;
    t0 = GLib.get_monotonic_time();
    for (let n = 0; n < N; n++)
        for (let i = 0; i <= (hit < 0 ? paths.length - 1 : hit); i++)
            try { GLib.file_get_contents(paths[i]); } catch (e) {}
    const avgUs = (GLib.get_monotonic_time() - t0) / N;
    report(firstUs, avgUs, hit);
}

function report(firstUs, avgUs, hit) {
    cleanup();
    print('medicao no laco principal do cjs real:');
    print('  timer de ' + TIMER_MS + ' ms com leitura SINCRONA do FIFO: atraso ' + ms(results.syncDelay) +
          ' ms (leitura bloqueou ' + ms(results.syncReadUs) + ' ms do laco)');
    print('  timer de ' + TIMER_MS + ' ms com load_contents_async do FIFO: atraso ' + ms(results.asyncDelay) +
          ' ms (dados chegaram em ' + ms(results.asyncReadUs) + ' ms, sem segurar o laco)');
    print('  sondagens do catalogo (4 caminhos, sincrono, primeiro hit no caminho ' + (hit + 1) + '/4): ' +
          ms(firstUs) + ' ms na primeira vez, ' + ms(avgUs) + ' ms em media (200 repeticoes)');
    const syncMs = results.syncDelay / 1000, asyncMs = results.asyncDelay / 1000;
    if (!(syncMs > 100 && asyncMs < 100)) {
        printerr('FAIL: contraste ausente (sincrono ' + syncMs.toFixed(1) + ' ms, assincrono ' + asyncMs.toFixed(1) + ' ms)');
        System.exit(1);
    }
    print('  contraste confirmado: leitura sincrona segurou o laco; assincrona nao');
    System.exit(0);
}

try { phaseSync(); } catch (e) { fail('' + e); }
loop.run();
