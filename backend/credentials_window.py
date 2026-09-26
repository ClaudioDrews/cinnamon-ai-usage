#!/usr/bin/env python3
"""Janela de credenciais do Cinnamon AI Usage.

Grava o que a pessoa digita no cofre do sistema (Secret Service), aponta um arquivo
NOME=VALOR ou um arquivo de token OAuth em JSON, tudo em ``config.json`` sem segredo.

Regras: nenhum valor é exibido, registrado ou escrito no cache; o arquivo de
configuração guarda apenas caminhos, nunca credenciais.

Uso: python3 credentials_window.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk  # noqa: E402

import credentials  # noqa: E402

APP_ID = "claudio.drews.CinnamonAIUsage.Credenciais"
WINDOW_TITLE = "Credenciais — Uso de IA"

# Serviços com chave digitada: rótulo, variável principal e alternativa aceita.
KEY_SERVICES = (
    ("openrouter", "OpenRouter", "OPENROUTER_API_KEY", "a chave em /api/v1/key"),
    ("deepseek", "DeepSeek", "DEEPSEEK_API_KEY", "a chave de API do saldo"),
    ("opencode", "OpenCode Go", "OPENCODE_GO_API_KEY", "a chave do plano Go (Zen não serve)"),
    ("grok", "Grok / xAI", "XAI_MANAGEMENT_API_KEY",
     "management key do Console → Settings → Management Keys (a de inferência não serve)"),
    ("nous", "Nous Portal", "NOUS_PORTAL_TOKEN", "token OAuth da conta"),
)

# Nomes equivalentes aceitos pela mesma credencial. A variável gravada é sempre a preferida do
# backend (a primeira de SERVICE_KEYS): gravar num alias fazia a chave recém-salva perder para
# uma credencial antiga do arquivo.
KEY_ALIASES = {"XAI_MANAGEMENT_API_KEY": ("XAI_MANAGEMENT_KEY",)}

# Serviços cujo token costuma viver em arquivo JSON de outro programa.
TOKEN_SERVICES = (("nous", "Nous Portal"),)


def config_paths():
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return config_dir / "cinnamon-ai-usage"


def load_config():
    try:
        return json.loads((config_paths() / "config.json").read_text())
    except (OSError, ValueError):
        return {}


def save_config(config):
    directory = config_paths()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    fd, name = tempfile.mkstemp(prefix=".config-", dir=directory)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, directory / "config.json")
    finally:
        if os.path.exists(name):
            os.unlink(name)


def source_of(name, config):
    """De onde o valor viria hoje, sem revelar o valor.

    A ordem é a do backend (``credentials.value_source``): o cofre vence em **qualquer** um dos
    nomes aceitos, e só depois vêm arquivo e ambiente. Antes a checagem era por nome — cofre,
    arquivo e ambiente de um candidato antes de passar ao próximo — e a janela informava "do
    arquivo indicado" enquanto a coleta usava a chave guardada no cofre de um alias.
    """
    return credentials.source_label((name,) + KEY_ALIASES.get(name, ()), config)


class CredentialsWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application, title=WINDOW_TITLE,
                         default_width=620, default_height=640)
        self.config = load_config()
        self.entries = {}
        self.status_labels = {}

        header = Gtk.HeaderBar(show_close_button=True)
        header.set_title(WINDOW_TITLE)
        header.set_subtitle("Nada aqui é gravado no cache nem no repositório")
        self.set_titlebar(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_border_width(14)
        scrolled.add(content)
        self.add(scrolled)

        self.message = Gtk.InfoBar(message_type=Gtk.MessageType.INFO)
        self.message.set_revealed(False)
        self.message_label = Gtk.Label(xalign=0)
        self.message_label.set_line_wrap(True)
        self.message.get_content_area().add(self.message_label)
        content.pack_start(self.message, False, False, 0)

        if not credentials.keyring_available():
            self._note(content, "Cofre do sistema indisponível: use um arquivo indicado abaixo.")

        self._key_section(content)
        self._file_section(content)
        self._token_section(content)
        self._help_section(content)

        content.show_all()
        self.refresh_status()

    # -- seções ------------------------------------------------------------

    def _section(self, parent, title):
        frame = Gtk.Frame(label=title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(10)
        frame.add(box)
        parent.pack_start(frame, False, False, 0)
        return box

    def _note(self, parent, text):
        label = Gtk.Label(xalign=0)
        label.set_line_wrap(True)
        label.set_text(text)
        label.get_style_context().add_class("dim-label")
        parent.pack_start(label, False, False, 0)
        return label

    def _key_section(self, parent):
        box = self._section(parent, "Chaves de API")
        self._note(box, "A chave vai para o cofre do sistema (gnome-keyring) e é lida pelo "
                        "coletor na hora da consulta. O campo é limpo depois de salvar.")
        for service, label, variable, hint in KEY_SERVICES:
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name = Gtk.Label(xalign=0)
            name.set_markup(f"<b>{GLib.markup_escape_text(label)}</b>")
            head.pack_start(name, False, False, 0)
            status = Gtk.Label(xalign=1)
            status.get_style_context().add_class("dim-label")
            head.pack_end(status, False, False, 0)
            row.pack_start(head, False, False, 0)
            entry = Gtk.Entry()
            entry.set_visibility(False)
            entry.set_placeholder_text(f"{variable} — {hint}")
            row.pack_start(entry, False, False, 0)
            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            save = Gtk.Button(label="Salvar no cofre")
            save.connect("clicked", self._on_save_key, service, variable, label, entry)
            remove = Gtk.Button(label="Remover do cofre")
            remove.connect("clicked", self._on_remove_key, variable, label)
            actions.pack_start(save, False, False, 0)
            actions.pack_start(remove, False, False, 0)
            row.pack_start(actions, False, False, 0)
            box.pack_start(row, False, False, 0)
            self.entries[variable] = entry
            self.status_labels[variable] = status

    def _file_section(self, parent):
        box = self._section(parent, "Arquivo de credenciais (NOME=VALOR)")
        self._note(box, "Use quando as chaves já estiverem em um arquivo seu, em qualquer caminho "
                        "(por exemplo ~/.env ou ~/.config/secrets.env). O arquivo é lido sem shell.")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.file_entry = Gtk.Entry()
        self.file_entry.set_text(self.config.get("credentials_path", ""))
        self.file_entry.set_placeholder_text("/caminho/para/credenciais.env")
        row.pack_start(self.file_entry, True, True, 0)
        choose = Gtk.Button(label="Escolher…")
        choose.connect("clicked", self._on_choose_file)
        row.pack_start(choose, False, False, 0)
        save = Gtk.Button(label="Salvar caminho")
        save.connect("clicked", self._on_save_file)
        row.pack_start(save, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.file_status = Gtk.Label(xalign=0)
        self.file_status.get_style_context().add_class("dim-label")
        box.pack_start(self.file_status, False, False, 0)

    def _token_section(self, parent):
        box = self._section(parent, "Identificadores do time")
        self._note(box, "Dados que não são segredo, mas a API exige — como o time da xAI. "
                        "Podem vir daqui, de config.json ou do próprio arquivo de credenciais "
                        "(XAI_TEAM_ID).")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name = Gtk.Label(xalign=0)
        name.set_markup("<b>Grok / xAI — team_id</b>")
        row.pack_start(name, False, False, 0)
        self.team_entry = Gtk.Entry()
        self.team_entry.set_text((self.config.get("grok") or {}).get("team_id", ""))
        self.team_entry.set_placeholder_text("console.x.ai/team/&lt;team_id&gt;/…")
        row.pack_start(self.team_entry, True, True, 0)
        save_team = Gtk.Button(label="Salvar")
        save_team.connect("clicked", self._on_save_team)
        row.pack_start(save_team, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.team_status = Gtk.Label(xalign=0)
        self.team_status.get_style_context().add_class("dim-label")
        box.pack_start(self.team_status, False, False, 0)

        box = self._section(parent, "Token OAuth em arquivo JSON")
        self._note(box, "Para serviços que autenticam por login em vez de chave. O token é procurado "
                        "no JSON, em qualquer nível; nada é copiado para o cache.")
        for service, label in TOKEN_SERVICES:
            variable = f"token_files.{service}"
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            name = Gtk.Label(xalign=0)
            name.set_markup(f"<b>{GLib.markup_escape_text(label)}</b>")
            row.pack_start(name, False, False, 0)
            entry = Gtk.Entry()
            entry.set_text((self.config.get("token_files") or {}).get(service, ""))
            entry.set_placeholder_text("/caminho/para/auth.json")
            row.pack_start(entry, True, True, 0)
            save = Gtk.Button(label="Salvar caminho")
            save.connect("clicked", self._on_save_token, service, entry)
            row.pack_start(save, False, False, 0)
            box.pack_start(row, False, False, 0)
            self.entries[variable] = entry

    def _help_section(self, parent):
        box = self._section(parent, "Sem chave")
        self._note(box, "Codex usa o login do próprio CLI (codex login) e Antigravity usa o servidor "
                        "local da IDE aberta — nenhum dos dois pede chave aqui.")

    # -- ações -------------------------------------------------------------

    def _inform(self, text, kind=Gtk.MessageType.INFO):
        self.message.set_message_type(kind)
        self.message_label.set_text(text)
        self.message.set_revealed(True)

    def _on_save_key(self, _button, service, variable, label, entry):
        value = entry.get_text().strip()
        if not value:
            self._inform("Digite a credencial antes de salvar.", Gtk.MessageType.WARNING)
            return
        try:
            credentials.keyring_set(variable, value, label)
        except Exception as error:
            self._inform(f"Não foi possível gravar no cofre: {error}", Gtk.MessageType.ERROR)
            return
        entry.set_text("")
        self._inform(f"{label}: credencial guardada no cofre como {variable}. "
                     "O cofre tem precedência; próxima coleta já usa.")
        self.refresh_status()

    def _on_remove_key(self, _button, variable, label):
        try:
            # Remove também os nomes equivalentes: "removido do cofre" precisa ser verdade
            # inteira, senão um alias esquecido continuaria autenticando.
            removed = any([credentials.keyring_delete(name)
                           for name in (variable,) + KEY_ALIASES.get(variable, ())])
        except Exception as error:
            self._inform(f"Não foi possível remover: {error}", Gtk.MessageType.ERROR)
            return
        self._inform(f"{label}: {'removido do cofre' if removed else 'nada havia no cofre'}.")
        self.refresh_status()

    def _on_choose_file(self, _button):
        dialog = Gtk.FileChooserDialog(title="Escolher arquivo de credenciais", parent=self,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Escolher", Gtk.ResponseType.OK)
        dialog.set_current_folder(str(Path.home()))
        if dialog.run() == Gtk.ResponseType.OK:
            self.file_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def _on_save_file(self, _button):
        path = self.file_entry.get_text().strip()
        self.config["credentials_path"] = path
        self._save_config(self._path_message("Caminho do arquivo de credenciais atualizado.", path))

    @staticmethod
    def _path_message(done, path):
        """Caminho que ainda não existe é aceito: o arquivo pode ser criado depois."""
        if path and not Path(path).expanduser().is_file():
            return f"{done} O arquivo indicado ainda não existe."
        return done

    def _on_save_team(self, _button):
        valor = self.team_entry.get_text().strip()
        if valor and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", valor):
            self._inform("O team_id aceita apenas letras, números, hífen e sublinhado.",
                         Gtk.MessageType.WARNING)
            return
        grok = dict(self.config.get("grok") or {})
        if valor:
            grok["team_id"] = valor
        else:
            grok.pop("team_id", None)
        self.config["grok"] = grok
        self._save_config("Identificador do time atualizado.")

    def _on_save_token(self, _button, service, entry):
        path = entry.get_text().strip()
        token_files = dict(self.config.get("token_files") or {})
        if path:
            token_files[service] = path
        else:
            token_files.pop(service, None)
        self.config["token_files"] = token_files
        self._save_config(self._path_message(f"Arquivo de token do {service} atualizado.", path))

    def _save_config(self, message):
        try:
            save_config(self.config)
        except OSError as error:
            self._inform(f"Não foi possível gravar a configuração: {error}", Gtk.MessageType.ERROR)
            return
        self._inform(message)
        self.refresh_status()

    def refresh_status(self):
        for _service, _label, variable, _hint in KEY_SERVICES:
            label = self.status_labels.get(variable)
            if label is None:
                continue
            if variable == "NOUS_PORTAL_TOKEN" and credentials.oauth_token("nous", self.config):
                label.set_text("do arquivo de token indicado")
                continue
            label.set_text(source_of(variable, self.config))
        path = self.config.get("credentials_path")
        if path:
            discarded = []
            found = credentials.read_file(path, discarded)
            expected = [variable for _s, _l, variable, _h in KEY_SERVICES]
            status = (f"{path} — {sum(1 for v in expected if found.get(v))} "
                      f"de {len(expected)} variáveis esperadas encontradas; "
                      "outras variáveis ficam disponíveis para os conectores.")
            if not Path(path).expanduser().is_file():
                status = f"{path} — arquivo ainda não existe."
            elif discarded:
                # "Não configurado" sem causa confunde: diga qual linha foi ignorada e por quê.
                motivos = ", ".join(f"{name} ({reason})" for name, reason in discarded)
                status += f" Linha(s) ignorada(s) por sintaxe: {motivos}."
            self.file_status.set_text(status)
        else:
            self.file_status.set_text("Nenhum arquivo indicado.")
        if hasattr(self, "team_status"):
            do_config = (self.config.get("grok") or {}).get("team_id")
            do_arquivo = credentials.read_file(self.config.get("credentials_path")).get("XAI_TEAM_ID")
            self.team_status.set_text(
                f"team_id atual: {do_config or do_arquivo or 'não definido'}"
                + (" (da configuração)" if do_config else " (do arquivo de credenciais)"
                   if do_arquivo else ""))


class CredentialsApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0, inactivity_timeout=60_000)
        self._window = None

    def do_activate(self):
        if self._window is None:
            self._window = CredentialsWindow(application=self)
            self._window.connect("destroy", self._on_destroyed)
        self._window.present()

    def _on_destroyed(self, _window):
        self._window = None
        self.quit()


def main(argv=None) -> int:
    return CredentialsApplication().run(list(sys.argv if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
