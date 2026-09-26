#!/usr/bin/env python3
"""Exercise the real GTK credentials window with synthetic data; requires display.

Same shape as `smoke_gtk.py`, and for the same reason: the product activates the language in
its `__main__`, while the harness builds the window by hand — so it activates the language
here too. Without that the two runs, pt_BR and en, came out identical and the capture proved
nothing.

Without `app.run()`: the window is built and the events are pumped by hand, because the
Gtk.Application loop only creates its own window on `activate` — and here the window is
already built. That was the difference between a blank capture and a readable window. The
synthetic configuration points `credentials_path` at a file with one of the five expected
variables, so the window shows the path, the count and the origin of each key without
touching the keyring. Nothing is installed, activated or reloaded in the panel.

    LANGUAGE=pt_BR.UTF-8 python3 tests/smoke_gtk_credentials.py out.png [texts.json]
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

import credentials_window as cw
import i18n

i18n.activate()
capture = sys.argv[1] if len(sys.argv) > 1 else None
texts_path = sys.argv[2] if len(sys.argv) > 2 else None

# Testemunhas de idioma: um título de seção e um exemplo de caminho, os dois vindos do catálogo.
WITNESSES = {"pt_BR": ("Chaves de API", "/caminho/para/credenciais.env"),
             "en": ("API keys", "/path/to/credentials.env")}

sandbox = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = sandbox.name
config_dir = Path(sandbox.name) / "cinnamon-ai-usage"
config_dir.mkdir(parents=True, exist_ok=True)
# Caminho de exemplo neutro: a janela mostra o caminho tal como está na configuração, e a
# captura vai para o repositório — nada de caminho desta máquina na imagem.
arquivo = Path("/tmp/ai-usage-credentials-example.env")
arquivo.write_text("DEEPSEEK_API_KEY=example\n", encoding="utf-8")
(config_dir / "config.json").write_text(
    json.dumps({"credentials_path": str(arquivo)}), encoding="utf-8")


def collect_texts(widget, out):
    """Todo texto que uma pessoa lê na árvore: rótulo, botão, exemplo de campo."""
    if isinstance(widget, Gtk.Label):
        out.append(widget.get_text())
    elif isinstance(widget, Gtk.Button):
        out.append(widget.get_label() or "")
    elif isinstance(widget, Gtk.Entry):
        out.append(widget.get_placeholder_text() or "")
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            collect_texts(child, out)


app = cw.CredentialsApplication()
try:
    app.register(None)
except Exception:
    pass
window = cw.CredentialsWindow(app)
window.show_all()

deadline = time.time() + 6
while time.time() < deadline and not window.get_mapped():
    while Gtk.events_pending():
        Gtk.main_iteration()
    time.sleep(0.05)
for _ in range(40):          # deixa o compositor desenhar antes de capturar
    while Gtk.events_pending():
        Gtk.main_iteration()
    time.sleep(0.02)

collected = []
collect_texts(window, collected)
visible = sorted({text.strip() for text in collected if text and text.strip()})
for esperado in WITNESSES.get(i18n.language(), ()):
    assert esperado in visible, (
        "idioma %s: %r não apareceu na janela de credenciais" % (i18n.language(), esperado))
if texts_path:
    Path(texts_path).write_text(
        json.dumps({"idioma": i18n.language(), "titulo": window.get_title(),
                    "mapeada": window.get_mapped(), "textos": visible},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
if capture:
    pixbuf = Gdk.pixbuf_get_from_window(window.get_window(), 0, 0,
                                        max(1, window.get_allocated_width()),
                                        max(1, window.get_allocated_height()))
    if pixbuf is None:
        raise SystemExit("GTK credentials: sem pixbuf para capturar")
    pixbuf.savev(capture, "png", [], [])
print(f"GTK credentials: idioma da janela {i18n.language()} conferido, "
      f"{len(visible)} textos visíveis, captura={capture}")
