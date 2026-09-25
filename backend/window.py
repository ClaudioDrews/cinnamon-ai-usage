#!/usr/bin/env python3
"""Janela GTK3 do Cinnamon AI Usage.

Mostra os serviços e métricas emitidos pelo coletor, conforme docs/contract.md.
Somente leitura: não acessa credenciais, não fala com a rede e não grava cache.
A coleta é feita por subprocesso (sem shell) e nunca bloqueia o GTK.

Uso: python3 window.py [--demo]
"""

from __future__ import annotations

import json
import locale
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gio, GLib, Gtk  # noqa: E402

APP_ID = "local.claudio.CinnamonAIUsage"
WINDOW_TITLE = "Uso de IA"
WINDOW_SUBTITLE = "Serviços de IA monitorados"

COLLECTOR_NAME = "collector.py"
COLLECT_TIMEOUT_SECONDS = 50  # timeout global de coleta (contrato)
UI_WATCHDOG_SECONDS = 60  # watchdog da interface (contrato)

BACKEND_DIR = Path(__file__).resolve().parent
COLLECTOR_PATH = BACKEND_DIR / COLLECTOR_NAME

# Assinatura de status aceita pelo contrato.
STATUS_LABELS = {
    "ok": "OK",
    "stale": "Desatualizado",
    "unavailable": "Indisponível",
    "unconfigured": "Não configurado",
    "error": "Erro",
    "disabled": "Desativado",
}
# Status sem leitura: vão para o expander "Sem leitura".
# `stale` NÃO entra aqui: é leitura anterior preservada após falha e deve aparecer
# na lista principal com o último valor, marcada com aviso (contrato).
NO_READING_STATUSES = ("unavailable", "unconfigured", "error", "disabled")

RECENCY_DESCRIPTIONS = {
    "observed_change": "aproximada, deduzida da mudança no consumo",
    "reported": "informada pela origem",
    "unknown": "aproximada, origem da data desconhecida",
}


# --------------------------------------------------------------------------
# Formatação (texto público, pt-BR)
# --------------------------------------------------------------------------


def escape(text) -> str:
    """Escapa texto público antes de entrar em markup Pango."""
    return GLib.markup_escape_text(str(text))


def parse_timestamp(value):
    """Converte ISO 8601 (com 'Z' ou offset) em datetime com fuso. None se inválido."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def to_local(moment):
    return moment.astimezone() if moment is not None else None


def format_datetime(value) -> str:
    local = to_local(parse_timestamp(value))
    if local is None:
        return "horário desconhecido"
    return local.strftime("%d/%m/%Y %H:%M")


def format_duration(seconds: float) -> str:
    """Duração curta e legível: '42 min', '3 h', '2 dias'."""
    seconds = max(0, int(seconds))
    if seconds < 90:
        return "menos de 2 minutos"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        rest = minutes % 60
        if hours < 12 and rest >= 5:
            return f"{hours} h {rest} min"
        return f"{hours} h"
    return f"{hours // 24} dias"


def format_relative(value) -> str:
    """'há 3 h' para um instante do passado."""
    moment = parse_timestamp(value)
    if moment is None:
        return ""
    delta = (datetime.now(timezone.utc) - moment).total_seconds()
    if delta < 0:
        return "agora"
    return f"há {format_duration(delta)}"


def format_number(value, decimals: int = 2) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "indisponível"
    return f"{float(value):.{decimals}f}".replace(".", ",")


def format_money(value, currency) -> str:
    text = format_number(value)
    if text == "indisponível":
        return text
    return f"{text} {currency}" if currency else text


def format_percent(used_percent) -> str:
    """Percentual ausente é null no contrato: nunca exibir como zero."""
    if used_percent is None:
        return "percentual indisponível"
    number = format_number(used_percent, 1)
    return f"{number}% usado" if number != "indisponível" else "percentual indisponível"


def status_text(status: str) -> str:
    key = (status or "").strip().lower()
    return STATUS_LABELS.get(key, "Indefinido" if not key else key)


def service_has_reading(service: dict) -> bool:
    """Um serviço tem leitura quando o status permite e há métrica utilizável."""
    status = (service.get("status") or "").strip().lower()
    if status in NO_READING_STATUSES:
        return False
    metrics = service.get("metrics")
    return isinstance(metrics, list) and len(metrics) > 0


def recency_text(service: dict) -> str:
    """Recência aproximada, sempre explícita quanto à natureza do dado."""
    last_used = service.get("last_used_at")
    basis = (service.get("recency_basis") or "unknown").strip().lower()
    if not isinstance(last_used, str) or not last_used.strip():
        return "Último uso: desconhecido (a primeira leitura não tem histórico)"
    relative = format_relative(last_used)
    description = RECENCY_DESCRIPTIONS.get(basis, RECENCY_DESCRIPTIONS["unknown"])
    return f"Último uso: {relative} ({description})"


def reset_text(metric: dict) -> str:
    reset_at = metric.get("reset_at")
    moment = parse_timestamp(reset_at)
    if moment is None:
        return ""
    remaining = (moment - datetime.now(timezone.utc)).total_seconds()
    relative = f"em {format_duration(remaining)}" if remaining > 0 else "aguardando atualização"
    label = "Renova" if metric.get("kind") == "balance" else "Reinicia"
    return f"{label} {format_datetime(reset_at)} ({relative})"


def window_text(metric: dict) -> str:
    seconds = metric.get("window_seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return ""
    return f"Janela: {format_duration(seconds)}"


def python_executable() -> str:
    """python3 do PATH, como no contrato; cai para o interpretador atual."""
    return shutil.which("python3") or sys.executable


# --------------------------------------------------------------------------
# Coleta assíncrona
# --------------------------------------------------------------------------


class CollectorResult:
    def __init__(self, ok, snapshot=None, error=None, timed_out=False):
        self.ok = ok
        self.snapshot = snapshot
        self.error = error
        self.timed_out = timed_out


class CollectorClient:
    """Executa `collector.py` em subprocesso sem shell, fora do laço do GTK."""

    def __init__(self):
        self._proc = None
        self._cancellable = None
        self._timeout_id = 0
        self._on_done = None
        self._state = "idle"

    @property
    def busy(self) -> bool:
        return self._state == "running"

    def start(self, args, on_done) -> bool:
        """args é a lista de argumentos do coletor, por exemplo ['collect', '--force']."""
        if self.busy:
            return False
        if not COLLECTOR_PATH.is_file():
            on_done(
                CollectorResult(False, error=f"Coletor não encontrado em {COLLECTOR_PATH}.")
            )
            return False

        argv = [python_executable(), str(COLLECTOR_PATH), *args]
        try:
            self._proc = Gio.Subprocess.new(
                argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            )
        except GLib.Error as exc:
            self._proc = None
            on_done(CollectorResult(False, error=f"Falha ao iniciar o coletor: {exc.message}"))
            return False

        self._on_done = on_done
        self._state = "running"
        self._timed_out = False
        self._cancellable = Gio.Cancellable()
        self._timeout_id = GLib.timeout_add_seconds(
            COLLECT_TIMEOUT_SECONDS, self._on_collect_timeout
        )
        self._proc.communicate_utf8_async(None, self._cancellable, self._on_communicate)
        return True

    def cancel(self):
        """Encerra a coleta em andamento (fechamento da janela)."""
        self._remove_timeout()
        self._state = "idle"
        proc, self._proc = self._proc, None
        self._on_done = None
        if self._cancellable is not None:
            self._cancellable.cancel()
            self._cancellable = None
        if proc is not None:
            try:
                proc.send_signal(15)
            except GLib.Error:
                pass

    # -- internos ---------------------------------------------------------

    def _remove_timeout(self):
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = 0

    def _on_collect_timeout(self):
        self._timeout_id = 0
        self._timed_out = True
        if self._proc is not None:
            try:
                self._proc.send_signal(15)
            except GLib.Error:
                pass
        return GLib.SOURCE_REMOVE

    def _finish(self, result: CollectorResult):
        self._remove_timeout()
        self._state = "idle"
        self._cancellable = None
        callback, self._on_done = self._on_done, None
        if callback is not None:
            callback(result)

    def _on_communicate(self, _source, result, _user_data=None):
        proc, self._proc = self._proc, None
        if proc is None or self._on_done is None:  # cancelado durante a coleta
            return
        timed_out = self._timed_out
        try:
            success, stdout, stderr = proc.communicate_utf8_finish(result)
        except GLib.Error as exc:
            self._finish(CollectorResult(False, error=f"Falha ao ler a saída do coletor: {exc.message}"))
            return

        if timed_out:
            self._finish(
                CollectorResult(
                    False,
                    error=f"Tempo limite de {COLLECT_TIMEOUT_SECONDS}s excedido na coleta.",
                    timed_out=True,
                )
            )
            return

        if not success or not proc.get_successful():
            code = proc.get_exit_status()
            detail = ""
            for line in (stderr or "").strip().splitlines():
                if line.strip():
                    detail = line.strip()[:200]
                    break
            message = f"Coletor terminou com erro (código {code})."
            if detail:
                message += f" {detail}"
            self._finish(CollectorResult(False, error=message))
            return

        try:
            snapshot = json.loads(stdout or "")
        except (json.JSONDecodeError, TypeError):
            self._finish(CollectorResult(False, error="Resposta do coletor não é JSON válido."))
            return

        services = snapshot.get("services") if isinstance(snapshot, dict) else None
        if not isinstance(services, list) or snapshot.get("schema_version") != 1:
            self._finish(CollectorResult(False, error="Resposta do coletor fora do contrato."))
            return

        self._finish(CollectorResult(True, snapshot=snapshot))


# --------------------------------------------------------------------------
# Janela
# --------------------------------------------------------------------------


class UsageWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application, demo: bool = False):
        super().__init__(
            application=application,
            title=WINDOW_TITLE,
            default_width=560,
            default_height=680,
        )
        self.demo = bool(demo)
        self.collector = CollectorClient()
        self._watchdog_id = 0
        self._snapshot = None
        self._last_update = None

        header = Gtk.HeaderBar(show_close_button=True)
        header.set_title(WINDOW_TITLE)
        header.set_subtitle(WINDOW_SUBTITLE)
        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        self.refresh_button.set_tooltip_text("Atualizar agora (força nova coleta)")
        self.refresh_button.connect("clicked", self._on_refresh_clicked)
        header.pack_end(self.refresh_button)
        self.spinner = Gtk.Spinner()
        header.pack_start(self.spinner)
        self.set_titlebar(header)
        header.show_all()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        self.error_bar = Gtk.InfoBar(message_type=Gtk.MessageType.ERROR, show_close_button=True)
        self.error_bar.set_revealed(False)
        self.error_label = self._info_bar_label(self.error_bar)
        self.error_bar.connect("response", lambda bar, _resp: bar.set_revealed(False))
        root.pack_start(self.error_bar, False, False, 0)

        self.demo_bar = Gtk.InfoBar(message_type=Gtk.MessageType.INFO)
        self.demo_bar.set_revealed(False)
        self._info_bar_label(self.demo_bar).set_text(
            "Demonstração — valores fictícios, sem alterar seu histórico."
        )
        root.pack_start(self.demo_bar, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.content.set_border_width(12)
        scrolled.add(self.content)
        root.pack_start(scrolled, True, True, 0)

        self.connect("destroy", self._on_destroy)

        if self.demo:
            self.demo_bar.set_revealed(True)

        self._show_placeholder("Carregando dados dos serviços…")
        root.show_all()
        self.refresh_button.grab_focus()
        # Primeira abertura: usa o cache se ainda estiver no TTL (sem --force).
        self._start_collection(["demo"] if self.demo else ["collect"])

    # -- construção auxiliar ---------------------------------------------

    @staticmethod
    def _info_bar_label(bar: Gtk.InfoBar) -> Gtk.Label:
        label = Gtk.Label(xalign=0)
        label.set_line_wrap(True)
        label.set_selectable(False)
        bar.get_content_area().add(label)
        bar.show_all()
        return label

    def _clear_content(self):
        for child in self.content.get_children():
            self.content.remove(child)
            child.destroy()

    def _show_placeholder(self, text: str):
        self._clear_content()
        label = Gtk.Label(label=text, xalign=0)
        label.get_style_context().add_class("dim-label")
        self.content.pack_start(label, False, False, 0)
        self.content.show_all()

    def _add_line(self, box: Gtk.Box, text: str, markup: bool = False, dim: bool = False):
        label = Gtk.Label(xalign=0)
        label.set_line_wrap(True)
        label.set_selectable(True)
        if markup:
            label.set_markup(text)
        else:
            label.set_text(text)
        if dim:
            label.get_style_context().add_class("dim-label")
        box.pack_start(label, False, False, 0)
        return label

    # -- coleta -----------------------------------------------------------

    def _start_collection(self, args):
        if self.collector.busy:
            return
        self.refresh_button.set_sensitive(False)
        self.spinner.start()
        self._watchdog_id = GLib.timeout_add_seconds(UI_WATCHDOG_SECONDS, self._on_watchdog)
        self.collector.start(args, self._on_collection_done)

    def _on_watchdog(self):
        self._watchdog_id = 0
        if self.collector.busy:
            self._show_placeholder(
                "A coleta está demorando mais que o esperado. "
                f"O coletor é encerrado em {COLLECT_TIMEOUT_SECONDS} segundos."
            )
        return GLib.SOURCE_REMOVE

    def _clear_watchdog(self):
        if self._watchdog_id:
            GLib.source_remove(self._watchdog_id)
            self._watchdog_id = 0

    def _on_collection_done(self, result: CollectorResult):
        self._clear_watchdog()
        self.spinner.stop()
        self.refresh_button.set_sensitive(True)
        if result.ok:
            self.error_bar.set_revealed(False)
            self._snapshot = result.snapshot
            self._last_update = datetime.now(timezone.utc)
            self._render_snapshot(result.snapshot)
        else:
            self.error_label.set_text(f"Erro na coleta: {result.error}")
            self.error_bar.set_revealed(True)
            if self._snapshot is None:
                self._show_placeholder("Sem dados para exibir enquanto a coleta falha.")
            else:
                self._render_snapshot(self._snapshot, stale_notice=result.error)

    def _on_refresh_clicked(self, _button):
        # Força nova coleta apenas a pedido do usuário (contrato).
        self._start_collection(["demo"] if self.demo else ["collect", "--force"])

    def _on_destroy(self, _widget=None):
        self._clear_watchdog()
        self.collector.cancel()
        return False

    # -- desenho ----------------------------------------------------------

    def _render_snapshot(self, snapshot: dict, stale_notice: str = None):
        self._clear_content()

        services = [s for s in snapshot.get("services", []) if isinstance(s, dict)]
        readable = [s for s in services if service_has_reading(s)]
        without_reading = [s for s in services if not service_has_reading(s)]

        if not services:
            self._add_line(self.content, "O coletor não devolveu serviços.", dim=True)

        for service in readable:
            self.content.pack_start(self._build_service_card(service), False, False, 0)

        if without_reading:
            expander = Gtk.Expander()
            expander.set_label(
                f"Sem leitura ({len(without_reading)} serviço{'s' if len(without_reading) > 1 else ''})"
            )
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            inner.set_border_width(8)
            expander.add(inner)
            for service in without_reading:
                inner.pack_start(self._build_service_card(service), False, False, 0)
            self.content.pack_start(expander, False, False, 0)

        if readable and not without_reading and stale_notice:
            notice = Gtk.Label(xalign=0)
            notice.set_line_wrap(True)
            notice.set_text(
                "Exibindo a última leitura conhecida; a coleta mais recente falhou: "
                f"{stale_notice}"
            )
            self.content.pack_start(notice, False, False, 0)

        self.content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        generated = snapshot.get("generated_at")
        footer = f"Coleta de {format_datetime(generated)} ({format_relative(generated)})"
        if self._last_update is not None:
            footer += f" · exibido às {to_local(self._last_update).strftime('%H:%M')}"
        if self.demo:
            footer += " · dados de demonstração"
        self._add_line(self.content, footer, dim=True)

        self.content.show_all()

    def _build_service_card(self, service: dict) -> Gtk.Frame:
        frame = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(10)
        frame.add(box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = service.get("label") or service.get("id") or "Serviço"
        name = Gtk.Label(xalign=0)
        name.set_markup(f"<b>{escape(label)}</b>")
        header.pack_start(name, True, True, 0)
        status = Gtk.Label(xalign=1)
        status.set_markup(f"<small>{escape(status_text(service.get('status')))}</small>")
        status.get_style_context().add_class("dim-label")
        header.pack_end(status, False, False, 0)
        box.pack_start(header, False, False, 0)

        source = service.get("source")
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        if isinstance(source, str) and source.strip():
            self._add_line(details, f"Origem: {source}", dim=True)

        read_at = service.get("read_at")
        read_line = f"Leitura: {format_datetime(read_at)}"
        relative = format_relative(read_at)
        if relative:
            read_line += f" ({relative})"
        self._add_line(details, read_line, dim=True)
        self._add_line(details, recency_text(service), dim=True)

        if (service.get("status") or "").strip().lower() == "stale":
            # Leitura anterior preservada após falha: aviso visível, valor mantido.
            warning = Gtk.Label(xalign=0)
            warning.set_line_wrap(True)
            warning.set_text(
                "Dados da leitura anterior: a atualização mais recente deste serviço falhou."
            )
            box.pack_start(warning, False, False, 0)

        message = service.get("message")
        if isinstance(message, str) and message.strip():
            self._add_line(box, message, dim=True)

        metrics = service.get("metrics")
        if isinstance(metrics, list) and metrics:
            box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
            for metric in metrics:
                if isinstance(metric, dict):
                    box.pack_start(self._build_metric_row(metric), False, False, 0)

        expander = Gtk.Expander(label="Detalhes da leitura")
        expander.add(details)
        box.pack_start(expander, False, False, 0)

        return frame

    def _build_metric_row(self, metric: dict) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        kind = (metric.get("kind") or "").strip().lower()
        label = metric.get("label") or metric.get("id") or "Métrica"
        if kind == "quota":
            used_percent = metric.get("used_percent")
            self._add_line(row, f"{label} · {format_percent(used_percent)}")
            if used_percent is not None and isinstance(used_percent, (int, float)) and not isinstance(used_percent, bool):
                # Barra somente para quota; valor ausente não vira barra cheia nem zero.
                fraction = max(0.0, min(1.0, float(used_percent) / 100.0))
                bar = Gtk.ProgressBar()
                bar.set_fraction(fraction)
                bar.set_show_text(False)
                bar.set_tooltip_text(f"{format_number(used_percent, 1)}% da quota usada")
                row.pack_start(bar, False, False, 0)
            extras = [part for part in (reset_text(metric),) if part]
            if extras:
                self._add_line(row, " · ".join(extras), dim=True)
        elif kind == "balance":
            self._add_line(row, f"{label}: {format_money(metric.get('value'), metric.get('currency'))}")
            if reset_text(metric):
                self._add_line(row, reset_text(metric), dim=True)
        elif kind == "spend":
            self._add_line(row, f"{label}: {format_money(metric.get('value'), metric.get('currency'))}")
        else:
            value = metric.get("value")
            if value is None:
                self._add_line(row, "Sem valor informado.", dim=True)
            else:
                self._add_line(row, format_money(value, metric.get("currency")))

        return row


class UsageApplication(Gtk.Application):
    """Instância única; aceita --demo pelo parser de opções do GTK."""

    def __init__(self, unique: bool = True, demo: bool = False):
        flags = Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        if not unique:
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(
            application_id=APP_ID + (".Demo" if demo else ""),
            flags=flags,
            inactivity_timeout=60_000,
        )
        self.demo = demo
        self._window = None
        self.add_main_option(
            "demo",
            ord("d"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Exibe dados de demonstração (simulação; não grava cache)",
            None,
        )

    # O parser local precisa aceitar --demo sem erro antes do registro.
    def do_handle_local_options(self, options):
        if options.contains("demo"):
            self.demo = True
        return -1

    def do_command_line(self, command_line):
        self.activate()
        return 0

    def do_activate(self):
        if self._window is None:
            self._window = UsageWindow(application=self, demo=self.demo)
            self._window.connect("destroy", self._on_window_destroyed)
        self._window.present()

    def _on_window_destroyed(self, _window):
        self._window = None
        self.quit()


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass  # mantém o locale do ambiente, sem falhar a janela

    demo = "--demo" in argv or "-d" in argv
    app = UsageApplication(demo=demo)
    try:
        app.register(None)
    except GLib.Error as exc:
        print(
            f"Aviso: instância única indisponível ({exc.message}); abrindo sem registro.",
            file=sys.stderr,
        )
        app = UsageApplication(unique=False, demo=demo)
        return app.run(argv)
    return app.run(argv)


if __name__ == "__main__":
    sys.exit(main())
