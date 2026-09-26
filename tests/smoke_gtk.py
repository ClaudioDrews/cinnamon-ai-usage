#!/usr/bin/env python3
"""Exercise the real GTK view and collector with synthetic data; requires display."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
import window
import providers
import i18n
from gi.repository import GLib, Gdk

# O `__main__` do produto ativa o idioma antes de abrir a janela; aqui a janela é montada à
# mão, então o harness ativa igual. Sem isto o catálogo nunca era carregado e as duas
# execuções — pt_BR e en — saíam idênticas, em inglês: a captura parecia provar a janela em
# português sem provar nada.
i18n.activate()

app = window.UsageApplication(unique=False, demo=True)
exit_code = [1]
capture = sys.argv[1] if len(sys.argv) > 1 else None

def verify():
    win = app._window
    if win and win._snapshot:
        try:
            assert win._snapshot.get('demo') is True
            assert len(win._snapshot['services']) == len(providers.SERVICES)
            assert win.get_child().get_visible()
            assert win.content.get_mapped()
            assert not win.collector.busy
            assert win.demo_bar.get_revealed()
            assert win.get_icon() is not None
            # Testemunha de idioma: a janela tem de mostrar o rótulo do idioma resolvido
            # pelo ambiente (é o mesmo caminho que o applet usa ao abrir a janela).
            esperado = {'pt_BR': 'Semana', 'en': 'Week'}.get(i18n.language())
            rotulos = [m.get('label') for s in win._snapshot['services']
                       for m in s.get('metrics', [])]
            if esperado:
                assert esperado in rotulos, (
                    'idioma %s: %r não apareceu nos rótulos da janela' % (i18n.language(), esperado))
            if capture:
                pixbuf = Gdk.pixbuf_get_from_window(win.get_window(), 0, 0, win.get_allocated_width(), win.get_allocated_height())
                pixbuf.savev(capture, 'png', [], [])
            print(f'GTK demo: {len(providers.SERVICES)} services rendered, collector done, '
                  f'idioma da janela {i18n.language()} conferido')
            exit_code[0] = 0
        finally:
            win.destroy()
        return False
    return True

def failed():
    print('GTK smoke timeout', file=sys.stderr)
    app.quit()
    return False

GLib.timeout_add(200, verify)
GLib.timeout_add_seconds(12, failed)
app.run(['smoke-gtk', '--demo'])
raise SystemExit(exit_code[0])
