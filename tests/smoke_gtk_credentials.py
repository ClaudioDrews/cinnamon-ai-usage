#!/usr/bin/env python3
"""Exercise the real GTK credentials window with synthetic data; requires display.

Same shape as `smoke_gtk.py`, and for the same reason: the product activates the language in
its `__main__`, while the harness builds the window by hand — so it activates the language
here too. Without that the two runs, pt_BR and en, came out identical and the capture proved
nothing.

Without `app.run()`: the window is built and the events are pumped by hand, because the
Gtk.Application loop only creates its own window on `activate` — and here the window is
already built. That was the difference between a blank capture and a readable window.

**The isolation is built, not assumed** (see `isolation.py`): the window is built inside an
exclusive temporary sandbox, with `HOME` and every `XDG_*` path pointed at it, the credential
variables out of the environment, and the system keyring, the credentials file of this machine
and the rest of the external sources replaced by fixtures. The previous version said it showed
"without touching the keyring" while calling `credentials.keyring_available()` and resolving
every key through the real precedence order — it read the keyring of the machine and whatever
the environment happened to export. What the capture shows now is a fixture: one variable in
the sandbox credentials file, no keyring entry, no environment variable. A run that reaches a
real source fails instead of writing a capture that claims otherwise.

    LANGUAGE=pt_BR.UTF-8 python3 tests/smoke_gtk_credentials.py out.png [texts.json]
"""
import json
import sys
import time
from pathlib import Path

aqui = Path(__file__).resolve().parent
arvore = aqui.parent
sys.path.insert(0, str(aqui))

from isolation import Isolation

# Caminho da pasta pessoal **antes** do isolamento: nenhum texto da janela pode citá-lo.
HOME_DA_MAQUINA = str(Path.home())

capture = sys.argv[1] if len(sys.argv) > 1 else None
texts_path = sys.argv[2] if len(sys.argv) > 2 else None

# Testemunhas de idioma: um título de seção e um exemplo de caminho, os dois vindos do catálogo.
WITNESSES = {"pt_BR": ("Chaves de API", "/caminho/para/credenciais.env"),
             "en": ("API keys", "/path/to/credentials.env")}


def collect_texts(widget, out):
    """Todo texto que uma pessoa lê na árvore: rótulo, botão, exemplo de campo."""
    from gi.repository import Gtk

    if isinstance(widget, Gtk.Label):
        out.append(widget.get_text())
    elif isinstance(widget, Gtk.Button):
        out.append(widget.get_label() or "")
    elif isinstance(widget, Gtk.Entry):
        out.append(widget.get_placeholder_text() or "")
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            collect_texts(child, out)


with Isolation(tree=arvore, keyring_available=True) as iso:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gtk

    import credentials_window as cw
    import i18n

    i18n.activate()

    # Arquivo de credenciais da fixture, dentro do sandbox: a janela o lê pelo leitor do próprio
    # produto (`credentials.read_file`), que recusa caminho fora daqui. O conteúdo é sintético e
    # o caminho que aparece na captura é o do temporário exclusivo — nunca um desta máquina.
    arquivo = iso.path("credenciais.env")
    arquivo.write_text("DEEPSEEK_API_KEY=example\n", encoding="utf-8")
    config_dir = iso.path("config") / "cinnamon-ai-usage"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps({"credentials_path": str(arquivo)}), encoding="utf-8")

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
    # Nenhum caminho desta máquina no texto que vai para o repositório.
    for text in visible + [window.get_title()]:
        assert HOME_DA_MAQUINA not in text, (
            "a janela mostrou caminho da pasta pessoal: %r" % text)
        assert "/home/" not in text, "a janela mostrou caminho de casa: %r" % text

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
    window.destroy()

    iso.assert_clean(expect=("cofre_disponibilidade", "cofre_leitura", "arquivo_leitura"))
    total, idioma = len(visible), i18n.language()

print(f"GTK credentials: idioma da janela {idioma} conferido, {total} textos visíveis, "
      f"captura={capture}")
print(iso.report(), file=sys.stderr)
