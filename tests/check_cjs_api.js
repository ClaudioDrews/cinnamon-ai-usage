// Runtime API check only: no stage, panel activation or Cinnamon restart.
imports.gi.versions.Clutter = '0';
imports.gi.versions.Cogl = '0';
const St = imports.gi.St;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const properties = St.Bin.list_properties().map(p => p.name);
for (const name of ['x-fill', 'x-align', 'width', 'height'])
    if (!properties.includes(name)) throw new Error('Missing St.Bin property: '+name);
if (typeof St.Bin.prototype.set_child !== 'function') throw new Error('Missing set_child');
if (typeof St.BoxLayout.prototype.add_actor !== 'function') throw new Error('Missing add_actor');
const loop = GLib.MainLoop.new(null, false);
const proc = Gio.Subprocess.new(['/usr/bin/printf', '{"schema_version":1}'], Gio.SubprocessFlags.STDOUT_PIPE);
proc.communicate_utf8_async(null, null, (p, res) => {
    const [ok, stdout] = p.communicate_utf8_finish(res);
    if (!ok || JSON.parse(stdout).schema_version !== 1) throw new Error('subprocess output');
    print('CJS: St API properties/methods and actual asynchronous Gio subprocess OK');
    loop.quit();
});
loop.run();
