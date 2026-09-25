"""Offline regression tests: provider meaning, history, cache and secret isolation."""
import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import providers as p
import collector as c


class ProviderTests(unittest.TestCase):
    def test_codex_multiple_buckets_and_actual_windows(self):
        got = p.parse_codex({'rateLimitsByLimitId': {
            'codex': {'primary': {'usedPercent': 0, 'windowDurationMins': 300, 'resetsAt': 1790370000}},
            'other': {'limitName': 'Other', 'secondary': {'usedPercent': 90, 'windowDurationMins': 10080}}}})
        self.assertEqual([m['used_percent'] for m in got], [0, 90])
        self.assertEqual([m['window_seconds'] for m in got], [18000, 604800])
        self.assertEqual(got[0]['reset_at'], p.stamp(1790370000))
        self.assertIsNone(got[1]['reset_at'])

    def test_missing_quota_is_not_zero(self):
        self.assertEqual(p.parse_codex({'rateLimits': {'primary': {'usedPercent': None}}}), [])
        self.assertIsNone(p.metric('a', 'A', 'quota')['used_percent'])

    def test_nonfinite_and_boolean_are_not_numeric(self):
        for n in (True, float('nan'), 'Infinity', None, {}, 'secret'):
            self.assertIsNone(p.number(n))

    def test_openrouter_without_cap_is_only_spend(self):
        got = p.parse_openrouter({'data': {'limit': None, 'usage': 10, 'usage_monthly': 2}})
        self.assertEqual([m['kind'] for m in got], ['spend', 'spend'])

    def test_openrouter_cap_uses_remaining_not_lifetime_spend(self):
        got = p.parse_openrouter({'data': {'limit': 20, 'limit_remaining': 15, 'usage': 100}})
        self.assertEqual(got[0]['used_percent'], 25)

    def test_deepseek_balance_cannot_be_monthly_usage(self):
        got = p.parse_deepseek({'balance_infos': [{'currency': 'USD', 'total_balance': '12.40'}]})
        self.assertEqual(got[0]['value'], 12.4)
        self.assertEqual(got[0]['kind'], 'balance')
        self.assertIsNone(got[0]['used_percent'])

    def test_nous_rollover_is_not_invented_percentage(self):
        got = p.parse_nous({'subscription': {'monthly_credits': 20, 'rollover_credits': 10,
                'current_period_end': '2026-10-01T00:00:00Z'}, 'paid_service_access': {
                'total_usable_credits': 35, 'subscription_credits_remaining': 25, 'purchased_credits_remaining': 10}})
        self.assertEqual(len(got), 3)
        self.assertTrue(all(m['kind'] == 'balance' and m['used_percent'] is None for m in got))
        self.assertEqual(got[1]['reset_at'], '2026-10-01T00:00:00Z')

    def test_nous_equal_balances_are_one_line(self):
        got = p.parse_nous({'subscription': {'current_period_end': '2026-10-22T21:17:20Z'},
                            'paid_service_access': {'total_usable_credits': 21.09,
                                                    'subscription_credits_remaining': 21.09,
                                                    'purchased_credits_remaining': 0}})
        self.assertEqual([m['id'] for m in got], ['total_usable_credits'])
        self.assertEqual(got[0]['label'], 'Saldo total disponível')
        self.assertEqual(got[0]['reset_at'], '2026-10-22T21:17:20Z')

    def test_go_observed_response_shape(self):
        got = p.parse_go({'usage': {'rolling': {'percent': 0, 'status': 'ok', 'resetsAt': '2026-10-01T00:00:00Z'},
                                  'weekly': {'percent': 30}, 'monthly': {'percent': None}}})
        self.assertEqual([m['used_percent'] for m in got], [0, 30])
        self.assertIsNone(got[0]['window_seconds'])
        self.assertEqual(p.parse_go({'unexpected': 5}), [])

    def test_antigravity_models_are_not_time_windows(self):
        got = p.parse_antigravity({'userStatus': {'cascadeModelConfigData': {'clientModelConfigs': [
            {'modelLabel': 'Model A', 'quotaInfo': {'remainingFraction': .25}},
            {'modelLabel': 'Model B', 'quotaInfo': {'remainingFraction': 0, 'resetTime': '2026-10-01T00:00:00Z'}},
            {'modelLabel': 'Unknown', 'quotaInfo': {}}]}}})
        self.assertEqual([m['used_percent'] for m in got], [75, 100])
        self.assertTrue(all(m['window_seconds'] is None for m in got))
        self.assertIsNone(got[0]['reset_at'])

    def test_antigravity_plan_credits_and_model_labels(self):
        got = p.parse_antigravity({'userStatus': {
            'planStatus': {'planInfo': {'planName': 'Pro', 'monthlyPromptCredits': 50000,
                                        'monthlyFlowCredits': 150000},
                           'availablePromptCredits': 500, 'availableFlowCredits': 300},
            'cascadeModelConfigData': {'clientModelConfigs': [
                {'label': 'Claude Sonnet 4.6 (Thinking)', 'quotaInfo': {'remainingFraction': 1,
                                                                        'resetTime': '2026-10-02T23:25:43Z'}},
                {'label': 'Gemini 3.1 Pro (High)', 'quotaInfo': {'resetTime': '2026-09-29T20:33:52Z'}}]}}})
        self.assertEqual([m['id'] for m in got], ['prompt', 'flow', 'model:Claude Sonnet 4.6 (Thinking)'])
        self.assertEqual([m['used_percent'] for m in got], [99, 99.8, 0])
        self.assertEqual(got[2]['label'], 'Claude Sonnet 4.6 (Thinking)')
        self.assertNotIn('Modelo', json.dumps(got, ensure_ascii=False))

    def test_exception_details_never_escape_provider(self):
        with patch.object(p, 'deepseek', side_effect=RuntimeError('Bearer TOP_SECRET')):
            result = p.collect_provider('deepseek', {})
        self.assertNotIn('TOP_SECRET', json.dumps(result))
        self.assertEqual(result['status'], 'error')

    def test_credentials_file_is_chosen_by_config_not_hardcoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home/'.config/agentes').mkdir(parents=True)
            (home/'.config/agentes/credenciais.env').write_text('KEY=do-caminho-antigo\n')
            custom = home/'secrets.env'
            custom.write_text('KEY="$(touch should-not-exist)"\nOTHER=private\n')
            with patch.object(Path, 'home', return_value=home):
                # O programa não conhece o caminho antigo: sem configuração, nada é lido.
                self.assertEqual(p.credentials.resolve(['KEY']), {})
                config = {'credentials_path': str(custom)}
                self.assertEqual(p.credentials.resolve(['KEY'], config), {'KEY': '$(touch should-not-exist)'})
            self.assertFalse((home/'should-not-exist').exists())

    def test_credentials_order_keyring_then_file_then_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'secrets.env'
            path.write_text('ALFA=do-arquivo\nBETA=do-arquivo\n')
            config = {'credentials_path': str(path)}
            with patch.object(p.credentials, 'keyring_get', side_effect=lambda n: 'do-cofre' if n == 'ALFA' else None), \
                 patch.dict(os.environ, {'BETA': 'do-ambiente', 'GAMA': 'do-ambiente'}, clear=False):
                got = p.credentials.resolve(['ALFA', 'BETA', 'GAMA'], config)
            self.assertEqual(got, {'ALFA': 'do-cofre', 'BETA': 'do-arquivo', 'GAMA': 'do-ambiente'})

    def test_missing_credential_is_unconfigured_not_zero(self):
        with patch.object(p.credentials, 'resolve', return_value={}):
            with self.assertRaises(p.Unavailable) as raised:
                p.require_key('OPENROUTER_API_KEY', {})
        self.assertEqual(raised.exception.status, 'unconfigured')

    def test_oauth_token_is_found_at_any_json_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'auth.json'
            path.write_text(json.dumps({'providers': {'nous': {'access_token': 'token-de-teste'}}}))
            self.assertEqual(p.credentials.oauth_token('nous', {'token_files': {'nous': str(path)}}),
                             'token-de-teste')
            self.assertIsNone(p.credentials.oauth_token('nous', {}))
            path.write_text('{broken')
            self.assertIsNone(p.credentials.oauth_token('nous', {'token_files': {'nous': str(path)}}))

    def test_no_redirect_with_auth(self):
        with self.assertRaises(p.Unavailable):
            p.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid')


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.old = p.service('codex', metrics=[p.metric('a', 'Quota', 'quota', percent=20,
                                                       reset='2026-10-01T00:00:00Z')], identity='account-a')
        self.old['read_at'] = '2026-09-25T10:00:00Z'
        self.new = copy.deepcopy(self.old)
        self.new['read_at'] = '2026-09-25T10:02:00Z'

    def test_polling_does_not_count_as_use(self):
        self.assertIsNone(c.merge_history(self.new, self.old)['last_used_at'])

    def test_positive_quota_change_counts(self):
        self.new['metrics'][0]['used_percent'] = 21
        result = c.merge_history(self.new, self.old)
        self.assertEqual(result['last_used_at'], self.new['read_at'])
        self.assertEqual(result['recency_basis'], 'observed_change')

    def test_reset_and_identity_changes_do_not_count(self):
        self.new['metrics'][0]['used_percent'] = 90
        self.new['metrics'][0]['reset_at'] = '2026-10-02T00:00:00Z'
        self.assertFalse(c.detected_change(self.old, self.new))
        self.new['metrics'][0]['reset_at'] = self.old['metrics'][0]['reset_at']
        self.new['_identity'] = 'other'
        self.assertFalse(c.detected_change(self.old, self.new))

    def test_balance_decrease_counts_but_topup_does_not(self):
        self.old['metrics'] = [p.metric('b', 'Balance', 'balance', value=10, currency='USD')]
        self.new['metrics'] = [p.metric('b', 'Balance', 'balance', value=9, currency='USD')]
        self.assertTrue(c.detected_change(self.old, self.new))
        self.new['metrics'][0]['value'] = 11
        self.assertFalse(c.detected_change(self.old, self.new))

    def test_failed_read_preserves_data_and_timestamp(self):
        got = c.merge_history(p.service('codex', 'error', 'Timeout'), self.old)
        self.assertEqual(got['status'], 'stale')
        self.assertEqual(got['read_at'], self.old['read_at'])
        self.assertEqual(got['metrics'], self.old['metrics'])
        self.assertIsNone(got['last_used_at'])

    def test_disabled_does_not_retain_reading(self):
        got = c.merge_history(p.service('codex', 'disabled'), self.old)
        self.assertEqual(got['status'], 'disabled')
        self.assertEqual(got['metrics'], [])

    def test_stale_baseline_allows_later_change(self):
        old = c.merge_history(p.service('codex', 'error'), self.old)
        self.new['metrics'][0]['used_percent'] = 21
        self.assertIsNotNone(c.merge_history(self.new, old)['last_used_at'])

    def test_public_output_removes_private_identity(self):
        result = c.public({'services': [self.old]})
        self.assertNotIn('_identity', result['services'][0])
        self.assertIn('_identity', self.old)


class CacheTests(unittest.TestCase):
    def test_atomic_cache_mode_and_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'snapshot.json'
            c.save_atomic(path, c.demo())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(c.load_snapshot(path)['schema_version'], 1)
            path.write_text('{broken')
            self.assertIsNone(c.load_snapshot(path)['generated_at'])

    def test_demo_never_writes_cache(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, XDG_CACHE_HOME=d)
            result = subprocess.run([sys.executable, c.__file__, 'demo'], capture_output=True, env=env, check=True)
            self.assertTrue(json.loads(result.stdout)['demo'])
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_all_disabled_collection_has_no_workers(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d)/'cache'; config = Path(d)/'config.json'
            config.write_text(json.dumps({'enabled': {k: False for k in p.SERVICES}}))
            with patch.object(c, 'paths', return_value=(cache, config)), patch.object(c.subprocess, 'Popen') as spawn:
                got = c.collect(True)
                spawn.assert_not_called()
            self.assertEqual(len(got['services']), 7)
            self.assertTrue(all(s['status']=='disabled' for s in got['services']))

    def test_valid_ttl_avoids_spawning(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d)/'cache'; cache.mkdir()
            c.save_atomic(cache/'snapshot.json', c.demo())
            with patch.object(c, 'paths', return_value=(cache, Path(d)/'config.json')), patch.object(c.subprocess, 'Popen') as spawn:
                c.collect(False)
                spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
