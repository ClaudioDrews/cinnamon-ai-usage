"""Prosa dos provedores no catálogo: rótulo, mensagem e texto que fica no cache.

Nada de tradução se prova aqui — quem confere o catálogo é ``tests/test_i18n.py``. O que se
prova é o que a conversão de ``backend/providers.py`` pode quebrar em silêncio:

- o rótulo de uma métrica e a mensagem de um serviço nascem de um **identificador** (o msgid) mais
  argumentos, e o texto é montado a partir dele no idioma da coleta;
- o argumento vai **cru** (número sem formato fixo): quem escreve o número é ``i18n``, com o
  separador do idioma em vigor, e por isso a mesma leitura aparece ``1,5 h`` em pt_BR e ``1.5 h``
  em inglês;
- identificador ausente do catálogo (leitura antiga, conector novo) volta ao texto gravado — e
  identificador presente manda sobre ele, mesmo que a tradução seja idêntica ao original;
- os caminhos de cache e de histórico não mudaram: a leitura boa é preservada, o carimbo da
  tentativa continua valendo, e a falha registrada segue com o identificador ao lado do texto.

As asserções citam a chave, nunca o literal traduzido (``i18n._('Available balance')``), para a
suíte passar em qualquer idioma — é a regra de docs/i18n.md.
"""
import ast
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import collector as c
import i18n
import providers as p

SOURCE = ROOT / 'backend' / 'providers.py'

# Identificadores citados pelas asserções. Escrever a chave uma vez, aqui, é o que mantém o teste
# legível: se o msgid mudar, é este bloco que muda — e o catálogo acusa a entrada obsoleta.
UNAVAILABLE_BALANCE = 'Available balance'
TOTAL_BALANCE = 'Total available balance'
PREPAID_USED = 'Prepaid credits used'
WINDOW_HOURS = 'Window of {hours} h'
CURRENT_WINDOW = 'Current window'
WEEK = 'Week'
WEEK_MODEL = 'Week · {model}'
WINDOW_WITH_NAME = '{name} · {hours} h window'
QUOTA_WITH_NAME = '{name} · quota'
KEY_LIMIT_RESET = 'Key limit ({reset})'
MODEL_NUMBER = 'Model {number}'
PLAN = 'Plan: {plan}.'
NOTE_PERCENT = 'Meta reported {percent}% usage; the applet bar stops at 100%.'
NO_CREDENTIALS = 'Credentials not configured.'
XAI_KEY = 'xAI management key not configured.'
CONNECTION_FAILED = 'Could not query the service; check the connection.'
HTTP_FAILED = 'Consultation failed (HTTP {code}).'
DEFERRED = ('Consultation deferred: there was already an attempt in the last {minutes} min '
            'and the minimum interval between calls has not passed yet; the previous reading '
            'is kept.')
NOT_IN_CATALOG = 'This msgid is not in the catalog'


def english():
    """Idioma de partida dos testes de cache: o inglês é o msgid, e é o que a suíte espera."""
    with patch.dict(os.environ, {'LANGUAGE': 'en', 'LC_ALL': 'en', 'LANG': 'en'}):
        i18n.activate()


class ProviderTestCase(unittest.TestCase):
    def setUp(self):
        i18n.activate('pt_BR')

    def tearDown(self):
        english()

    def test_language_is_not_forced_to_english_only(self):
        self.assertEqual(i18n.language(), 'pt_BR')


class LabelIdentifierTests(ProviderTestCase):
    """Rótulo de métrica: identificador + argumentos, texto montado pelo helper."""

    def test_the_balance_label_comes_from_the_identifier(self):
        for code in ('pt_BR', 'en'):
            i18n.activate(code)
            metric = p.parse_deepseek({'balance_infos': [{'currency': 'USD',
                                                          'total_balance': '12.40'}]})[0]
            self.assertEqual(metric['label_id'], UNAVAILABLE_BALANCE, code)
            self.assertEqual(metric['label_args'], {}, code)
            self.assertEqual(metric['label'], i18n._(UNAVAILABLE_BALANCE), code)
            self.assertEqual(metric['value'], 12.4, code)
            self.assertEqual(metric['kind'], 'balance', code)

    def test_the_window_label_carries_the_hours_as_argument(self):
        for code in ('pt_BR', 'en'):
            i18n.activate(code)
            metric = p.parse_meta({'subs_usage': {'window': {
                'used_percent': 3, 'window_duration_mins': 300}}})[0]
            self.assertEqual(metric['label_id'], WINDOW_HOURS, code)
            self.assertEqual(metric['label_args'], {'hours': '5'}, code)
            self.assertEqual(metric['label'],
                             i18n._f(i18n._(WINDOW_HOURS), hours='5'), code)
            self.assertEqual(metric['window_seconds'], 18000, code)

    def test_the_window_without_duration_is_its_own_identifier(self):
        metric = p.parse_meta({'subs_usage': {'window': {'used_percent': 7}}})[0]
        self.assertEqual(metric['label_id'], CURRENT_WINDOW)
        self.assertEqual(metric['label'], i18n._(CURRENT_WINDOW))
        self.assertIsNone(metric['window_seconds'])

    def test_the_week_label_is_the_same_identifier_in_both_windows(self):
        meta = p.parse_meta({'subs_usage': {'weekly': {'used_percent': 1}}})[0]
        claude = p.parse_claude({'seven_day': {'utilization': 14}})[0]
        self.assertEqual((meta['label_id'], claude['label_id']), (WEEK, WEEK))
        self.assertEqual((meta['label'], claude['label']),
                         (i18n._(WEEK), i18n._(WEEK)))
        self.assertEqual((meta['id'], claude['id']), ('semanal', 'semanal'))

    def test_each_connector_label_is_an_identifier(self):
        cases = (
            (p.parse_nous({'paid_service_access': {'total_usable_credits': 35,
                                                   'subscription_credits_remaining': 25,
                                                   'purchased_credits_remaining': 10}}),
             [TOTAL_BALANCE, 'Plan balance', 'Prepaid credit balance']),
            (p.parse_grok({'total': {'val': '-1500'},
                           'changes': [{'amount': {'val': '-2000'}}, {'amount': {'val': '500'}}]}),
             ['API prepaid balance', PREPAID_USED]),
            (p.parse_go({'usage': {'rolling': {'percent': 0}, 'weekly': {'percent': 30},
                                   'monthly': {'percent': 9}}}),
             ['Rolling window', WEEK, 'Month']),
            (p.parse_antigravity({'userStatus': {'planStatus': {
                'planInfo': {'monthlyPromptCredits': 50000, 'monthlyFlowCredits': 150000},
                'availablePromptCredits': 500, 'availableFlowCredits': 300}}}),
             ['Prompt credits', 'Flow credits']),
            (p.parse_openrouter({'data': {'limit': None, 'usage_monthly': 2, 'usage': 10}}),
             ['Monthly spend', 'Cumulative key spend']),
        )
        for metrics, expected in cases:
            self.assertEqual([m['label_id'] for m in metrics], expected)
            for metric in metrics:
                self.assertEqual(metric['label'], i18n._(metric['label_id']))
                self.assertEqual(metric['label_args'], {})

    def test_the_key_limit_keeps_the_reset_value_raw(self):
        reset = '2026-10-01T00:00:00Z'
        metric = p.parse_openrouter({'data': {'limit': 20, 'limit_remaining': 15,
                                              'limit_reset': reset}})[0]
        self.assertEqual(metric['label_id'], KEY_LIMIT_RESET)
        self.assertEqual(metric['label_args'], {'reset': reset})
        self.assertEqual(metric['label'], i18n._f(i18n._(KEY_LIMIT_RESET), reset=reset))
        self.assertEqual(metric['used_percent'], 25)

    def test_the_bucket_name_is_a_raw_argument_of_the_composite_label(self):
        """Nome de balde é dado, horas são número: nada de texto já traduzido no argumento.

        Argumento com texto já traduzido ficaria no idioma da coleta quando a interface estivesse
        em outro — por isso a frase que junta o nome à janela é um msgid próprio, com os dois
        valores crus, e a reescrita no idioma em vigor sai inteira.
        """
        metrics = p.parse_codex({'rateLimitsByLimitId': {
            'codex': {'primary': {'usedPercent': 0, 'windowDurationMins': 300}},
            'other': {'limitName': 'Outro balde',
                      'secondary': {'usedPercent': 90, 'windowDurationMins': 10080}}}})
        self.assertEqual([m['label_id'] for m in metrics], [WINDOW_WITH_NAME, WINDOW_WITH_NAME])
        self.assertEqual(metrics[0]['label_args'], {'name': 'codex', 'hours': '5'})
        self.assertEqual(metrics[1]['label_args'], {'name': 'Outro balde', 'hours': '168'})
        self.assertEqual(metrics[1]['label'],
                         i18n._f(i18n._(WINDOW_WITH_NAME), name='Outro balde', hours='168'))

    def test_a_bucket_without_duration_is_a_quota_of_that_bucket(self):
        metrics = p.parse_codex({'rateLimitsByLimitId': {
            'codex': {'primary': {'usedPercent': 0, 'windowDurationMins': 300}},
            'other': {'limitName': 'Outro balde', 'primary': {'usedPercent': 90}}}})
        self.assertEqual(metrics[1]['label_id'], QUOTA_WITH_NAME)
        self.assertEqual(metrics[1]['label_args'], {'name': 'Outro balde'})
        self.assertEqual(metrics[1]['label'],
                         i18n._f(i18n._(QUOTA_WITH_NAME), name='Outro balde'))

    def test_a_model_name_is_data_and_a_missing_name_is_an_identifier(self):
        named, nameless = p.parse_antigravity({'userStatus': {'cascadeModelConfigData': {
            'clientModelConfigs': [
                {'label': 'Claude Sonnet 4.6', 'quotaInfo': {'remainingFraction': .25}},
                {'quotaInfo': {'remainingFraction': .5}}]}}})
        self.assertEqual(named['label'], 'Claude Sonnet 4.6')
        self.assertNotIn('label_id', named)
        self.assertEqual(nameless['label_id'], MODEL_NUMBER)
        self.assertEqual(nameless['label_args'], {'number': 2})
        self.assertEqual(nameless['label'], i18n._f(i18n._(MODEL_NUMBER), number=2))
        # O identificador da métrica continua saindo do rótulo exibido: nada foi renomeado.
        self.assertEqual(named['id'], 'model:Claude Sonnet 4.6')
        self.assertEqual(nameless['id'], 'model:' + i18n._f(i18n._(MODEL_NUMBER), number=2))

    def test_the_claude_scoped_window_names_the_model_as_argument(self):
        got = p.parse_claude({'limits': [
            {'kind': 'session', 'percent': 35.0, 'resets_at': '2026-09-26T22:00:00Z'},
            {'kind': 'weekly_scoped', 'percent': 39.0,
             'scope': {'model': {'display_name': 'Sonnet'}}}]})
        self.assertEqual([m['id'] for m in got], ['janela', 'semanal:Sonnet'])
        self.assertEqual(got[1]['label_id'], WEEK_MODEL)
        self.assertEqual(got[1]['label_args'], {'model': 'Sonnet'})
        self.assertEqual(got[1]['label'], i18n._f(i18n._(WEEK_MODEL), model='Sonnet'))
        self.assertEqual(got[0]['label'],
                         i18n._f(i18n._(WINDOW_HOURS), hours=5))


class MessageIdentifierTests(ProviderTestCase):
    """Mensagem de serviço: o identificador viaja com o registro e a falha o carrega."""

    def test_an_unconfigured_provider_carries_the_identifier_and_no_arguments(self):
        result = p.collect_provider('grok', {})
        self.assertEqual(result['status'], 'unconfigured')
        self.assertEqual(result['message_id'], XAI_KEY)
        self.assertEqual(result['message_args'], {})
        self.assertEqual(result['message'], i18n._(XAI_KEY))

    def test_the_message_of_a_known_identifier_follows_the_language(self):
        """O texto gravado é o da coleta; a leitura reaproveitada sai no idioma em vigor."""
        result = p.collect_provider('grok', {})
        self.assertEqual(result['message'], i18n._(XAI_KEY))     # texto no idioma da coleta
        english()
        self.assertEqual(i18n.record_text(result), XAI_KEY)      # sem catálogo, o msgid é o texto
        i18n.activate('pt_BR')
        self.assertEqual(i18n.record_text(result), i18n._(XAI_KEY))

    def test_an_http_failure_keeps_the_code_as_raw_argument(self):
        error = p.HTTPError('https://exemplo.invalid/uso', 599, 'falha', {}, io.BytesIO())
        with patch.object(p, 'build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(p.Unavailable) as caught:
                p.request('https://exemplo.invalid/uso')
        self.assertEqual(str(caught.exception), HTTP_FAILED)
        self.assertEqual(caught.exception.message_args, {'code': 599})
        self.assertEqual(caught.exception.status, 'error')
        record = p.service('codex', caught.exception.status, message_id=str(caught.exception),
                           message_args=caught.exception.message_args)
        self.assertEqual(record['message'],
                         i18n._f(i18n._(HTTP_FAILED), code=599))

    def test_a_known_http_status_uses_its_own_identifier(self):
        error = p.HTTPError('https://exemplo.invalid/uso', 429, 'limite', {}, io.BytesIO())
        with patch.object(p, 'build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(p.Unavailable) as caught:
                p.request('https://exemplo.invalid/uso')
        self.assertEqual(str(caught.exception),
                         'Consultation limit reached; wait for the next update.')
        self.assertEqual(caught.exception.message_args, {'code': 429})
        self.assertEqual(caught.exception.message_args.get('code'), 429)

    def test_the_deferred_consultation_keeps_the_minutes_as_argument(self):
        for interval, minutes in ((900, 15), (300, 5), (10, 1)):
            error = p.quota_deferred(interval)
            self.assertEqual(str(error), DEFERRED, interval)
            self.assertEqual(error.message_args, {'minutes': minutes}, interval)
            self.assertEqual(error.status, 'unavailable')
            record = p.service('meta', error.status, message_id=str(error),
                               message_args=error.message_args)
            self.assertEqual(record['message'],
                             i18n._f(i18n._(DEFERRED), minutes=minutes), interval)

    def test_the_service_note_is_composed_from_identifiers(self):
        payload = {'subs_tier_name': 'Muse Code Everyday Usage',
                   'subs_usage': {'window': {'used_percent': 140}}}
        args = p.meta_note_args(payload)
        note = p.meta_message(payload)
        self.assertEqual(note, i18n._f(i18n._(p.META_NOTE_ID), **args))
        self.assertIn(i18n._f(i18n._(PLAN), plan='Muse Code Everyday Usage'), note)
        self.assertIn(i18n._f(i18n._(NOTE_PERCENT), percent='140'), note)
        self.assertIn('Muse Code Everyday Usage', note)
        self.assertIn('140%', note)

    def test_the_note_without_optional_parts_is_the_bare_identifier(self):
        args = p.meta_note_args({})
        self.assertEqual(args, {'details': ''})
        self.assertEqual(p.meta_message({}), i18n._f(i18n._(p.META_NOTE_ID), details=''))

    def test_the_note_in_the_cache_follows_the_language_without_recollecting(self):
        payload = {'subs_tier_name': 'Muse Code Everyday Usage', 'subs_usage': {}}
        args = p.meta_note_args(payload)
        record = p.service('meta', 'ok', message=p.meta_message(payload),
                           message_id=p.META_NOTE_ID, message_args=args)
        self.assertEqual(record['message_id'], p.META_NOTE_ID)
        self.assertEqual(record['message_args'], args)
        self.assertEqual(record['message'],
                         i18n._f(i18n._(p.META_NOTE_ID), **args))
        english()
        self.assertEqual(i18n.record_text(record),
                         i18n._f(i18n._(p.META_NOTE_ID), **args))


class CachedTextFallbackTests(ProviderTestCase):
    """Identificador ausente do catálogo volta ao texto gravado; presente, ele manda."""

    def test_a_label_identifier_missing_from_the_catalog_uses_the_saved_text(self):
        record = {'label_id': NOT_IN_CATALOG, 'label_args': {},
                  'label': 'Rótulo gravado pela coleta antiga.'}
        self.assertEqual(i18n.record_text(record, 'label_id', 'label_args', 'label'),
                         'Rótulo gravado pela coleta antiga.')

    def test_a_label_identifier_in_the_catalog_beats_the_saved_text(self):
        record = {'label_id': UNAVAILABLE_BALANCE, 'label_args': {},
                  'label': 'Saldo de ontem, em outro idioma.'}
        self.assertEqual(i18n.record_text(record, 'label_id', 'label_args', 'label'),
                         i18n._(UNAVAILABLE_BALANCE))

    def test_the_composite_label_is_rewritten_in_the_language_in_force(self):
        """Reescrita inteira: nem o nome do balde nem as horas sobram no idioma da coleta."""
        metric = p.parse_codex({'rateLimitsByLimitId': {
            'codex': {'primary': {'usedPercent': 0, 'windowDurationMins': 300}},
            'other': {'limitName': 'Outro balde',
                      'secondary': {'usedPercent': 90, 'windowDurationMins': 10080}}}})[1]
        self.assertEqual(metric['label'], 'Outro balde · janela de 168 h')  # idioma da coleta
        i18n.activate('en')
        self.assertEqual(i18n.record_text(metric, 'label_id', 'label_args', 'label'),
                         i18n._f(i18n._(WINDOW_WITH_NAME), name='Outro balde', hours='168'))
        self.assertEqual(i18n.record_text(metric, 'label_id', 'label_args', 'label'),
                         'Outro balde · 168 h window')

    def test_arguments_are_not_reformatted_by_the_presentation(self):
        """Número já formatado na coleta fica no idioma em que foi formatado.

        É o motivo de o argumento ir cru: ``{hours}`` recebe o valor que a coleta escreveu, e quem
        formata o percentual exibido é a apresentação (``formatPercent`` no painel, ``i18n.percent``
        na janela) — não este caminho.
        """
        i18n.activate('pt_BR')
        metric = p.parse_meta({'subs_usage': {'window': {
            'used_percent': 3, 'window_duration_mins': 90}}})[0]
        self.assertEqual(metric['label_args'], {'hours': '1,5'})
        self.assertEqual(i18n.record_text(metric, 'label_id', 'label_args', 'label'),
                         'Janela de 1,5 h')


class CacheAndHistoryTests(ProviderTestCase):
    """Os caminhos de cache e de histórico continuam os mesmos — só o texto mudou de lugar."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'XDG_CACHE_HOME': self.tmp.name}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.identity = 'digest-da-conta'
        self.cache = Path(self.tmp.name) / 'cinnamon-ai-usage' / 'meta.json'

    def _write_good_reading(self):
        read_at = p.stamp()
        metrics = [p.metric('janela', label_id=i18n.N_(WINDOW_HOURS),
                            label_args={'hours': p.window_hours(300)}, kind='quota', percent=42)]
        p.quota_mark_attempt('meta', self.identity)
        p.quota_write_cache('meta', self.identity, read_at, metrics)
        return read_at, metrics

    def test_a_failure_is_recorded_with_the_identifier_and_the_reading_is_preserved(self):
        read_at, metrics = self._write_good_reading()
        p.quota_mark_failure('meta', self.identity, i18n.N_(CONNECTION_FAILED))
        data = json.loads(self.cache.read_text(encoding='utf-8'))
        self.assertEqual(data['attempt_status'], 'failure')
        self.assertEqual(data['attempt_message_id'], CONNECTION_FAILED)
        self.assertEqual(data['attempt_message'], i18n._(CONNECTION_FAILED))
        self.assertEqual(data['attempt_message_args'], {})
        self.assertEqual(data['read_at'], read_at)          # leitura boa preservada
        self.assertEqual(data['metrics'], metrics)          # valores crus, sem retraduzir
        self.assertEqual(data['identity'], self.identity)   # só o digest da conta

    def test_the_reused_reading_comes_back_with_its_identifier_and_arguments(self):
        read_at, metrics = self._write_good_reading()
        p.quota_mark_failure('meta', self.identity, i18n.N_(DEFERRED),
                             {'minutes': 15})
        cached = p.quota_reuse('meta', 900, self.identity)
        self.assertEqual(cached['read_at'], read_at)
        self.assertEqual(cached['metrics'], metrics)
        self.assertEqual(cached['failure_id'], DEFERRED)
        self.assertEqual(cached['failure_args'], {'minutes': 15})
        self.assertEqual(cached['failure'], i18n._f(i18n._(DEFERRED), minutes=15))
        service = p.quota_reused_service('meta', cached, 'fonte', self.identity)
        self.assertEqual(service['status'], 'stale')
        self.assertEqual(service['stale_reason'], 'failure')
        self.assertEqual(service['message_id'], DEFERRED)
        self.assertEqual(service['message_args'], {'minutes': 15})
        self.assertEqual(service['read_at'], read_at)
        self.assertEqual(service['metrics'], metrics)
        i18n.activate('en')
        self.assertEqual(i18n.record_text(service), i18n._f(i18n._(DEFERRED), minutes=15))

    def test_an_old_failure_cache_without_identifier_keeps_its_saved_text(self):
        read_at, metrics = self._write_good_reading()
        data = json.loads(self.cache.read_text(encoding='utf-8'))
        data.update(attempt_status='failure', attempt_message='Falha antiga, sem identificador.')
        data.pop('attempt_message_id', None)
        data.pop('attempt_message_args', None)
        self.cache.write_text(json.dumps(data), encoding='utf-8')
        cached = p.quota_reuse('meta', 900, self.identity)
        self.assertEqual(cached['failure'], 'Falha antiga, sem identificador.')
        self.assertIsNone(cached['failure_id'])
        self.assertEqual(cached['failure_args'], {})
        service = p.quota_reused_service('meta', cached, 'fonte', self.identity)
        self.assertNotIn('message_id', service)
        self.assertEqual(service['message'], 'Falha antiga, sem identificador.')
        self.assertEqual(service['read_at'], read_at)
        self.assertEqual(service['metrics'], metrics)

    def test_a_reused_reading_without_failure_is_not_stale(self):
        read_at, metrics = self._write_good_reading()
        cached = p.quota_reuse('meta', 900, self.identity)
        service = p.quota_reused_service('meta', cached, 'fonte', self.identity,
                                         message_id=i18n.N_('Reading reused.'))
        self.assertNotIn('stale_reason', service)
        self.assertEqual(service['message_id'], 'Reading reused.')
        self.assertEqual(service['read_at'], read_at)
        self.assertEqual(service['metrics'], metrics)

    def test_an_expired_interval_recollects_without_discarding_the_cache(self):
        """Intervalo vencido faz consultar de novo — e não apaga nem o carimbo nem a leitura."""
        read_at, metrics = self._write_good_reading()
        data = json.loads(self.cache.read_text(encoding='utf-8'))
        data['attempted_at'] = p.stamp(time.time() - 3600)      # tentativa de uma hora atrás
        self.cache.write_text(json.dumps(data), encoding='utf-8')
        self.assertIsNone(p.quota_reuse('meta', 900, self.identity))
        self.assertFalse(p.quota_attempt_recent('meta', 900, self.identity))
        self.assertEqual(json.loads(self.cache.read_text(encoding='utf-8')), data)
        self.assertEqual(data['read_at'], read_at)
        self.assertEqual(data['metrics'], metrics)

    def test_history_keeps_the_identifier_of_the_new_failure(self):
        previous = p.service('codex', 'ok', message_id=i18n.N_('No reading available; refresh to query.'),
                             metrics=[p.metric('a', label_id=i18n.N_('Quota'), kind='quota', percent=20)])
        previous['read_at'] = '2026-09-25T10:00:00Z'
        failure = p.collect_provider('grok', {})
        merged = c.merge_history(failure, previous)
        self.assertEqual(merged['status'], 'stale')
        self.assertEqual(merged['stale_reason'], 'failure')
        self.assertEqual(merged['read_at'], previous['read_at'])   # erro não é medição nova
        self.assertEqual(merged['metrics'], previous['metrics'])   # nada foi descartado
        self.assertEqual(merged['message_id'], failure['message_id'])
        self.assertEqual(merged['message'], failure['message'])
        self.assertEqual(merged['stale_reason'], 'failure')

    def test_a_language_change_does_not_invalidate_the_private_cache(self):
        read_at, metrics = self._write_good_reading()
        i18n.activate('en')
        cached = p.quota_reuse('meta', 900, self.identity)
        self.assertEqual(cached['read_at'], read_at)
        self.assertEqual(cached['metrics'], metrics)


class NativeSourceTests(ProviderTestCase):
    """Nenhuma prosa fora do catálogo no módulo convertido."""

    def test_every_accented_literal_of_the_module_is_a_catalog_entry(self):
        """Literal acentuado que não é msgid é prosa portuguesa escrita direto na tela.

        A checagem é contra o ``.mo`` — o artefato que o gettext do Python e o shell carregam —,
        e não contra uma lista mantida a mão.
        """
        catalog = i18n._load('pt_BR')
        self.assertIsNotNone(catalog, 'rode scripts/i18n.sh')
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, 'body', [])
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            if any(ord(char) > 127 for char in node.value):
                self.assertTrue(i18n._has_entry(catalog, node.value),
                                'literal acentuado fora do catálogo: %r' % node.value)

    def test_the_module_still_declares_its_contract_symbols(self):
        """A conversão não mexeu em nome de campo, identificador de métrica nem no serviço."""
        for name in ('SERVICES', 'META_NOTE_ID', 'CLAUDE_NOTE_ID', 'CLAUDE_WINDOWS',
                     'CLAUDE_FLAT_WINDOWS', 'QUOTA_FAILURE_MESSAGE', 'DIAGNOSTICS',
                     'META_PERCENT_FIELDS'):
            self.assertTrue(hasattr(p, name), name)
        self.assertEqual(sorted(p.DIAGNOSTICS), ['claude', 'meta'])
        self.assertEqual(p.SERVICES['meta'], 'Meta AI (Muse Code)')
        self.assertEqual(p.META_NOTE_ID,
                         'Application subscription; not API usage billing.{details}')
        self.assertEqual(len(p.CLAUDE_WINDOWS['session']), 4)  # id, msgid, argumentos, duração
        self.assertEqual(p.CLAUDE_WINDOWS['session'][0], 'janela')
        self.assertEqual(p.CLAUDE_WINDOWS['session'][3], 18000)


class FormattingTests(ProviderTestCase):
    """O número sai da tabela do idioma, não de um formato fixo."""

    def test_the_window_hours_follow_the_language(self):
        english()
        self.assertEqual(p.window_hours(300), '5')
        self.assertEqual(p.window_hours(60), '1')
        self.assertEqual(p.window_hours(90), '1.5')
        i18n.activate('pt_BR')
        self.assertEqual(p.window_hours(300), '5')
        self.assertEqual(p.window_hours(90), '1,5')

    def test_the_label_of_a_fractional_window_uses_the_language_separator(self):
        payload = {'subs_usage': {'window': {'used_percent': 3, 'window_duration_mins': 90}}}
        english()
        self.assertEqual(p.parse_meta(payload)[0]['label'],
                         i18n._f(i18n._(WINDOW_HOURS), hours='1.5'))
        i18n.activate('pt_BR')
        self.assertEqual(p.parse_meta(payload)[0]['label'],
                         i18n._f(i18n._(WINDOW_HOURS), hours='1,5'))
        self.assertEqual(i18n.record_text(p.parse_meta(payload)[0], 'label_id', 'label_args',
                                          'label'), 'Janela de 1,5 h')

    def test_the_reported_percentage_of_the_note_is_not_a_fixed_format(self):
        for code, expected in (('pt_BR', '100,5'), ('en', '100.5')):
            i18n.activate(code)
            note = p.meta_message({'subs_usage': {'window': {'used_percent': 100.5}}})
            self.assertEqual(note, i18n._f(i18n._(p.META_NOTE_ID),
                                           **p.meta_note_args({'subs_usage': {
                                               'window': {'used_percent': 100.5}},
                                               'subs_tier_name': ''})), code)
            self.assertIn(i18n._f(i18n._(NOTE_PERCENT), percent=expected), note, code)


if __name__ == '__main__':
    unittest.main()
