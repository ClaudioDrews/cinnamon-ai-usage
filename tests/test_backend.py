"""Offline regression tests: provider meaning, history, cache and secret isolation."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
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

    def _grok_payload(self, total, changes=()):
        return {'total': {'val': total},
                'changes': [{'changeOrigin': origem, 'amount': {'val': valor}}
                            for origem, valor in changes]}

    def test_grok_balance_is_the_available_credit_not_the_ledger_sign(self):
        # Forma observada na resposta da xAI: a recarga entra negativa no razão e o total fica
        # negativo, de modo que o crédito disponível é o módulo do total.
        metrics = p.parse_grok(self._grok_payload('-1000', [('PURCHASE', '-1000')]))
        self.assertEqual(metrics[0]['value'], 10.0)
        self.assertEqual(metrics[0]['currency'], 'USD')
        self.assertIsNone(metrics[0]['used_percent'])
        self.assertEqual(len(metrics), 1)  # Sem consumo, sem barra em zero.

    def test_grok_ledger_with_usage_gives_percentage_of_granted_credits(self):
        metrics = p.parse_grok(self._grok_payload('-1500', [('PURCHASE', '-2000'), ('USAGE', '500')]))
        self.assertEqual(metrics[0]['value'], 15.0)
        self.assertEqual(metrics[1]['label'], 'Créditos pré-pagos usados')
        self.assertEqual(metrics[1]['used_percent'], 25.0)
        self.assertEqual(metrics[1]['value'], 5.0)

    def test_grok_needs_team_id_and_a_configured_key(self):
        with patch.object(p, 'request') as request:
            missing_team = p.collect_provider('grok', {'credentials_path': self._key_file()})
            self.assertEqual(missing_team['status'], 'unconfigured')
            # A mensagem cita o NOME da variável, nunca o valor lido do arquivo.
            self.assertNotIn('chave-do-arquivo', json.dumps(missing_team))
            request.assert_not_called()

    def _key_file(self, extra=''):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        path = Path(self._tmp.name)/'credenciais.env'
        path.write_text('XAI_MANAGEMENT_KEY="chave-do-arquivo"\n' + extra)
        return str(path)

    def test_grok_uses_key_from_configured_file(self):
        seen = {}
        with patch.object(p, 'request') as request:
            request.side_effect = lambda url, key, *a, **k: seen.update(url=url, key=key) or \
                self._grok_payload('-1000', [('PURCHASE', '-1000')])
            result = p.grok({'credentials_path': self._key_file(), 'grok': {'team_id': 'team-1'}})
        self.assertEqual(seen['key'], 'chave-do-arquivo')  # Nome alternativo aceito.
        self.assertEqual(seen['url'], 'https://management-api.x.ai/v1/billing/teams/team-1/prepaid/balance')
        self.assertEqual(result['metrics'][0]['value'], 10.0)

    def test_grok_team_id_can_come_with_the_credentials(self):
        seen = {}
        with patch.object(p, 'request') as request:
            request.side_effect = lambda url, *a, **k: seen.update(url=url) or self._grok_payload('-1000')
            result = p.grok({'credentials_path': self._key_file('XAI_TEAM_ID="team-do-arquivo"\n')})
        self.assertIn('/teams/team-do-arquivo/prepaid/balance', seen['url'])
        self.assertEqual(result['status'], 'ok')

    def test_grok_rejects_team_id_with_path_characters(self):
        with patch.object(p, 'request') as request:
            result = p.collect_provider('grok', {'credentials_path': self._key_file('XAI_TEAM_ID="../outro"\n')})
        self.assertEqual(result['status'], 'unconfigured')
        request.assert_not_called()

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

    def _meta_payload(self, window=3, weekly=1, minutes=300):
        return {'subs_tier_name': 'Muse Code Everyday Usage',
                'subs_usage': {'window': {'used_percent': window, 'window_duration_mins': minutes,
                                          'resets_at': 1790443036},
                               'weekly': {'used_percent': weekly, 'resets_at': 1790553600},
                               'tier': '27681393394859588'},
                'api_key': 'nunca-deve-sair', 'user_email': 'pessoa@exemplo.invalid'}

    def _meta_tmp(self, name='meta-tmp'):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name

    def _meta_login(self, token='token-de-teste'):
        path = Path(self._meta_tmp())/'auth.json'
        path.write_text(json.dumps({'providers': {'meta': {'access_token': token, 'api_key': 'chave-x'}}}))
        return str(path)

    def test_meta_windows_come_from_the_subscription_snapshot(self):
        got = p.parse_meta(self._meta_payload())
        self.assertEqual([m['id'] for m in got], ['janela', 'semanal'])
        self.assertEqual([m['label'] for m in got], ['Janela de 5 h', 'Semana'])
        self.assertEqual([m['used_percent'] for m in got], [3, 1])
        self.assertEqual([m['window_seconds'] for m in got], [18000, 604800])
        self.assertTrue(all(m['kind'] == 'quota' for m in got))
        self.assertEqual(got[0]['reset_at'], p.stamp(1790443036))

    def test_meta_missing_percent_is_not_zero(self):
        self.assertEqual(p.parse_meta({}), [])
        self.assertEqual(p.parse_meta({'subs_usage': {'window': {'window_duration_mins': 300}}}), [])
        self.assertEqual(p.parse_meta({'subs_usage': {'window': {'used_percent': None}, 'weekly': {}}}), [])

    def test_meta_above_hundred_clamps_the_bar_and_keeps_the_real_number_in_the_note(self):
        payload = self._meta_payload(window=140)
        self.assertEqual(p.parse_meta(payload)[0]['used_percent'], 100)
        nota = p.meta_message(payload)
        self.assertIn('140%', nota)
        self.assertIn('Muse Code Everyday Usage', nota)

    def test_meta_note_never_leaks_credential_or_account(self):
        nota = p.meta_message(self._meta_payload())
        self.assertNotIn('nunca-deve-sair', nota)
        self.assertNotIn('exemplo.invalid', nota)

    def test_meta_without_login_is_unconfigured_and_does_not_call(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': self._meta_tmp()}, clear=False), \
             patch.object(p, 'request') as request:
            result = p.collect_provider('meta', {})
        self.assertEqual(result['status'], 'unconfigured')
        request.assert_not_called()

    def test_meta_posts_the_key_call_with_the_oauth_token(self):
        seen = {}
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self._meta_tmp()}, clear=False), \
             patch.object(p, 'request') as request:
            request.side_effect = lambda url, token=None, **k: seen.update(
                url=url, token=token, data=k.get('data'), headers=k.get('headers')) or self._meta_payload()
            result = p.meta({'token_files': {'meta': self._meta_login()}})
        self.assertEqual(seen['url'], p.META_KEY_URL)
        self.assertEqual(seen['token'], 'token-de-teste')
        self.assertEqual(seen['data'], {})  # corpo presente: POST, e não GET
        self.assertEqual(seen['headers'], {'x-client-id': 'tbh:tui'})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([m['used_percent'] for m in result['metrics']], [3, 1])

    def test_meta_reuses_the_reading_inside_the_interval(self):
        cache = self._meta_tmp()
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False), \
             patch.object(p, 'request') as request:
            request.side_effect = lambda *a, **k: self._meta_payload()
            config = {'token_files': {'meta': self._meta_login()}}
            first = p.meta(config)
            segunda = p.meta(config)
        self.assertEqual(request.call_count, 1)  # a segunda leitura não chamou de novo
        self.assertEqual(segunda['read_at'], first['read_at'])  # horário real, sem frescor inventado
        self.assertEqual([m['used_percent'] for m in segunda['metrics']], [3, 1])
        self.assertIn('reaproveitada', segunda['message'])
        arquivo = Path(cache)/'cinnamon-ai-usage'/'meta.json'
        self.assertEqual(stat.S_IMODE(arquivo.stat().st_mode), 0o600)
        texto = arquivo.read_text()
        self.assertIn(hashlib.sha256(b'token-de-teste').hexdigest(), texto)  # só o digest da conta
        self.assertNotIn('token-de-teste', texto)  # nunca o token

    def test_meta_expired_reading_is_refreshed(self):
        cache = self._meta_tmp()
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False):
            path = Path(cache)/'cinnamon-ai-usage'
            path.mkdir(parents=True)
            (path/'meta.json').write_text(json.dumps(
                {'read_at': '2026-09-26T00:00:00Z', 'identity': 'x', 'metrics': [{'id': 'janela'}]}))
            self.assertIsNone(p.meta_read_cache({}, 'x'))  # antiga: será consultada de novo

    def test_meta_login_path_follows_the_client_order(self):
        # Ordem lida no launcher do binário: token_files.meta > MUSE_AUTH_PATH > XDG.
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': '/xdg', 'MUSE_AUTH_PATH': '/custom/auth.json'},
                        clear=False):
            self.assertEqual(str(p.meta_login_path({})), '/custom/auth.json')
            self.assertEqual(str(p.meta_login_path({'token_files': {'meta': '~/outro.json'}})),
                             str(Path.home()/'outro.json'))
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': '/xdg'}, clear=False):
            os.environ.pop('MUSE_AUTH_PATH', None)
            self.assertEqual(str(p.meta_login_path({})), '/xdg/muse/auth.json')

    def test_meta_interval_has_floor_and_ceiling(self):
        self.assertEqual(p.meta_interval({}), 900)
        self.assertEqual(p.meta_interval({'meta': {'min_interval_seconds': 60}}), 300)
        self.assertEqual(p.meta_interval({'meta': {'min_interval_seconds': 999999}}), 86400)
        self.assertEqual(p.meta_interval({'meta': {'min_interval_seconds': 1800}}), 1800)

    def test_meta_http_failure_is_error_without_inventing_zero(self):
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self._meta_tmp()}, clear=False), \
             patch.object(p, 'request', side_effect=p.Unavailable('Credencial recusada.', 'error')):
            result = p.collect_provider('meta', {'token_files': {'meta': self._meta_login()}})
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['metrics'], [])


class ClaudeTests(unittest.TestCase):
    """Conector do Claude Code: rotas, formas de resposta e degradação sem conta real."""

    def _claude_tmp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name

    def _claude_login(self, token='token-de-teste', expires_at=None):
        path = Path(self._claude_tmp())/'.credentials.json'
        path.write_text(json.dumps({'claudeAiOauth': {
            'accessToken': token, 'refreshToken': 'nunca-deve-sair',
            'expiresAt': expires_at if expires_at else int((time.time() + 3600) * 1000),
            'subscriptionType': 'max', 'rateLimitTier': 'default_claude_max_5x'}}))
        return str(path)

    def _claude_payload(self, five=35.0, week=14.0):
        return {'five_hour': {'utilization': five, 'resets_at': '2026-09-26T22:00:00+00:00'},
                'seven_day': {'utilization': week, 'resets_at': '2026-10-02T20:00:00+00:00'},
                'seven_day_sonnet': None, 'seven_day_opus': None,
                'extra_usage': {'is_enabled': True, 'used_credits': 0.0},
                'access_token': 'nunca-deve-sair'}

    def _claude_limits_payload(self):
        return {'limits': [
            {'kind': 'session', 'percent': 35.0, 'resets_at': '2026-09-26T22:00:00+00:00'},
            {'kind': 'weekly_all', 'percent': 14.0, 'resets_at': '2026-10-02T20:00:00+00:00'},
            {'kind': 'weekly_scoped', 'percent': 39.0, 'scope': {'model': {'display_name': 'Sonnet'}}},
            {'kind': 'weekly_scoped', 'percent': 10.0, 'scope': {'model': {}}},
            {'kind': 'iguana_necktie', 'percent': 99.0}]}

    def test_claude_flat_objects_give_the_two_windows(self):
        got = p.parse_claude(self._claude_payload())
        self.assertEqual([m['id'] for m in got], ['janela', 'semanal'])
        self.assertEqual([m['label'] for m in got], ['Janela de 5 h', 'Semana'])
        self.assertEqual([m['used_percent'] for m in got], [35.0, 14.0])
        self.assertEqual([m['window_seconds'] for m in got], [18000, 604800])
        self.assertTrue(all(m['kind'] == 'quota' for m in got))
        self.assertEqual(got[0]['reset_at'], '2026-09-26T22:00:00Z')

    def test_claude_structured_limits_are_read_and_unknown_kinds_ignored(self):
        got = p.parse_claude(self._claude_limits_payload())
        self.assertEqual([m['id'] for m in got], ['janela', 'semanal', 'semanal:Sonnet'])
        self.assertEqual([m['used_percent'] for m in got], [35.0, 14.0, 39.0])
        self.assertEqual(got[2]['label'], 'Semana · Sonnet')
        self.assertNotIn('iguana_necktie', [m['id'] for m in got])  # sem janela nem modelo

    def test_claude_missing_percent_is_not_zero(self):
        self.assertEqual(p.parse_claude({}), [])
        self.assertEqual(p.parse_claude({'five_hour': {'utilization': None}, 'seven_day': {}}), [])
        self.assertEqual(p.parse_claude({'limits': [{'kind': 'session'}, 'nada', None]}), [])

    def test_claude_percent_scale_is_used_as_reported_never_rescaled(self):
        # A escala relatada é 0–100; multiplicar por 100 um valor fracionário inventaria uso.
        self.assertEqual(p.parse_claude({'five_hour': {'utilization': 0.4}})[0]['used_percent'], 0.4)
        self.assertEqual(p.parse_claude({'five_hour': {'utilization': 140}})[0]['used_percent'], 100)

    def test_claude_login_path_follows_documented_order(self):
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/contas/work'}, clear=False):
            self.assertEqual(str(p.claude_login_path({})), '/contas/work/.credentials.json')
            self.assertEqual(str(p.claude_login_path({'token_files': {'claude': '~/c.json'}})),
                             str(Path.home()/'c.json'))
            os.environ.pop('CLAUDE_CONFIG_DIR', None)
            self.assertEqual(str(p.claude_login_path({})),
                             str(Path.home()/'.claude'/'.credentials.json'))

    def test_claude_without_login_is_unconfigured_and_does_not_call(self):
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': self._claude_tmp()}, clear=False), \
             patch.object(p, 'request') as request:
            result = p.collect_provider('claude', {})
        self.assertEqual(result['status'], 'unconfigured')
        self.assertEqual(result['metrics'], [])
        request.assert_not_called()

    def test_claude_expired_token_warns_without_calling(self):
        vencido = self._claude_login(expires_at=int((time.time() - 60) * 1000))
        with patch.object(p, 'request') as request:
            result = p.collect_provider('claude', {'token_files': {'claude': vencido}})
        self.assertEqual(result['status'], 'unconfigured')
        self.assertIn('expirado', result['message'])
        request.assert_not_called()  # o applet não renova credencial

    def test_claude_reads_the_usage_route_with_the_beta_header_and_no_body(self):
        seen = {}
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self._claude_tmp()}, clear=False), \
             patch.object(p, 'request') as request:
            request.side_effect = lambda url, token=None, **k: seen.update(
                url=url, token=token, data=k.get('data'), headers=k.get('headers')) or self._claude_payload()
            result = p.claude({'token_files': {'claude': self._claude_login()}})
        self.assertEqual(seen['url'], p.CLAUDE_USAGE_URL)
        self.assertEqual(seen['token'], 'token-de-teste')
        self.assertEqual(seen['headers'], {'anthropic-beta': 'oauth-2025-04-20'})
        self.assertIsNone(seen['data'])  # GET: nenhuma requisição de inferência
        self.assertNotIn('messages', seen['url'])
        self.assertEqual([m['used_percent'] for m in result['metrics']], [35.0, 14.0])
        self.assertIn('não verificado', result['source'])

    def test_claude_reuses_the_reading_and_the_cache_keeps_only_the_digest(self):
        cache = self._claude_tmp()
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False), \
             patch.object(p, 'request') as request:
            request.side_effect = lambda *a, **k: self._claude_payload()
            config = {'token_files': {'claude': self._claude_login()}}
            first = p.claude(config)
            segunda = p.claude(config)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(segunda['read_at'], first['read_at'])
        self.assertIn('reaproveitada', segunda['message'])
        arquivo = Path(cache)/'cinnamon-ai-usage'/'claude.json'
        self.assertEqual(stat.S_IMODE(arquivo.stat().st_mode), 0o600)
        texto = arquivo.read_text()
        self.assertIn(hashlib.sha256(b'token-de-teste').hexdigest(), texto)
        self.assertNotIn('token-de-teste', texto)

    def test_claude_interval_has_floor_and_ceiling(self):
        self.assertEqual(p.claude_interval({}), 300)
        self.assertEqual(p.claude_interval({'claude': {'min_interval_seconds': 10}}), 120)
        self.assertEqual(p.claude_interval({'claude': {'min_interval_seconds': 1900}}), 1900)

    def test_claude_unrecognized_response_asks_for_the_diagnostic(self):
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self._claude_tmp()}, clear=False), \
             patch.object(p, 'request', side_effect=lambda *a, **k: {'limits': [{'kind': 'novo'}]}):
            result = p.collect_provider('claude', {'token_files': {'claude': self._claude_login()}})
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('diag claude', result['message'])

    def test_claude_http_failure_is_error_without_inventing_zero(self):
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self._claude_tmp()}, clear=False), \
             patch.object(p, 'request', side_effect=p.Unavailable('Credencial recusada.', 'error')):
            result = p.collect_provider('claude', {'token_files': {'claude': self._claude_login()}})
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['metrics'], [])

    def test_claude_note_never_leaks_credential_or_account(self):
        nota = p.claude_message(self._claude_payload(), {'subscriptionType': 'max'})
        self.assertNotIn('nunca-deve-sair', nota)
        self.assertIn('Plano: max', nota)

    def test_claude_diagnostic_reports_structure_without_values(self):
        login = self._claude_login()
        with patch.object(p, 'request', side_effect=lambda *a, **k: self._claude_payload()):
            report = p.claude_diag({'token_files': {'claude': login}})
        texto = json.dumps(report, ensure_ascii=False)
        self.assertEqual(report['consulta'], 'ok')
        self.assertEqual(report['credencial'], 'encontrada')
        self.assertEqual(report['janelas_reconhecidas'], ['janela', 'semanal'])
        self.assertIn('número entre 1 e 100', texto)  # faixa, não o valor
        self.assertNotIn('nunca-deve-sair', texto)
        self.assertNotIn('35', texto)
        self.assertNotIn(login, texto)  # nenhum caminho da máquina
        self.assertEqual(report['campos_do_login'],
                         ['accessToken', 'expiresAt', 'rateLimitTier', 'refreshToken', 'subscriptionType'])

    def test_diagnose_is_absent_for_services_without_one(self):
        self.assertEqual(p.diagnose('deepseek', {}),
                         {'diagnostico': 'não há diagnóstico para este serviço'})


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


class CredentialFileTests(unittest.TestCase):
    """Arquivo NOME=VALOR: valor sem aspas é literal, e o descartado vem com motivo."""

    def test_hash_inside_an_unquoted_value_survives(self):
        # Chave de API com '#' era cortada em silêncio pelo leitor anterior.
        self.assertEqual(p.credentials.parse_assignments('KEY=sk-abc#def\n'),
                         {'KEY': 'sk-abc#def'})

    def test_comment_still_needs_whitespace_before_the_hash(self):
        self.assertEqual(p.credentials.parse_assignments('KEY=valor  # nota\n'), {'KEY': 'valor'})
        self.assertEqual(p.credentials.parse_assignments('# KEY=ignorado\n'), {})

    def test_spaces_and_apostrophes_are_kept_literally(self):
        self.assertEqual(p.credentials.parse_assignments('KEY=value with spaces\n'),
                         {'KEY': 'value with spaces'})
        self.assertEqual(p.credentials.parse_assignments("KEY=it's-a-token\n"),
                         {'KEY': "it's-a-token"})

    def test_quoted_values_follow_shell_rules(self):
        self.assertEqual(p.credentials.parse_assignments('KEY="com # hash"\n'),
                         {'KEY': 'com # hash'})
        self.assertEqual(p.credentials.parse_assignments("KEY='solto'\n"), {'KEY': 'solto'})
        self.assertEqual(p.credentials.parse_assignments('KEY="$(touch nao-deve-existir)"\n'),
                         {'KEY': '$(touch nao-deve-existir)'})  # sem shell, literal

    def test_discarded_lines_come_with_a_reason(self):
        motivos = []
        got = p.credentials.parse_assignments('KEY="sem-fecho\nOK=valor\n', motivos)
        self.assertEqual(got, {'OK': 'valor'})
        self.assertEqual(motivos, [('KEY', 'aspas não fechadas')])
        motivos.clear()
        p.credentials.parse_assignments('KEY="a" "b"\n', motivos)
        self.assertEqual(motivos, [('KEY', 'mais de um valor entre aspas')])

    def test_read_file_reports_discarded_lines_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'secrets.env'
            path.write_text('BOM=1\nRUIM="sem-fecho\n')
            motivos = []
            self.assertEqual(p.credentials.read_file(str(path), motivos), {'BOM': '1'})
            self.assertEqual(motivos, [('RUIM', 'aspas não fechadas')])
            self.assertEqual(p.credentials.read_file(str(Path(tmp)/'nao-existe'), motivos), {})


class DemoAndVersionTests(unittest.TestCase):
    """A demonstração não pode afirmar o que o serviço não mede, e a versão é uma só."""

    def test_demo_follows_each_connector_shape(self):
        por_id = {s['id']: s for s in c.demo()['services']}
        grok = por_id['grok']['metrics']
        self.assertIn('balance', [m['kind'] for m in grok])
        self.assertFalse([m for m in grok if m['window_seconds'] == 18000])  # não é pré-pago com 5 h
        self.assertEqual([m['label'] for m in por_id['opencode']['metrics']],
                         ['Janela móvel', 'Semana', 'Mês'])
        self.assertEqual(por_id['openrouter']['metrics'][0]['kind'], 'spend')
        for servico in c.demo()['services']:
            self.assertTrue(servico['metrics'], servico['id'])
            for metrica in servico['metrics']:
                if metrica['kind'] == 'quota':
                    self.assertIsNotNone(metrica['used_percent'])

    def test_version_matches_everywhere(self):
        raiz = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((raiz/'applet/metadata.json').read_text())['version'], p.VERSION)
        self.assertIn(p.VERSION, (raiz/'docs/validation.md').read_text())
        self.assertIn(p.VERSION, (raiz/'README.md').read_text())
        self.assertNotIn('0.1.0', (raiz/'backend/providers.py').read_text())


class _FakeProc:
    """Worker de mentira: parece vivo no poll e já morreu quando a limpeza tenta o sinal."""

    def __init__(self, payload):
        self.pid, self.returncode, self.stdout = 4242, 0, None
        self._payload = payload

    def communicate(self, timeout=None):
        return self._payload, b''

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


class HygieneTests(unittest.TestCase):
    """Higiene antes de publicar: TTL do read, corrida na limpeza, fuso e instalador."""

    def _snapshot(self, diretorio, read_at):
        cache = Path(diretorio)/'cinnamon-ai-usage'
        cache.mkdir(parents=True, exist_ok=True)
        (cache/'snapshot.json').write_text(json.dumps({
            'schema_version': 1, 'generated_at': p.stamp(),
            'services': [{'id': 'codex', 'label': 'Codex', 'status': 'ok', 'message': '',
                          'source': 'teste', 'read_at': read_at, 'last_used_at': None,
                          'recency_basis': 'unknown', 'metrics': []}]}))
        return cache

    def _config(self, diretorio, refresh_seconds):
        pasta = Path(diretorio)/'config'/'cinnamon-ai-usage'
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta/'config.json').write_text(json.dumps({'refresh_seconds': refresh_seconds}))

    def test_read_command_follows_the_configured_ttl(self):
        # Leitura de 10 min atrás: dentro de um TTL de 3600, fora de um de 30.
        with tempfile.TemporaryDirectory() as tmp:
            self._snapshot(tmp, p.stamp(time.time()-600))
            self._config(tmp, 3600)
            ambiente = {**os.environ, 'XDG_CACHE_HOME': tmp, 'XDG_CONFIG_HOME': str(Path(tmp)/'config')}

            def read():
                coletor = Path(__file__).resolve().parents[1]/'backend'/'collector.py'
                saida = subprocess.run([sys.executable, str(coletor), 'read'], capture_output=True,
                                       text=True, env=ambiente)
                return json.loads(saida.stdout)['services'][0]['status']

            self.assertEqual(read(), 'ok')
            self._config(tmp, 30)
            self.assertEqual(read(), 'stale')

    def test_cleanup_survives_a_worker_that_already_exited(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = json.dumps(p.service('codex', 'ok', '', 'teste', [])).encode()
            with patch.dict(os.environ, {'XDG_CACHE_HOME': tmp}, clear=False), \
                 patch.object(c.subprocess, 'Popen', side_effect=lambda *a, **k: _FakeProc(payload)), \
                 patch.object(c.os, 'killpg', side_effect=ProcessLookupError):
                resultado = c.collect(force=True)
            self.assertTrue(resultado['generated_at'].endswith('Z'))
            self.assertEqual([s['status'] for s in resultado['services'] if s['id'] == 'codex'], ['ok'])
            # Nada de "Falha ao ler configuração": a corrida no encerramento não é erro de leitura.
            self.assertNotIn('Falha ao ler configuração', json.dumps(resultado))

    def test_naive_timestamp_is_read_as_utc(self):
        # Antes a data sem fuso sumia em silêncio (o campo reset_at desaparecia).
        self.assertEqual(p.stamp('2026-09-26T10:00:00'), '2026-09-26T10:00:00Z')
        self.assertEqual(p.stamp('2026-09-26T10:00:00-03:00'), '2026-09-26T13:00:00Z')
        self.assertIsNone(p.stamp('ontem'))

    def test_install_leaves_no_phantom_applet_and_a_readable_tree(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import install
        with tempfile.TemporaryDirectory() as tmp:
            applets = Path(tmp)/'applets'
            alvo = install.install(str(applets))
            self.assertEqual(sorted(pasta.name for pasta in applets.iterdir()), [install.UUID])
            self.assertEqual(stat.S_IMODE(alvo.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE((alvo/'backend').stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE((alvo/'applet.js').stat().st_mode), 0o644)
            self.assertTrue((alvo/'backend/collector.py').is_file())
            self.assertTrue((alvo/'assets/robot-head-symbolic.svg').is_file())
            install.install(str(applets))  # segunda vez: a anterior vai para backup
            self.assertEqual(sorted(pasta.name for pasta in applets.iterdir()), [install.UUID])
            self.assertEqual(len(list((Path(tmp)/'ai-usage-backups').iterdir())), 1)


class LockNoticeTests(unittest.TestCase):
    """Trava ocupada é aviso, não falha: o applet precisa distinguir "pulei" de "falhei"."""

    def _cache_com_snapshot(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        raiz = Path(directory.name)/'cinnamon-ai-usage'
        raiz.mkdir(parents=True)
        antigo = {'schema_version': 1, 'generated_at': '2026-09-26T10:00:00Z', 'services': [
            {'id': 'codex', 'label': 'Codex', 'status': 'ok', 'message': '', 'source': 'teste',
             'read_at': '2026-09-26T10:00:00Z', 'last_used_at': None, 'recency_basis': 'unknown',
             'metrics': [{'id': 'primary', 'label': 'Janela de 5 h', 'kind': 'quota',
                          'used_percent': 42.0, 'value': None, 'currency': None,
                          'window_seconds': 18000, 'reset_at': None}]}]}
        (raiz/'snapshot.json').write_text(json.dumps(antigo))
        return directory.name, raiz, antigo

    def test_busy_lock_reports_the_skip_and_keeps_the_last_readings(self):
        cache, raiz, antigo = self._cache_com_snapshot()
        fd = os.open(raiz/'collect.lock', os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)  # como uma coleta em andamento
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False), \
             patch.object(c.subprocess, 'Popen') as popen:
            resultado = c.collect(force=True)
        self.assertIn('coleta em andamento', resultado['notice'])
        self.assertEqual(resultado['generated_at'], antigo['generated_at'])
        self.assertEqual(resultado['services'][0]['status'], 'stale')
        self.assertEqual(resultado['services'][0]['metrics'][0]['used_percent'], 42.0)
        popen.assert_not_called()  # nenhum provedor foi consultado

    def test_the_skip_notice_is_not_written_to_the_cache(self):
        # Aviso de coleta pulada é do momento, não estado: não pode virar conteúdo do cache.
        cache, raiz, _ = self._cache_com_snapshot()
        fd = os.open(raiz/'collect.lock', os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False):
            self.assertIn('notice', c.collect(force=True))
        self.assertNotIn('notice', json.loads((raiz/'snapshot.json').read_text()))

    def test_a_fresh_snapshot_carries_no_notice(self):
        # Caminho normal, sem disputa de trava: o aviso não deve aparecer por engano.
        cache, raiz, _ = self._cache_com_snapshot()
        (raiz/'snapshot.json').write_text(json.dumps(
            {'schema_version': 1, 'generated_at': c.stamp(), 'services': []}))
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False), \
             patch.object(c.subprocess, 'Popen') as popen:
            resultado = c.collect()
        self.assertNotIn('notice', resultado)
        popen.assert_not_called()


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
            self.assertEqual(len(got['services']), len(p.SERVICES))
            self.assertTrue(all(s['status']=='disabled' for s in got['services']))

    def test_valid_ttl_avoids_spawning(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d)/'cache'; cache.mkdir()
            c.save_atomic(cache/'snapshot.json', c.demo())
            with patch.object(c, 'paths', return_value=(cache, Path(d)/'config.json')), patch.object(c.subprocess, 'Popen') as spawn:
                c.collect(False)
                spawn.assert_not_called()


class SecondReviewTests(unittest.TestCase):
    """Segunda revisão: idade real, intervalo depois de falha, alias do cofre, aviso honesto."""

    def _tmp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name

    def _aged_service(self, id_, minutos=10):
        item = p.service(id_, 'ok', '', 'teste', [{
            'id': 'janela', 'label': 'Janela de 5 h', 'kind': 'quota', 'used_percent': 90.0,
            'value': None, 'currency': None, 'window_seconds': 18000, 'reset_at': None}])
        item['read_at'] = p.stamp(time.time() - minutos*60)
        return item

    def test_collection_does_not_present_an_old_reading_as_current(self):
        # Leitura de dez minutos atrás com TTL de dois: a saída da coleta precisa dar o mesmo
        # veredito que o `read` — antes ela saía 'ok' e a cota antiga coloria o robô.
        with tempfile.TemporaryDirectory() as tmp:
            def fake(*args, **_kwargs):
                return _FakeProc(json.dumps(self._aged_service(args[0][-1])).encode())
            with patch.dict(os.environ, {'XDG_CACHE_HOME': tmp}, clear=False), \
                 patch.object(c.subprocess, 'Popen', side_effect=fake):
                resultado = c.collect(force=True)
            meta = [s for s in resultado['services'] if s['id'] == 'meta'][0]
            self.assertEqual((meta['status'], meta['stale_reason']), ('stale', 'pending'))
            self.assertEqual(meta['metrics'][0]['used_percent'], 90.0)  # valor real preservado
            salvos = {s['id']: s for s in json.loads(
                (Path(tmp)/'cinnamon-ai-usage'/'snapshot.json').read_text())['services']}
            self.assertEqual(salvos['meta']['status'], 'ok')  # o cache guarda o estado cru
            self.assertEqual(c.stale_read({'services': [salvos['meta']]})['services'][0]['status'],
                             'stale')  # e o mesmo snapshot lido depois dá o mesmo veredito

    def test_a_failed_refresh_keeps_the_data_and_names_the_failure(self):
        anterior = self._aged_service('meta')
        falha = p.service('meta', 'error', 'Credencial recusada.', 'teste', [])
        resultado = c.merge_history(falha, anterior)
        self.assertEqual(resultado['status'], 'stale')
        self.assertEqual(resultado['stale_reason'], 'failure')
        self.assertEqual(resultado['read_at'], anterior['read_at'])  # erro não é medição nova

    def test_the_warning_does_not_claim_failure_when_only_the_interval_lapsed(self):
        pendente = {'status': 'stale', 'stale_reason': 'pending',
                    'message': 'Última leitura disponível; atualização pendente.'}
        self.assertNotIn('falhou', c.stale_warning(pendente))
        falhou = {'status': 'stale', 'stale_reason': 'failure', 'message': 'HTTP 429'}
        self.assertIn('falhou', c.stale_warning(falhou))
        # Snapshot antigo, sem o campo estruturado: a mensagem do coletor decide.
        self.assertNotIn('falhou', c.stale_warning(
            {'status': 'stale', 'message': 'Última leitura disponível; atualização pendente.'}))

    def _meta_login(self, token='token-de-teste'):
        path = Path(self._tmp())/'auth.json'
        path.write_text(json.dumps({'providers': {'meta': {'access_token': token}}}))
        return str(path)

    def test_a_failed_attempt_holds_the_minimum_interval(self):
        # Três tentativas seguidas não podem virar três chamadas: com HTTP 429 a coleta
        # automática repetia a consulta a cada dois minutos e agravava o bloqueio.
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self._tmp()}, clear=False), \
             patch.object(p, 'request', side_effect=p.Unavailable('HTTP 429', 'error')) as request:
            config = {'token_files': {'meta': self._meta_login()}}
            primeira = p.collect_provider('meta', config)
            segunda = p.collect_provider('meta', config)
            terceira = p.collect_provider('meta', config)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(primeira['status'], 'error')
        for depois in (segunda, terceira):
            self.assertEqual(depois['status'], 'unavailable')
            self.assertIn('Consulta adiada', depois['message'])

    def test_a_failed_attempt_holds_the_interval_for_claude_too(self):
        with patch.dict(os.environ, {'XDG_CACHE_HOME': self._tmp()}, clear=False), \
             patch.object(p, 'request', side_effect=p.Unavailable('HTTP 429', 'error')) as request:
            path = Path(self._tmp())/'.credentials.json'
            path.write_text(json.dumps({'claudeAiOauth': {
                'accessToken': 'token-de-teste',
                'expiresAt': int((time.time() + 3600) * 1000)}}))
            config = {'token_files': {'claude': str(path)}}
            p.collect_provider('claude', config)
            p.collect_provider('claude', config)
        self.assertEqual(request.call_count, 1)

    def test_an_old_snapshot_still_reads_its_interval_from_the_reading(self):
        # Cache escrito antes do campo `attempted_at`: continua valendo pelo horário da leitura.
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'XDG_CACHE_HOME': tmp}, clear=False):
                raiz = Path(tmp)/'cinnamon-ai-usage'
                raiz.mkdir(parents=True)
                (raiz/'meta.json').write_text(json.dumps(
                    {'read_at': p.stamp(), 'identity': 'x', 'metrics': [{'id': 'janela'}]}))
                self.assertIsNotNone(p.quota_read_cache('meta', 900, 'x'))
                self.assertTrue(p.quota_attempt_recent('meta', 900, 'x'))


class CredentialPrecedenceTests(unittest.TestCase):
    """Cofre vence o arquivo mesmo gravado sob o nome alternativo (revisão: alias vencia)."""

    def test_the_window_saves_the_variable_the_backend_prefers(self):
        # Gravar num alias fazia a chave recém-salva perder para a credencial antiga do arquivo.
        fonte = (Path(__file__).resolve().parents[1]/'backend'/'credentials_window.py').read_text()
        pares = re.findall(r'\("(\w+)", "([^"]+)", "([A-Z_]+)"', fonte)
        self.assertTrue(pares)
        for servico, _rotulo, variavel in pares:
            self.assertIn(servico, p.credentials.SERVICE_KEYS)
            self.assertEqual(variavel, p.credentials.SERVICE_KEYS[servico][0], servico)

    def test_the_keyring_wins_over_an_old_alias_in_the_file(self):
        limpo = {k: v for k, v in os.environ.items()
                 if k not in ('XAI_MANAGEMENT_API_KEY', 'XAI_MANAGEMENT_KEY')}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, limpo, clear=True):
            arquivo = Path(tmp)/'secrets.env'
            arquivo.write_text('XAI_MANAGEMENT_API_KEY=chave-velha\n')
            config = {'credentials_path': str(arquivo)}
            cofre = {'XAI_MANAGEMENT_KEY': 'chave-nova'}
            with patch.object(p.credentials, 'keyring_get',
                              side_effect=lambda nome: cofre.get(nome)):
                self.assertEqual(p.credentials.service_value('grok', config), 'chave-nova')
                cofre.clear()
                self.assertEqual(p.credentials.service_value('grok', config), 'chave-velha')

    def test_the_origin_the_window_shows_matches_the_value_the_backend_uses(self):
        # Onde a coleta lê o valor e onde a janela diz que ele está têm de ser o mesmo lugar:
        # com o cofre de um alias e o arquivo do nome preferido, a janela informava "do arquivo
        # indicado" enquanto a coleta usava a chave do cofre.
        limpo = {k: v for k, v in os.environ.items()
                 if k not in ('XAI_MANAGEMENT_API_KEY', 'XAI_MANAGEMENT_KEY')}
        nomes = ('XAI_MANAGEMENT_API_KEY', 'XAI_MANAGEMENT_KEY')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, limpo, clear=True):
            arquivo = Path(tmp)/'secrets.env'
            arquivo.write_text('XAI_MANAGEMENT_API_KEY=chave-velha\n')
            config = {'credentials_path': str(arquivo)}
            cofre = {'XAI_MANAGEMENT_KEY': 'chave-nova'}
            with patch.object(p.credentials, 'keyring_get',
                              side_effect=lambda nome: cofre.get(nome)):
                self.assertEqual(p.credentials.service_value('grok', config), 'chave-nova')
                self.assertEqual(p.credentials.source_label(nomes, config), 'guardado no cofre')
                cofre.clear()
                self.assertEqual(p.credentials.service_value('grok', config), 'chave-velha')
                self.assertEqual(p.credentials.source_label(nomes, config), 'do arquivo indicado')
                os.environ['XAI_MANAGEMENT_KEY'] = 'chave-do-ambiente'
                self.assertEqual(p.credentials.source_label(nomes, {}), 'da variável de ambiente')
                del os.environ['XAI_MANAGEMENT_KEY']
            self.assertEqual(p.credentials.source_label(nomes, {}), 'não configurado')

    def test_the_window_takes_the_precedence_order_from_the_backend(self):
        # A interface não repete a regra: se ela reimplementasse a ordem, as duas voltariam a
        # discordar em silêncio.
        fonte = (Path(__file__).resolve().parents[1]/'backend'/'credentials_window.py').read_text()
        self.assertIn('credentials.source_label(', fonte)
        self.assertNotIn('keyring_get(', fonte)


class ThirdReviewTests(unittest.TestCase):
    """Terceira revisão: falha registrada não pode sumir na leitura reaproveitada."""

    def _tmp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return directory.name

    def _meta_login(self, token='token-de-teste'):
        path = Path(self._tmp())/'auth.json'
        path.write_text(json.dumps({'providers': {'meta': {'access_token': token}}}))
        return str(path)

    def _claude_login(self, token='token-de-teste'):
        path = Path(self._tmp())/'.credentials.json'
        path.write_text(json.dumps({'claudeAiOauth': {
            'accessToken': token, 'refreshToken': 'nunca-deve-sair',
            'expiresAt': int((time.time() + 3600) * 1000)}}))
        return str(path)

    def _meta_payload(self, janela=40, semana=20):
        agora = int(time.time())
        return {'subs_tier_name': 'Plano de exemplo', 'subs_usage': {
            'window': {'used_percent': janela, 'window_duration_mins': 300,
                       'resets_at': agora + 3600},
            'weekly': {'used_percent': semana, 'resets_at': agora + 86400}}}

    @staticmethod
    def _claude_payload():
        return {'five_hour': {'utilization': 35.0, 'resets_at': '2026-09-26T22:00:00+00:00'},
                'seven_day': {'utilization': 14.0, 'resets_at': '2026-10-02T20:00:00+00:00'}}

    def _vence_o_intervalo(self, cache_home, servico):
        """Envelhece o carimbo da tentativa para o intervalo mínimo deixar de valer.

        O intervalo é de 300 s (Claude) e 900 s (Meta); sem envelhecer o carimbo a consulta
        seguinte seria reaproveitada e a falha nem chegava a ser provocada.
        """
        caminho = Path(cache_home)/'cinnamon-ai-usage'/f'{servico}.json'
        guardado = json.loads(caminho.read_text())
        guardado['attempted_at'] = p.stamp(time.time() - 7200)
        caminho.write_text(json.dumps(guardado))
        return guardado

    def test_a_reused_reading_keeps_the_failure_of_the_last_attempt(self):
        # Sequência do revisor: leitura boa, HTTP 429 na seguinte e a rodada depois do 429 sem
        # chamada nova. Antes, o conector devolvia a leitura como `ok` e o coletor a reclassificava
        # como "atualização pendente" — a falha saía da tela sem o serviço ter voltado.
        cache = self._tmp()
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False):
            config = {'token_files': {'meta': self._meta_login()}}
            with patch.object(p, 'request', return_value=self._meta_payload()):
                primeira = p.collect_provider('meta', config)
            self.assertEqual(primeira['status'], 'ok')
            self._vence_o_intervalo(cache, 'meta')
            with patch.object(p, 'request', side_effect=p.Unavailable(
                    'Limite de consultas; aguarde a próxima atualização.', 'error')) as request:
                falha = p.collect_provider('meta', config)
                self.assertEqual(request.call_count, 1)
            self.assertEqual(falha['status'], 'error')

            with patch.object(p, 'request') as request:
                seguinte = p.collect_provider('meta', config)
                request.assert_not_called()  # o intervalo mínimo continua valendo
            self.assertEqual(seguinte['status'], 'stale')
            self.assertEqual(seguinte['stale_reason'], 'failure')
            self.assertEqual(seguinte['message'], falha['message'])
            self.assertEqual(seguinte['read_at'], primeira['read_at'])  # horário real
            self.assertEqual(seguinte['metrics'], primeira['metrics'])

            # O coletor não pode trocar o motivo: vencido o TTL, o veredito continua sendo falha.
            resultado = c.stale_read({'services': [c.merge_history(seguinte, primeira)]},
                                     ttl=2)['services'][0]
            self.assertEqual((resultado['status'], resultado['stale_reason']),
                             ('stale', 'failure'))
            self.assertIn('falhou', c.stale_warning(resultado))

    def test_the_claude_connector_records_the_same_way(self):
        cache = self._tmp()
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False):
            config = {'token_files': {'claude': self._claude_login()}}
            with patch.object(p, 'request', return_value=self._claude_payload()):
                primeira = p.collect_provider('claude', config)
            self.assertEqual(primeira['status'], 'ok')
            self._vence_o_intervalo(cache, 'claude')
            # Resposta sem as janelas esperadas também é tentativa falha registrada.
            with patch.object(p, 'request', return_value={'limits': [{'kind': 'novo'}]}):
                falha = p.collect_provider('claude', config)
            self.assertEqual(falha['status'], 'unavailable')
            with patch.object(p, 'request') as request:
                seguinte = p.collect_provider('claude', config)
                request.assert_not_called()
            self.assertEqual(seguinte['status'], 'stale')
            self.assertEqual(seguinte['stale_reason'], 'failure')
            self.assertEqual(seguinte['metrics'], primeira['metrics'])

    def test_a_service_that_answers_again_leaves_the_failure_behind(self):
        cache = self._tmp()
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False):
            config = {'token_files': {'meta': self._meta_login()}}
            with patch.object(p, 'request', return_value=self._meta_payload()):
                p.collect_provider('meta', config)
            self._vence_o_intervalo(cache, 'meta')
            with patch.object(p, 'request', side_effect=p.Unavailable(
                    'Limite de consultas; aguarde a próxima atualização.', 'error')):
                p.collect_provider('meta', config)
            self._vence_o_intervalo(cache, 'meta')
            with patch.object(p, 'request', return_value=self._meta_payload(58, 21)) as request:
                voltou = p.collect_provider('meta', config)
                self.assertEqual(request.call_count, 1)
            self.assertEqual(voltou['status'], 'ok')
            self.assertNotIn('stale_reason', voltou)
            with patch.object(p, 'request') as request:
                outra = p.collect_provider('meta', config)
                request.assert_not_called()
            self.assertEqual(outra['status'], 'ok')
            self.assertNotIn('stale_reason', outra)

    def test_a_first_failure_without_a_reading_is_still_deferred_not_ok(self):
        # Sem leitura anterior não há o que reaproveitar: a resposta honesta continua sendo a
        # consulta adiada, e o registro da falha não inventa valores.
        cache = self._tmp()
        with patch.dict(os.environ, {'XDG_CACHE_HOME': cache}, clear=False), \
             patch.object(p, 'request', side_effect=p.Unavailable('HTTP 429', 'error')) as request:
            config = {'token_files': {'meta': self._meta_login()}}
            p.collect_provider('meta', config)
            segunda = p.collect_provider('meta', config)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(segunda['status'], 'unavailable')
        self.assertEqual(segunda['metrics'], [])
        self.assertIn('Consulta adiada', segunda['message'])


if __name__ == '__main__':
    unittest.main()
