"""Idioma na coleta e nas credenciais: o identificador viaja, o texto não é a verdade.

Nada de tradução se prova aqui — isso é de `tests/test_i18n.py`. O que se prova é o que uma
conversão de prosa quebra em silêncio, no `collector.py` e no `credentials.py`:

- o aviso de leitura antiga é decidido pelo identificador (`message_id`) e pelo motivo
  estruturado, nunca pelo texto: leitura vencida pelo intervalo não é falha;
- a mensagem de coleta pausada (trava ocupada) e a de falha ao ler configuração/cache saem
  como msgid, e o registro responde no idioma em vigor;
- mensagem de credencial — ausente, linha inválida no arquivo e cofre indisponível — nasce em
  ``_()`` e é resolvida na chamada, não na importação do módulo;
- o caminho de falha não descarta leitura: histórico, carimbos e valores brutos ficam, e o
  identificador acompanha o texto que ele descreve (nunca um identificador órfão).

As asserções citam a **chave** (`i18n._('Last reading available; refresh pending.')`), nunca o
literal em português: assim a suíte passa em qualquer idioma, e um msgid trocado no código
quebra o teste em vez de passar despercebido.
"""
import fcntl
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import collector as c
import credentials
import i18n
import providers as p

# Identificadores citados nos testes. São msgid em inglês: a tradução vem de `i18n._()`.
NO_READING = 'No reading available; refresh to query.'
STALE_INTERVAL = ('Previous reading data: the refresh interval has passed and this service '
                  'has not been read again yet.')
STALE_FAILURE = 'Previous reading data: the most recent refresh of this service failed.'
SKIPPED = ('Refresh skipped: a collection is already running; the values are the last '
           'reading.')
CACHE_FAILURE = 'Failed to read the configuration or write the local cache.'
DISABLED = 'Disabled in the configuration.'
TIMEOUT = 'The query timed out or returned invalid data.'


def english():
    """Volta o idioma em vigor para o inglês: com catálogo, o texto é o próprio msgid."""
    with patch.dict(os.environ, {'LANGUAGE': 'en', 'LC_ALL': 'en', 'LANG': 'en'}):
        i18n.activate()


class _FakeProc:
    """Worker de mentira: entrega um JSON já pronto, sem levantar processo nenhum."""

    def __init__(self, payload=b'', timeout=False):
        self.pid = 2 ** 30          # pid inexistente: o encerramento não encontra o que matar
        self.returncode = 0
        self.stdout = io.BytesIO(b'')
        self._payload = payload
        self._timeout = timeout

    def communicate(self, timeout=None):
        if self._timeout:
            raise subprocess.TimeoutExpired('worker', timeout or 1)
        return self._payload, b''

    def poll(self):
        return None if self._timeout else 0

    def wait(self, timeout=None):
        return 0


def workers(answer=None, timeout=False, failing=()):
    """Fábrica de ``subprocess.Popen``: cada worker devolve o serviço que pediu.

    ``failing`` traz os serviços que estouram o tempo: a falha de um worker não pode decidir o
    destino dos outros.
    """
    def spawn(argv, *args, **kwargs):
        if answer is not None:
            return _FakeProc(json.dumps(answer).encode())
        if timeout or argv[3] in failing:
            return _FakeProc(timeout=True)
        return _FakeProc(json.dumps(p.service(argv[3], 'ok', '', 'teste', [])).encode())
    return spawn


class StaleWarningTests(unittest.TestCase):
    """Leitura vencida pelo intervalo não é falha — e quem decide é o identificador."""

    def setUp(self):
        i18n.activate('pt_BR')

    def tearDown(self):
        english()

    def test_an_expired_reading_is_the_interval_and_not_a_failure(self):
        self.assertNotEqual(i18n._(STALE_INTERVAL), i18n._(STALE_FAILURE))
        self.assertEqual(c.stale_warning({'status': 'stale', 'message_id': c.PENDING_MESSAGE_ID}),
                         i18n._(STALE_INTERVAL))

    def test_the_identifier_wins_over_the_saved_text(self):
        # O texto gravado veio de uma coleta que pode ter sido feita em outro idioma — e o
        # identificador é o que define o que aconteceu.
        trocado = {'status': 'stale', 'message_id': c.PENDING_MESSAGE_ID,
                   'message': i18n._(STALE_FAILURE)}
        self.assertEqual(c.stale_warning(trocado), i18n._(STALE_INTERVAL))

    def test_the_structured_reason_wins_over_everything(self):
        falha = {'status': 'stale', 'stale_reason': 'failure', 'message_id': c.PENDING_MESSAGE_ID}
        self.assertEqual(c.stale_warning(falha), i18n._(STALE_FAILURE))

    def test_a_snapshot_older_than_the_identifier_is_read_by_its_text(self):
        # O texto histórico é a tradução pt_BR deste mesmo msgid: ele sai do catálogo, e não
        # de um literal em português escrito no código.
        legado = i18n._t(c.PENDING_MESSAGE_ID, 'pt_BR')
        self.assertTrue(legado and legado != c.PENDING_MESSAGE_ID)
        self.assertEqual(c.stale_warning({'status': 'stale', 'message': legado}),
                         i18n._(STALE_INTERVAL))

    def test_a_snapshot_without_identifier_keeps_the_failure_reading(self):
        self.assertEqual(c.stale_warning({'status': 'stale', 'message': 'HTTP 429'}),
                         i18n._(STALE_FAILURE))


class StaleReadTests(unittest.TestCase):
    """A marcação de leitura vencida grava o identificador e não descarta nada."""

    read_at = '2026-09-26T10:00:00Z'
    last_used_at = '2026-09-26T09:00:00Z'

    def setUp(self):
        i18n.activate('pt_BR')

    def tearDown(self):
        english()

    def _service(self, minutes_ago=10):
        read_at = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))
        metrics = [{'id': 'primary', 'label': 'Janela de 5 h', 'kind': 'quota',
                    'used_percent': 42.0, 'value': None, 'currency': None,
                    'window_seconds': 18000, 'reset_at': None}]
        return {'id': 'codex', 'label': 'Codex', 'status': 'ok', 'message': '', 'source': 'teste',
                'read_at': read_at.isoformat(timespec='seconds').replace('+00:00', 'Z'),
                'last_used_at': self.last_used_at, 'recency_basis': 'observed_change',
                'metrics': metrics}

    def test_an_expired_reading_is_marked_with_the_identifier_and_keeps_the_data(self):
        antigo = self._service()
        novo = c.stale_read({'schema_version': 1, 'generated_at': c.stamp(), 'services': [antigo]},
                            ttl=120)['services'][0]
        self.assertEqual((novo['status'], novo['stale_reason']), ('stale', 'pending'))
        self.assertEqual(novo['message_id'], c.PENDING_MESSAGE_ID)
        self.assertEqual(novo['message'], i18n._(c.PENDING_MESSAGE_ID))
        self.assertEqual(novo['message_args'], {})
        # Nenhuma leitura descartada: valor bruto, carimbo e histórico intactos.
        self.assertEqual(novo['read_at'], antigo['read_at'])
        self.assertEqual(novo['metrics'], antigo['metrics'])
        self.assertEqual(novo['last_used_at'], self.last_used_at)
        self.assertEqual(novo['recency_basis'], 'observed_change')

    def test_the_same_record_answers_in_another_language_without_recollecting(self):
        vencido = c.stale_read({'services': [self._service()]}, ttl=120)['services'][0]
        self.assertEqual(i18n.record_text(vencido), i18n._(c.PENDING_MESSAGE_ID))
        i18n.activate('en')
        self.assertEqual(i18n.record_text(vencido), c.PENDING_MESSAGE_ID)

    def test_a_reading_inside_the_interval_is_left_alone(self):
        novo = self._service(minutes_ago=0)
        self.assertEqual(c.stale_read({'services': [novo]}, ttl=120)['services'][0], novo)


class EmptySnapshotTests(unittest.TestCase):
    """O snapshot sem leitura é gravado em cache: ele também vai por identificador."""

    def setUp(self):
        i18n.activate('pt_BR')

    def tearDown(self):
        english()

    def test_every_service_carries_the_identifier(self):
        vazio = c.empty_snapshot()
        self.assertEqual(list(vazio), ['schema_version', 'generated_at', 'services'])
        for item in vazio['services']:
            self.assertEqual(item['message_id'], NO_READING)
            self.assertEqual(item['message'], i18n._(NO_READING))
            self.assertEqual(i18n.record_text(item), i18n._(NO_READING))

    def test_the_failure_to_read_config_or_cache_uses_a_message_id(self):
        with patch.object(c, 'collect', side_effect=OSError('cache ilegível')), \
             patch.object(sys, 'argv', ['collector.py']), \
             patch('sys.stdout', new_callable=io.StringIO) as saida:
            c.main()
        resposta = json.loads(saida.getvalue())
        for item in resposta['services']:
            self.assertEqual(item['status'], 'unavailable')
            self.assertEqual(item['message_id'], CACHE_FAILURE)
            self.assertEqual(item['message'], i18n._(CACHE_FAILURE))


class CollectionNoticeTests(unittest.TestCase):
    """Coleta pausada e coleta que estourou o tempo: mensagem por identificador."""

    def setUp(self):
        i18n.activate('pt_BR')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cache = Path(self.directory.name)
        self.raiz = self.cache / 'cinnamon-ai-usage'
        self.raiz.mkdir(parents=True)

    def tearDown(self):
        english()

    def _old_reading(self, status='ok'):
        return {'id': 'codex', 'label': 'Codex', 'status': status, 'message': '', 'source': 'teste',
                'read_at': '2026-09-26T10:00:00Z', 'last_used_at': '2026-09-26T09:00:00Z',
                'recency_basis': 'observed_change',
                'metrics': [{'id': 'primary', 'label': 'Janela de 5 h', 'kind': 'quota',
                             'used_percent': 42.0, 'value': None, 'currency': None,
                             'window_seconds': 18000, 'reset_at': None}]}

    def _cache(self, servico=None):
        antigo = servico or self._old_reading()
        (self.raiz / 'snapshot.json').write_text(json.dumps(
            {'schema_version': 1, 'generated_at': '2026-09-26T10:00:00Z', 'services': [antigo]}))
        return antigo

    def test_a_skipped_collection_says_it_and_keeps_the_readings(self):
        antigo = self._cache()
        fd = os.open(self.raiz / 'collect.lock', os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)              # como uma coleta em andamento
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self.directory.name}, clear=False), \
             patch.object(c.subprocess, 'Popen') as popen:
            resultado = c.collect(force=True)
        popen.assert_not_called()                   # nenhum provedor foi consultado
        self.assertEqual(resultado['notice'], i18n._(SKIPPED))
        self.assertEqual(resultado['generated_at'], '2026-09-26T10:00:00Z')
        codex = resultado['services'][0]
        self.assertEqual(codex['read_at'], antigo['read_at'])
        self.assertEqual(codex['metrics'], antigo['metrics'])

    def test_the_skip_notice_is_not_state(self):
        self._cache()
        fd = os.open(self.raiz / 'collect.lock', os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self.directory.name}, clear=False):
            self.assertIn('notice', c.collect(force=True))
        self.assertNotIn('notice', json.loads((self.raiz / 'snapshot.json').read_text()))

    def test_a_paused_service_is_disabled_by_identifier(self):
        self._cache()
        config = self.cache / 'config' / 'cinnamon-ai-usage'
        config.mkdir(parents=True)
        (config / 'config.json').write_text(json.dumps({'enabled': {'codex': False}}))
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self.directory.name,
                                     'XDG_CONFIG_HOME': str(self.cache / 'config')}, clear=False), \
             patch.object(c.subprocess, 'Popen', side_effect=workers()) as popen:
            resultado = c.collect(force=True)
        pausados = [s for s in resultado['services'] if s['status'] == 'disabled']
        self.assertEqual([s['id'] for s in pausados], ['codex'])
        self.assertEqual(pausados[0]['message_id'], DISABLED)
        self.assertEqual(pausados[0]['message'], i18n._(DISABLED))
        self.assertEqual(popen.call_count, len(c.SERVICES) - 1)
        # Serviço pausado não herda a leitura anterior nem inventa métrica.
        self.assertEqual(pausados[0]['metrics'], [])

    def test_a_worker_that_times_out_names_the_failure_and_keeps_the_history(self):
        antigo = self._cache()
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self.directory.name}, clear=False), \
             patch.object(c.subprocess, 'Popen', side_effect=workers(failing=('codex',))):
            resultado = c.collect(force=True)
        codex = [s for s in resultado['services'] if s['id'] == 'codex'][0]
        self.assertEqual((codex['status'], codex['stale_reason']), ('stale', 'failure'))
        self.assertEqual(codex['message_id'], TIMEOUT)
        self.assertEqual(codex['message'], i18n._(TIMEOUT))
        self.assertEqual(codex['read_at'], antigo['read_at'])
        self.assertEqual(codex['metrics'], antigo['metrics'])
        # A falha é de um serviço só: os outros respondem normalmente.
        self.assertEqual([s['status'] for s in resultado['services'] if s['id'] == 'grok'], ['ok'])

    def test_the_timeout_error_is_the_same_for_every_worker(self):
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self.directory.name}, clear=False), \
             patch.object(c.subprocess, 'Popen', side_effect=workers(timeout=True)):
            resultado = c.collect(force=True)
        for item in resultado['services']:
            self.assertEqual(item['status'], 'error')
            self.assertEqual(item['message_id'], TIMEOUT)
            self.assertEqual(i18n.record_text(item), i18n._(TIMEOUT))


class FailurePathTests(unittest.TestCase):
    """Falha preserva leitura, carimbos e histórico — e o identificador do texto que fica."""

    def setUp(self):
        i18n.activate('pt_BR')

    def tearDown(self):
        english()

    def _previous(self):
        return {'id': 'meta', 'label': 'Meta AI (Muse Code)', 'status': 'ok', 'message': '',
                'source': 'teste', 'read_at': '2026-09-26T10:00:00Z',
                'last_used_at': '2026-09-26T09:00:00Z', 'recency_basis': 'observed_change',
                'metrics': [{'id': 'janela', 'label': 'Janela de 5 h', 'kind': 'quota',
                             'used_percent': 42.0, 'value': None, 'currency': None,
                             'window_seconds': 18000, 'reset_at': None}]}

    def test_a_failure_keeps_the_reading_the_timestamps_and_the_identifier(self):
        anterior = self._previous()
        falha = p.service('meta', 'error', message_id=p.QUOTA_FAILURE_MESSAGE)
        resultado = c.merge_history(falha, anterior)
        self.assertEqual((resultado['status'], resultado['stale_reason']), ('stale', 'failure'))
        self.assertEqual(resultado['read_at'], anterior['read_at'])          # erro não é medição
        self.assertEqual(resultado['metrics'], anterior['metrics'])          # nada descartado
        self.assertEqual(resultado['last_used_at'], anterior['last_used_at'])
        self.assertEqual(resultado['recency_basis'], 'observed_change')
        self.assertEqual(resultado['message_id'], p.QUOTA_FAILURE_MESSAGE)
        self.assertEqual(resultado['message_args'], {})
        self.assertEqual(i18n.record_text(resultado), i18n._(p.QUOTA_FAILURE_MESSAGE))

    def test_a_failure_without_identifier_does_not_inherit_the_previous_one(self):
        # Texto novo com identificador velho faria a interface traduzir a frase errada: sem
        # identificador, o campo some em vez de mentir.
        anterior = self._previous()
        anterior.update(message_id=c.PENDING_MESSAGE_ID, message_args={})
        falha = p.service('meta', 'error', 'HTTP 429', 'teste', [])
        resultado = c.merge_history(falha, anterior)
        self.assertEqual(resultado['status'], 'stale')
        self.assertEqual(resultado['message'], 'HTTP 429')
        self.assertNotIn('message_id', resultado)
        self.assertNotIn('message_args', resultado)
        self.assertEqual(i18n.record_text(resultado), 'HTTP 429')  # sem identificador, o texto fica
        self.assertEqual(resultado['read_at'], anterior['read_at'])
        self.assertEqual(resultado['metrics'], anterior['metrics'])

    def test_a_new_reading_replaces_the_identifier_together_with_the_text(self):
        anterior = self._previous()
        anterior.update(message_id=c.PENDING_MESSAGE_ID, message_args={}, status='stale',
                        stale_reason='pending')
        falha = p.service('meta', 'error', message_id=p.QUOTA_FAILURE_MESSAGE,
                          message_args={'service': 'Meta'})
        resultado = c.merge_history(falha, anterior)
        self.assertEqual(resultado['message_id'], p.QUOTA_FAILURE_MESSAGE)
        self.assertEqual(resultado['message_args'], {'service': 'Meta'})
        self.assertEqual(i18n.record_text(resultado),
                         i18n._f(i18n._(p.QUOTA_FAILURE_MESSAGE), service='Meta'))


class DemoPayloadTests(unittest.TestCase):
    """Rótulo de demonstração entra no contrato por identificador, como o da coleta real."""

    def setUp(self):
        i18n.activate('pt_BR')

    def tearDown(self):
        english()

    def _labels(self, metricas):
        return [i18n.record_text(m, 'label_id', 'label_args', 'label') for m in metricas]

    def test_demo_labels_answer_in_the_language_in_force(self):
        aberto = {s['id']: s for s in c.demo()['services']}['opencode']
        self.assertEqual(self._labels(aberto['metrics']),
                         [i18n._('Rolling window'), i18n._('Week'), i18n._('Month')])
        for metrica in aberto['metrics']:
            self.assertIn('label_id', metrica)
        self.assertEqual(aberto['metrics'][1]['window_seconds'], 604800)  # valor bruto intacto
        i18n.activate('en')
        self.assertEqual(self._labels(aberto['metrics']), ['Rolling window', 'Week', 'Month'])

    def test_demo_source_is_text_in_the_language_of_the_run(self):
        simulado = {s['id']: s for s in c.demo()['services']}
        for item in simulado.values():
            self.assertEqual(item['source'], i18n._('Simulation — no real data'))


class CredentialMessageTests(unittest.TestCase):
    """Mensagens de credencial: ausente, inválida e cofre indisponível, no idioma em vigor."""

    NAMES = ('XAI_MANAGEMENT_API_KEY', 'XAI_MANAGEMENT_KEY')

    def setUp(self):
        i18n.activate('pt_BR')

    def tearDown(self):
        english()

    def _without_keyring(self):
        """Cofre que não existe nesta máquina: nenhum teste toca o cofre de verdade."""
        return patch.object(credentials, 'keyring_get', return_value=None)

    def _without_environment(self):
        return patch.dict(os.environ, {nome: '' for nome in self.NAMES}, clear=False)

    def test_an_absent_credential_is_not_configured(self):
        os.environ.pop('XAI_TEAM_ID', None)
        with self._without_keyring(), self._without_environment():
            self.assertEqual(credentials.source_label(self.NAMES, {}),
                             i18n._('not configured'))
            self.assertIsNone(credentials.service_value('grok', {}))
            self.assertIsNone(credentials.setting_value('grok', {}))

    def test_the_label_follows_the_language_of_the_call_not_of_the_import(self):
        with self._without_keyring(), self._without_environment():
            i18n.activate('pt_BR')
            portugues = credentials.source_label(self.NAMES, {})
            i18n.activate('en')
            self.assertEqual(portugues, i18n._t('not configured', 'pt_BR'))
            self.assertNotEqual(portugues, credentials.source_label(self.NAMES, {}),
                                'rótulo traduzido na importação ficaria preso num idioma só')

    def test_each_layer_names_itself_without_revealing_the_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / 'secrets.env'
            arquivo.write_text('XAI_MANAGEMENT_API_KEY=do-arquivo\n')
            config = {'credentials_path': str(arquivo)}
            with self._without_environment():
                with patch.object(credentials, 'keyring_get', side_effect=lambda nome: 'do-cofre'):
                    # O cofre vence em qualquer um dos nomes aceitos — e vence o arquivo.
                    self.assertEqual(credentials.source_label(self.NAMES, config),
                                     i18n._('stored in the system keyring'))
                with self._without_keyring():
                    self.assertEqual(credentials.source_label(self.NAMES, config),
                                     i18n._('from the indicated file'))
                    self.assertEqual(credentials.service_value('grok', config), 'do-arquivo')
                    self.assertEqual(credentials.source_label(self.NAMES, {}),
                                     i18n._('not configured'))
                with self._without_keyring(), \
                     patch.dict(os.environ, {'XAI_MANAGEMENT_API_KEY': 'do-ambiente'}, clear=False):
                    # O ambiente é a última camada: sem cofre e sem arquivo indicado, ele responde.
                    self.assertEqual(credentials.source_label(self.NAMES, {}),
                                     i18n._('from the environment variable'))
                    self.assertEqual(credentials.service_value('grok', {}), 'do-ambiente')
                    self.assertEqual(credentials.source_label(self.NAMES, config),
                                     i18n._('from the indicated file'))

    def test_an_unavailable_keyring_says_so_when_saving_and_removing(self):
        with patch.object(credentials, '_secret_module', return_value=None):
            for chamada in (lambda: credentials.keyring_set('KEY', 'valor'),
                            lambda: credentials.keyring_delete('KEY')):
                with self.assertRaises(RuntimeError) as erro:
                    chamada()
                self.assertEqual(str(erro.exception), i18n._('System keyring unavailable.'))

    def test_an_invalid_line_comes_with_the_reason_and_the_rest_is_kept(self):
        motivos = []
        self.assertEqual(credentials.parse_assignments('KEY="sem-fecho\nOK=valor\n', motivos),
                         {'OK': 'valor'})
        self.assertEqual(motivos, [('KEY', i18n._('unterminated quotes'))])
        motivos.clear()
        self.assertEqual(credentials.parse_assignments('KEY="a" "b"\n', motivos), {})
        self.assertEqual(motivos, [('KEY', i18n._('more than one value inside quotes'))])
        motivos.clear()
        # Valor vazio não é credencial: some sem virar motivo nem valor.
        self.assertEqual(credentials.parse_assignments('KEY=\n', motivos), {})
        self.assertEqual(motivos, [])

    def test_an_invalid_token_file_is_an_absent_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            quebrado = Path(tmp) / 'auth.json'
            quebrado.write_text('{ isto não é json')
            self.assertIsNone(credentials.token_from_json(str(quebrado)))
            self.assertIsNone(credentials.token_from_json(str(Path(tmp) / 'nao-existe.json')))
            valido = Path(tmp) / 'valido.json'
            valido.write_text(json.dumps({'providers': {'nous': {'access_token': 'token'}}}))
            self.assertEqual(credentials.token_from_json(str(valido)), 'token')
            self.assertIsNone(credentials.oauth_token('nous', {}))     # sem arquivo indicado
            self.assertIsNone(credentials.service_value('nous', {}))


if __name__ == '__main__':
    unittest.main()
