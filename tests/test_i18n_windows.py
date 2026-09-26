"""Janelas de uso e de credenciais: o texto sai do catálogo, pelos identificadores.

Nada aqui abre janela nem exige display: o texto é conferido onde ele nasce — nas funções
que o montam e nos widgets que a janela mandou desenhar, com uma fábrica de widgets de
mentira no lugar do GTK. A suíte passa em qualquer idioma porque toda asserção cita a
CHAVE: ``i18n._("Stale")``, ``i18n._f(i18n._("Reading: {datetime}"), ...)``.

Três coisas se provam aqui, e as três quebram em silêncio:

- rótulo, título, tooltip e mensagem de erro das duas janelas vêm do catálogo (nada de
  literal traduzido nem de inglês fixo no código);
- texto que veio do snapshot do contrato é exibido pelo identificador, não pelo texto
  gravado no idioma da coleta antiga (``i18n.record_text``);
- número, dinheiro, data, hora e duração seguem o idioma em vigor — nos dois idiomas.

O ``python3`` do PATH pode não ter PyGObject (o do sistema tem): sem ``gi`` instalável, um
``gi`` de mentira é posto em ``sys.modules`` só para as janelas ficarem importáveis. Quem
abre janela de verdade é ``tests/smoke_gtk.py``, com sessão gráfica.
"""
import contextlib
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests'))

import i18n  # noqa: E402
import test_i18n  # noqa: E402  (a cobertura de msgid de tests/test_i18n.py, só leitura)


def _importable_gi() -> bool:
    try:
        import gi  # noqa: F401
        return True
    except ImportError:
        return False


class _StubMeta(type):
    """Classe de mentira que também responde a atributo de classe (``Gtk.Application``)."""

    def __getattr__(cls, name):
        return _StubMeta(name, (), {})


def _stub_class(name):
    return _StubMeta(name, (), {})


def _fake_gi():
    """``gi`` mínimo: o suficiente para importar as janelas sem GTK nenhum.

    Só o que o import toca: ``require_version`` e as classes que servem de base. Nenhuma
    função é chamada de verdade — nos testes o próprio módulo ``Gtk`` é substituído.
    """
    gi = types.ModuleType('gi')
    gi.require_version = lambda *args, **kwargs: None
    repository = types.ModuleType('gi.repository')
    for name in ('Gio', 'GLib', 'Gtk', 'GdkPixbuf'):
        setattr(repository, name, _stub_class(name))
    gi.repository = repository
    sys.modules['gi'] = gi
    sys.modules['gi.repository'] = repository


if not _importable_gi():
    _fake_gi()

import credentials_window  # noqa: E402
import window  # noqa: E402


class _Wallet:
    """O que a janela mandou desenhar: só texto, na ordem em que apareceu."""

    def __init__(self):
        self.texts = []

    def add(self, value):
        if isinstance(value, str):
            self.texts.append(value)

    def widget(self, kind='root'):
        return _Widget(self, kind)

    def has(self, text):
        return text in self.texts

    def contains(self, fragment):
        """Verdadeiro quando algum texto desenhado contém o trecho (linhas costumam ser montadas)."""
        return any(fragment in text for text in self.texts)

    def missing(self, expected):
        return [text for text in expected if text not in self.texts]


class _Widget:
    """Widget de mentira: registra o texto e devolve outro widget para qualquer chamada.

    Basta para as duas janelas: elas constroem, rotulam e empacotam — e nada disso precisa
    de display para ser conferido.
    """

    def __init__(self, wallet, kind, args=(), kwargs=None):
        self.wallet = wallet
        self.kind = kind
        for value in list(args) + list((kwargs or {}).values()):
            wallet.add(value)

    def __getattr__(self, name):
        def call(*args, **kwargs):
            for value in list(args) + list(kwargs.values()):
                self.wallet.add(value)
            return _Widget(self.wallet, self.kind + '.' + name, args, kwargs)
        return call

    def get_children(self):
        return []


class _Factory:
    """Faz o papel de ``Gtk.Label``, ``Gtk.Orientation.VERTICAL`` e de método de classe."""

    def __init__(self, wallet, kind):
        self.wallet = wallet
        self.kind = kind

    def __call__(self, *args, **kwargs):
        return _Widget(self.wallet, self.kind, args, kwargs)

    def __getattr__(self, name):
        return _Factory(self.wallet, self.kind + '.' + name)


class _Namespace:
    """Módulo GTK de mentira: qualquer atributo vira fábrica que registra texto."""

    def __init__(self, wallet, name):
        self.wallet = wallet
        self.name = name

    def __getattr__(self, name):
        return _Factory(self.wallet, self.name + '.' + name)


class _GLib:
    """``GLib`` com escape de verdade: o markup do cabeçalho tem de sair texto."""

    def __init__(self, wallet):
        self.wallet = wallet

    @staticmethod
    def markup_escape_text(text):
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def __getattr__(self, name):
        return _Factory(self.wallet, 'GLib.' + name)


class _Entry:
    """Campo de texto de mentira, para as ações da janela de credenciais."""

    def __init__(self, text=''):
        self._text = text
        self.written = None

    def get_text(self):
        return self._text

    def set_text(self, value):
        self.written = value


@contextlib.contextmanager
def drawing(module):
    """Troca o GTK do módulo por fábricas que registram texto, sem display nenhum."""
    wallet = _Wallet()
    patches = [patch.object(module, 'Gtk', _Namespace(wallet, 'Gtk')),
               patch.object(module, 'GLib', _GLib(wallet))]
    for name in ('Gio', 'GdkPixbuf'):
        if hasattr(module, name):
            patches.append(patch.object(module, name, _Namespace(wallet, name)))
    for item in patches:
        item.start()
    try:
        yield wallet
    finally:
        for item in reversed(patches):
            item.stop()


def catalog():
    """O que o catálogo pt_BR diz, por msgid (a leitura é a de tests/test_i18n.py)."""
    return test_i18n.lookup()


class LanguageTestCase(unittest.TestCase):
    """Devolve o idioma em vigor ao fim: o estado de i18n não é desta janela."""

    def setUp(self):
        self._language = i18n.language()
        i18n.activate('pt_BR')
        # A janela de credenciais grava `config.json` de verdade quando o caminho é exercitado
        # (`_on_save_team` em test_path_and_team_messages_are_translated salvava o team_id de
        # mentira por cima da configuração de quem roda a suíte, apagando `credentials_path` e
        # `token_files`). O diretório de configuração vai para um temporário, e a conferência
        # abaixo falha se ele escapar de lá.
        self._config = tempfile.TemporaryDirectory(prefix='ai-usage-config-')
        self.addCleanup(self._config.cleanup)
        patcher = patch.object(credentials_window, 'config_paths',
                               return_value=Path(self._config.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertTrue(str(credentials_window.config_paths()).startswith(self._config.name),
                        'a janela escreveria fora do temporário')

    def tearDown(self):
        i18n.activate(self._language)

    @staticmethod
    def usage_window():
        win = window.UsageWindow.__new__(window.UsageWindow)
        win.demo = False
        win._last_update = None
        win._snapshot = None
        return win

    @staticmethod
    def credentials():
        win = credentials_window.CredentialsWindow.__new__(
            credentials_window.CredentialsWindow)
        win.config = {}
        win.entries = {}
        win.status_labels = {}
        return win

    @staticmethod
    def snapshot(hours_ago: int = 3):
        now = datetime.now(timezone.utc)
        read_at = (now - timedelta(hours=hours_ago)).isoformat()
        return {
            'schema_version': 1,
            'generated_at': read_at,
            'services': [
                {'id': 'codex', 'label': 'Codex', 'status': 'ok', 'source': 'CLI local',
                 'read_at': read_at, 'last_used_at': read_at,
                 'recency_basis': 'observed_change',
                 'message_id': 'Failed to read the service data; try refreshing.',
                 'message': 'Falha ao ler os dados do serviço; tente atualizar.',
                 'metrics': [
                     {'id': 'janela', 'label': 'Janela de 5 h', 'kind': 'quota',
                      'used_percent': 42, 'window_seconds': 18000,
                      'reset_at': (now - timedelta(hours=1)).isoformat()},
                     {'id': 'movel', 'label': 'Janela móvel', 'kind': 'quota',
                      'used_percent': 7.5, 'window_seconds': 18000,
                      'reset_at': (now + timedelta(hours=3)).isoformat()},
                     {'id': 'saldo', 'label': 'Saldo', 'kind': 'balance', 'value': 7.02,
                      'currency': 'USD'},
                     {'id': 'gasto', 'label': 'Gasto', 'kind': 'spend', 'value': None},
                     {'id': 'outro', 'label': 'Outro', 'kind': 'desconhecido', 'value': None},
                 ]},
                {'id': 'grok', 'label': 'Grok', 'status': 'unavailable'},
            ],
        }


class UsageWindowTextTests(LanguageTestCase):
    """Rótulos, mensagens e formatação da janela de uso."""

    def test_status_labels_come_from_the_catalog(self):
        cases = (
            ('ok', i18n._('OK')), ('stale', i18n._('Stale')),
            ('unavailable', i18n._('Unavailable')),
            ('unconfigured', i18n._('Not configured')),
            ('error', i18n._('Error')), ('disabled', i18n._('Disabled')),
        )
        for status, expected in cases:
            self.assertEqual(window.status_text(status), expected, status)
        # Status fora do contrato sai cru (o identificador não é texto), e o rótulo não é
        # adivinhado a partir de outra língua: ' DESATUALIZADO ' não é 'stale'.
        self.assertEqual(window.status_text('novo'), 'novo')
        self.assertEqual(window.status_text(' DESATUALIZADO '), 'desatualizado')
        self.assertEqual(window.status_text(''), i18n._('Undefined'))

    def test_english_label_is_the_msgid(self):
        i18n.activate('en')
        self.assertEqual(window.status_text('stale'), 'Stale')
        self.assertEqual(window.status_text('unconfigured'), 'Not configured')

    def test_recency_text_is_translated_and_says_its_basis(self):
        moment = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        descriptions = {
            'observed_change': i18n._('approximate, inferred from the change in consumption'),
            'reported': i18n._('reported by the source'),
            'unknown': i18n._('approximate, the origin of the date is unknown'),
        }
        for basis in ('observed_change', 'reported', 'unknown'):
            service = {'last_used_at': moment, 'recency_basis': basis}
            self.assertEqual(window.recency_text(service),
                             i18n._f(i18n._('Last use: {relative} ({description})'),
                                     relative=i18n.relative(window.parse_timestamp(moment)),
                                     description=descriptions[basis]), basis)
        # Base desconhecida cai na descrição de origem desconhecida; sem instante, no aviso.
        self.assertEqual(window.recency_text({'last_used_at': moment, 'recency_basis': 'x'}),
                         i18n._f(i18n._('Last use: {relative} ({description})'),
                                 relative=i18n.relative(window.parse_timestamp(moment)),
                                 description=descriptions['unknown']))
        self.assertEqual(window.recency_text({'last_used_at': None}),
                         i18n._('Last use: unknown (the first reading has no history)'))

    def test_reset_and_window_lines_follow_the_language(self):
        # Instante com folga do múltiplo de minuto: a duração não pende da fronteira.
        future_moment = datetime.now(timezone.utc) + timedelta(hours=3, seconds=30)
        future = future_moment.isoformat()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        in_duration = i18n._f(
            i18n._('in {duration}'),
            duration=i18n.duration((future_moment - datetime.now(timezone.utc)).total_seconds()))
        self.assertEqual(window.reset_text({'reset_at': future, 'kind': 'quota'}), i18n._f(
            i18n._('Resets {datetime} ({relative})'),
            datetime=window.format_datetime(future), relative=in_duration))
        self.assertEqual(window.reset_text({'reset_at': past, 'kind': 'quota'}), i18n._f(
            i18n._('Resets {datetime} ({relative})'),
            datetime=window.format_datetime(past), relative=i18n._('awaiting update')))
        self.assertEqual(window.reset_text({'reset_at': future, 'kind': 'balance'}), i18n._f(
            i18n._('Renews {datetime} ({relative})'),
            datetime=window.format_datetime(future), relative=in_duration))
        self.assertEqual(window.reset_text({}), '')
        self.assertEqual(window.reset_text({'reset_at': 'nada'}), '')
        self.assertEqual(window.window_text({'window_seconds': 18000}),
                         i18n._f(i18n._('Window: {duration}'),
                                 duration=i18n.duration(18000)))
        self.assertEqual(window.window_text({'window_seconds': None}), '')
        # Extras da linha da quota: a duração some quando o próprio rótulo já a diz.
        said = window.window_extra({'window_seconds': 18000}, window.format_duration(18000))
        self.assertEqual(said, '')
        self.assertEqual(window.window_extra({'window_seconds': 18000}, 'Janela móvel'),
                         i18n._f(i18n._('Window: {duration}'),
                                 duration=i18n.duration(18000)))

    def test_numbers_money_dates_and_durations_in_both_languages(self):
        moment = datetime(2026, 9, 26, 14, 35, tzinfo=timezone(timedelta(hours=-3)))
        cases = (
            ('pt_BR', '1234,50', '7,02 USD', '26/09/2026 14:35', '42,0% usado', '3 dias'),
            ('en', '1234.50', 'USD 7.02', 'Sep 26, 2026 2:35 PM', '42.0% used', '3 days'),
        )
        for code, number, money, text, percent, days in cases:
            i18n.activate(code)
            self.assertEqual(window.format_number(1234.5), number, code)
            self.assertEqual(window.format_money(7.02, 'USD'), money, code)
            self.assertEqual(window.format_datetime(moment.isoformat()), text, code)
            self.assertEqual(window.format_percent(42), percent, code)
            self.assertEqual(window.format_duration(3 * 86400), days, code)
            # Ausente é ausente, nunca zero — e o texto vem do catálogo.
            self.assertEqual(window.format_percent(None), i18n.percent(None), code)
            self.assertEqual(window.format_number('7'), i18n._('unavailable'), code)
            self.assertEqual(window.format_money('7', 'USD'), i18n._('unavailable'), code)
            self.assertEqual(window.format_datetime(None), i18n._('unknown time'), code)
            self.assertEqual(window.format_relative('nada'), '', code)

    def test_snapshot_labels_are_drawn_from_the_catalog(self):
        snapshot = self.snapshot()
        with drawing(window) as wallet:
            win = self.usage_window()
            win.content = wallet.widget('content')
            win._render_snapshot(snapshot)
        service = snapshot['services'][0]
        read_at = service['read_at']
        movel = service['metrics'][1]
        expected = [
            # O nome do serviço é o rótulo público do contrato (não se traduz) e o status
            # vem do catálogo.
            '<b>Codex</b>',
            f"<small>{i18n._('OK')}</small>",
            i18n._f(i18n._('Source: {source}'), source='CLI local'),
            i18n._f(i18n._('Reading: {datetime} ({relative})'),
                    datetime=window.format_datetime(read_at),
                    relative=window.format_relative(read_at)),
            window.recency_text(service),
            i18n._('Reading details'),
            # Texto que veio do snapshot: quem manda é o identificador.
            i18n._('Failed to read the service data; try refreshing.'),
            # Linha da métrica, tooltip da barra e expander dos serviços sem leitura.
            i18n._f(i18n._('{label} · {percent}'), label='Janela de 5 h',
                    percent=i18n._f(i18n._('{percent}% used'),
                                    percent=i18n.number(42, 1))),
            i18n._f(i18n._('{window} · {reset}'), window=window.window_text(movel),
                    reset=window.reset_text(movel)),
            i18n._f(i18n._('{percent}% of the quota used'), percent=i18n.number(7.5, 1)),
            i18n._f(i18n._('{label}: {money}'), label='Saldo',
                    money=i18n.money(7.02, 'USD')),
            i18n._f(i18n._('{label}: {money}'), label='Gasto',
                    money=i18n.money(None, None)),
            i18n._('No value reported.'),
            i18n._f(i18n._n('No reading ({count} service)',
                            'No reading ({count} services)', 1), count=1),
            i18n._f(i18n._('Collection from {datetime} ({relative})'),
                    datetime=window.format_datetime(read_at),
                    relative=window.format_relative(read_at)),
        ]
        self.assertEqual(wallet.missing(expected), [])

    def test_the_source_of_the_reading_is_drawn_by_its_identifier(self):
        """A origem é texto do cache como qualquer outro: com identificador, o idioma manda.

        "OpenRouter · chave", gravado por uma coleta em português, não pode atravessar uma
        apresentação em inglês — e o texto gravado segue ao lado, para quem não tem catálogo.
        """
        snapshot = self.snapshot()
        servico = snapshot['services'][0]
        servico.update({'source_id': 'OpenRouter · key', 'source_args': {},
                        'source': 'OpenRouter · chave'})
        for code, origem in (('pt_BR', 'OpenRouter · chave'), ('en', 'OpenRouter · key')):
            i18n.activate(code)
            with drawing(window) as wallet:
                win = self.usage_window()
                win.content = wallet.widget('content')
                win._render_snapshot(snapshot)
            self.assertTrue(wallet.has(
                i18n._f(i18n._('Source: {source}'), source=origem)), code)

    def test_plural_of_the_no_reading_expander_follows_the_language(self):
        snapshot = self.snapshot()
        snapshot['services'].append({'id': 'extra', 'label': 'Extra', 'status': 'error'})
        for code in ('pt_BR', 'en'):
            i18n.activate(code)
            with drawing(window) as wallet:
                win = self.usage_window()
                win.content = wallet.widget('content')
                win._render_snapshot(snapshot)
            self.assertTrue(wallet.has(i18n._f(
                i18n._n('No reading ({count} service)', 'No reading ({count} services)', 2),
                count=2)), code)

    def test_stale_and_skipped_notices_are_translated(self):
        snapshot = self.snapshot()
        snapshot['notice'] = ('Refresh skipped: a collection is already running; the '
                              'values are the last reading.')
        with drawing(window) as wallet:
            win = self.usage_window()
            win.content = wallet.widget('content')
            win._render_snapshot(snapshot, stale_notice='detalhe do erro')
        expected = [
            i18n._f(i18n._('Showing the last known reading; the most recent collection '
                           'failed: {reason}'), reason='detalhe do erro'),
            # Aviso do momento: sem identificador no contrato, vale o texto que veio.
            snapshot['notice'],
        ]
        self.assertEqual(wallet.missing(expected), [])
        # Com identificador, quem manda é ele — mesmo com texto gravado em outro idioma.
        snapshot['notice_id'] = snapshot['notice']
        snapshot['notice'] = 'Atualização ignorada, texto de coleta antiga.'
        with drawing(window) as wallet:
            win = self.usage_window()
            win.content = wallet.widget('content')
            win._render_snapshot(snapshot)
        self.assertTrue(wallet.has(i18n._('Refresh skipped: a collection is already '
                                          'running; the values are the last reading.')))

    def test_empty_snapshot_and_demo_footer(self):
        with drawing(window) as wallet:
            win = self.usage_window()
            win.content = wallet.widget('content')
            win._render_snapshot({'services': []})
        self.assertTrue(wallet.has(i18n._('The collector returned no services.')))
        with drawing(window) as wallet:
            win = self.usage_window()
            win.demo = True
            win.content = wallet.widget('content')
            win._render_snapshot(self.snapshot())
        self.assertTrue(wallet.contains(i18n._(' · demo data')))
        # Com a hora da última atualização, o rodapé segue o formato do idioma.
        with drawing(window) as wallet:
            win = self.usage_window()
            win._last_update = datetime.now(timezone.utc)
            win.content = wallet.widget('content')
            win._render_snapshot(self.snapshot())
        self.assertTrue(wallet.contains(i18n._f(
            i18n._(' · shown at {time}'),
            time=i18n.time_text(window.to_local(win._last_update)))))

    def test_metric_label_from_identifier_follows_the_current_language(self):
        metric = {'id': 'janela', 'kind': 'quota', 'used_percent': 42,
                  'label_id': 'Critical quota', 'label_args': {},
                  'label': 'Cota crítica'}
        with drawing(window) as wallet:
            win = self.usage_window()
            win.content = wallet.widget('content')
            win._build_metric_row(metric)
        self.assertTrue(wallet.has(i18n._f(
            i18n._('{label} · {percent}'), label=i18n._('Critical quota'),
            percent=window.format_percent(42))))
        i18n.activate('en')
        with drawing(window) as wallet:
            win = self.usage_window()
            win.content = wallet.widget('content')
            win._build_metric_row(metric)
        self.assertTrue(wallet.has(i18n._f(
            i18n._('{label} · {percent}'), label='Critical quota',
            percent=window.format_percent(42))))

    def test_collector_error_message_comes_from_the_catalog(self):
        client = window.CollectorClient()
        missing = Path('/caminho/que/nao/existe/collector.py')
        with patch.object(window, 'COLLECTOR_PATH', missing):
            results = []
            self.assertFalse(client.start(['collect'], results.append))
        self.assertEqual(results[0].error,
                         i18n._f(i18n._('Collector not found at {path}.'), path=missing))


class CredentialsWindowTextTests(LanguageTestCase):
    """Rótulos, notas, botões e mensagens da janela de credenciais."""

    def test_sections_notes_and_buttons_come_from_the_catalog(self):
        win = self.credentials()
        with drawing(credentials_window) as wallet:
            parent = wallet.widget('parent')
            win._key_section(parent)
            win._file_section(parent)
            win._token_section(parent)
            win._help_section(parent)
        expected = [
            i18n._('API keys'), i18n._('Credentials file (NAME=VALUE)'),
            i18n._('Team identifiers'), i18n._('OAuth token in a JSON file'),
            i18n._('Without a key'),
            i18n._('Save to the keyring'), i18n._('Remove from the keyring'),
            i18n._('Choose…'), i18n._('Save path'), i18n._('Save'),
            i18n._('The key goes to the system keyring (gnome-keyring) and is read by the '
                   'collector at query time. The field is cleared after saving.'),
            i18n._('Use it when the keys are already in a file of yours, at any path (for '
                   'example ~/.env or ~/.config/secrets.env). The file is read without a '
                   'shell.'),
            i18n._('Data that is not a secret, but the API requires — such as the xAI team. '
                   'It can come from here, from config.json or from the credentials file '
                   'itself (XAI_TEAM_ID).'),
            i18n._('For services that authenticate by login instead of a key. The token is '
                   'looked up in the JSON, at any level; nothing is copied to the cache.'),
            i18n._('Codex uses the login of the CLI itself (codex login) and Antigravity '
                   'uses the local server of the open IDE — neither one asks for a key '
                   'here.'),
            i18n._('/path/to/credentials.env'), i18n._('/path/to/auth.json'),
            i18n._('console.x.ai/team/&lt;team_id&gt;/…'),
            # O nome do time sai em markup, como o serviço na outra janela.
            f"<b>{i18n._('Grok / xAI — team_id')}</b>",
        ]
        self.assertEqual(wallet.missing(expected), [])

    def test_key_hints_are_msgids_and_the_placeholder_joins_both(self):
        i18n.activate('en')
        entries = catalog()
        english = {}
        for service, _label, _variable in credentials_window.KEY_SERVICES:
            msgid = credentials_window.key_hint(service)
            english[service] = msgid
            self.assertIn(msgid, entries, service)
        i18n.activate('pt_BR')
        for service, _label, _variable in credentials_window.KEY_SERVICES:
            self.assertNotEqual(credentials_window.key_hint(service), english[service],
                                service)   # traduzido, não o msgid cru
        with drawing(credentials_window) as wallet:
            win = self.credentials()
            win._key_section(wallet.widget('parent'))
        for service, _label, variable in credentials_window.KEY_SERVICES:
            self.assertTrue(wallet.has(i18n._f(i18n._('{variable} — {hint}'),
                                               variable=variable,
                                               hint=credentials_window.key_hint(service))),
                            service)

    def test_titles_follow_the_language(self):
        self.assertEqual(i18n._('Credentials — AI usage'), 'Credenciais — Uso de IA')
        self.assertEqual(i18n._('API keys'), 'Chaves de API')
        i18n.activate('en')
        self.assertEqual(i18n._('Credentials — AI usage'), 'Credentials — AI usage')
        self.assertEqual(i18n._('API keys'), 'API keys')

    def test_saving_and_removing_messages_are_translated(self):
        win = self.credentials()
        win.refresh_status = lambda: None
        entry = _Entry('chave-nova')
        with drawing(credentials_window) as wallet:
            win.message = wallet.widget('message')
            win.message_label = wallet.widget('message_label')
            with patch.object(credentials_window.credentials, 'keyring_set',
                              side_effect=RuntimeError('cofre fora do ar')):
                win._on_save_key(None, 'openrouter', 'OPENROUTER_API_KEY', 'OpenRouter', entry)
            self.assertTrue(wallet.has(i18n._f(
                i18n._('Could not write to the keyring: {error}'),
                error=RuntimeError('cofre fora do ar'))))
            with patch.object(credentials_window.credentials, 'keyring_set', return_value=None):
                win._on_save_key(None, 'openrouter', 'OPENROUTER_API_KEY', 'OpenRouter', entry)
            self.assertTrue(wallet.has(i18n._f(
                i18n._('{label}: credential saved to the keyring as {variable}. The keyring '
                       'has precedence; the next collection already uses it.'),
                label='OpenRouter', variable='OPENROUTER_API_KEY')))
        self.assertEqual(entry.written, '')

    def test_removing_says_which_of_the_two_things_happened(self):
        win = self.credentials()
        win.refresh_status = lambda: None
        with drawing(credentials_window) as wallet:
            win.message = wallet.widget('message')
            win.message_label = wallet.widget('message_label')
            with patch.object(credentials_window.credentials, 'keyring_delete',
                              return_value=True):
                win._on_remove_key(None, 'OPENROUTER_API_KEY', 'OpenRouter')
            self.assertTrue(wallet.has(
                i18n._f(i18n._('{label}: removed from the keyring.'), label='OpenRouter')))
            with patch.object(credentials_window.credentials, 'keyring_delete',
                              return_value=False):
                win._on_remove_key(None, 'OPENROUTER_API_KEY', 'OpenRouter')
            self.assertTrue(wallet.has(i18n._f(
                i18n._('{label}: there was nothing in the keyring.'), label='OpenRouter')))

    def test_path_and_team_messages_are_translated(self):
        win = self.credentials()
        win.refresh_status = lambda: None
        self.assertEqual(
            win._path_message(i18n._('Credentials file path updated.'), '/nao/existe'),
            i18n._f(i18n._('{done} The indicated file does not exist yet.'),
                    done=i18n._('Credentials file path updated.')))
        self.assertEqual(win._path_message(i18n._('Team identifier updated.'), ''), 
                         i18n._('Team identifier updated.'))
        with drawing(credentials_window) as wallet:
            win.message = wallet.widget('message')
            win.message_label = wallet.widget('message_label')
            win.team_entry = _Entry('time-invalido!')
            win._on_save_team(None)
            self.assertTrue(wallet.has(
                i18n._('The team_id accepts only letters, numbers, hyphen and underscore.')))
            win.team_entry = _Entry('equipe-1')
            win._on_save_team(None)
            self.assertTrue(wallet.has(i18n._('Team identifier updated.')))
        self.assertEqual(win.config['grok'], {'team_id': 'equipe-1'})

    def test_status_lines_of_the_file_and_of_the_team(self):
        win = self.credentials()
        with drawing(credentials_window) as wallet:
            win.file_status = wallet.widget('file_status')
            win.team_status = wallet.widget('team_status')
            win.config = {'grok': {'team_id': 'equipe-1'}}
            win.refresh_status()
        expected = [
            i18n._('No file indicated.'),
            i18n._f(i18n._('Current team_id: {value}'), value='equipe-1')
            + i18n._(' (from the configuration)'),
        ]
        self.assertEqual(wallet.missing(expected), [])
        # Sem configuração e sem arquivo, o time sai como não definido.
        with drawing(credentials_window) as wallet:
            win.file_status = wallet.widget('file_status')
            win.team_status = wallet.widget('team_status')
            win.config = {}
            win.refresh_status()
        self.assertTrue(wallet.has(i18n._f(i18n._('Current team_id: {value}'),
                                           value=i18n._('not defined'))))

    def test_file_status_counts_the_expected_variables(self):
        win = self.credentials()
        path = ROOT / 'tests' / 'credenciais-de-mentira.env'
        path.write_text('OPENROUTER_API_KEY=chave\n', encoding='utf-8')
        self.addCleanup(path.unlink)
        with drawing(credentials_window) as wallet:
            win.file_status = wallet.widget('file_status')
            win.team_status = wallet.widget('team_status')
            win.config = {'credentials_path': str(path)}
            win.refresh_status()
        self.assertTrue(wallet.has(i18n._f(
            i18n._('{path} — {found} of {expected} expected variables found; the other '
                   'variables remain available to the connectors.'),
            path=str(path), found=1, expected=len(credentials_window.KEY_SERVICES))))
        win.config = {'credentials_path': '/nao/existe/credenciais.env'}
        with drawing(credentials_window) as wallet:
            win.file_status = wallet.widget('file_status')
            win.team_status = wallet.widget('team_status')
            win.refresh_status()
        self.assertTrue(wallet.has(i18n._f(
            i18n._('{path} — the file does not exist yet.'),
            path='/nao/existe/credenciais.env')))


class CatalogTests(LanguageTestCase):
    """As duas janelas não guardam prosa portuguesa nenhuma: tudo passa pelo catálogo."""

    FILES = ('window.py', 'credentials_window.py')

    def test_every_msgid_of_the_windows_is_translated(self):
        entries = catalog()
        for name in self.FILES:
            singles, plurals = test_i18n.py_msgids(ROOT / 'backend' / name)[:2]
            self.assertTrue(singles, name)
            for msgid in sorted(singles | plurals):
                self.assertIn(msgid, entries, f'{name}: msgid sem entrada no catálogo')
                self.assertTrue(any(text.strip() for text in entries[msgid]['text']),
                                f'{name}: msgid sem tradução: {msgid!r}')

    def test_the_shared_detector_finds_no_prose_in_the_windows(self):
        """Nada além do declarado, e o crivo é o mesmo do resto do backend.

        A lista de exceções (nome de serviço, molde, token técnico) vive em
        tests/test_i18n.py, com o motivo de cada literal: um crivo só, para os dois não
        divergirem — aqui se confere o escopo das duas janelas, que é o deste módulo.
        """
        known = set(catalog())
        for name in self.FILES:
            declarado = sorted(test_i18n.NOT_PROSE.get(name, []))
            pendentes = sorted(set(test_i18n.prose_outside_catalog(ROOT / 'backend' / name, known)))
            self.assertEqual(pendentes, declarado, f'{name}: prosa fora do catálogo')


if __name__ == '__main__':
    unittest.main()
