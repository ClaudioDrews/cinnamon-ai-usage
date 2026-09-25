#!/usr/bin/env python3
"""Exercise the real GTK view and collector with synthetic data; requires display."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
import window
from gi.repository import GLib, Gdk

app = window.UsageApplication(unique=False, demo=True)
exit_code = [1]
capture = sys.argv[1] if len(sys.argv) > 1 else None

def verify():
    win = app._window
    if win and win._snapshot:
        try:
            assert win._snapshot.get('demo') is True
            assert len(win._snapshot['services']) == 7
            assert win.get_child().get_visible()
            assert win.content.get_mapped()
            assert not win.collector.busy
            assert win.demo_bar.get_revealed()
            if capture:
                pixbuf = Gdk.pixbuf_get_from_window(win.get_window(), 0, 0, win.get_allocated_width(), win.get_allocated_height())
                pixbuf.savev(capture, 'png', [], [])
            print('GTK demo: 7 services rendered, async collector completed, widgets visible')
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
