"""Isolamento dos geradores de evidência: o que eles afirmam tem de ser o que acontece.

Os dois harnesses de `docs/evidence/` afirmam que uma rodada não lê credencial desta máquina,
não consulta serviço nenhum e não executa binário local. Afirmar é fácil — a primeira versão
deles afirmava isso apontando só `XDG_CONFIG_HOME`/`XDG_CACHE_HOME` para um temporário, e o
dump versionado registrava o Codex como `ok` porque o `codex` instalado respondia.

O que se prova aqui:

- o dump é **invariante à máquina**: rodado com variáveis de credencial plantadas no ambiente e
  um `codex` de mentira no `PATH`, sai byte a byte igual à rodada limpa — e a linha de stderr
  diz o que foi substituído;
- a guarda **falha** quando alguém alcança o mundo real (rede, cofre, arquivo fora do sandbox);
- a fixture é o que a resolução de credencial usa, e ela recusa caminho fora do sandbox;
- todo caminho que o produto resolve fica dentro do sandbox da rodada.

Substituição que não é exercitada passa por isolamento sem provar nada, por isso `assert_clean`
exige que as fixtures tenham sido usadas.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import isolation  # noqa: E402  (o módulo de fixtures vive em tests/)

DUMP = ROOT / 'tests' / 'dump_visible_text.py'


def run_dump(extra_environment, language='pt_BR.UTF-8'):
    environment = dict(os.environ)
    environment.update({'LANGUAGE': language, 'LC_ALL': language, 'LC_MESSAGES': language})
    environment.update(extra_environment)
    process = subprocess.run([sys.executable, str(DUMP)], capture_output=True, text=True,
                             env=environment, cwd=str(ROOT), timeout=120)
    return process


class DumpInvarianceTests(unittest.TestCase):
    """O dump não pode depender da credencial, do ambiente nem dos binários desta máquina."""

    def test_the_dump_is_the_same_with_credentials_in_the_environment_and_a_fake_codex(self):
        """Ambiente com credenciais e um `codex` no PATH: o dump sai igual à rodada limpa.

        É o defeito que a revisão pegou, virado em prova: antes só o diretório de configuração
        era isolado, e a seção "sem configuração" do dump registrava o Codex como `ok` porque o
        binário da máquina foi executado. O `codex` de mentira fica no `PATH` da rodada suja: se
        a substituição do executável local cair, a mensagem do Codex muda e o dump deixa de ser
        igual ao da rodada limpa.
        """
        with tempfile.TemporaryDirectory() as binarios:
            falso = Path(binarios) / 'codex'
            falso.write_text('#!/bin/sh\necho \'{"id":1,"error":{"message":"falso"}}\'\n')
            falso.chmod(0o755)
            sujo = run_dump({'DEEPSEEK_API_KEY': 'chave-da-maquina',
                             'OPENROUTER_API_KEY': 'chave-da-maquina',
                             'XAI_MANAGEMENT_API_KEY': 'chave-da-maquina',
                             'XAI_TEAM_ID': 'time-da-maquina',
                             'NOUS_PORTAL_TOKEN': 'token-da-maquina',
                             'CODEX_HOME': binarios,
                             'PATH': binarios + os.pathsep + os.environ.get('PATH', '')})
        limpo = run_dump({})
        self.assertEqual(sujo.returncode, 0, sujo.stderr)
        self.assertEqual(limpo.returncode, 0, limpo.stderr)
        self.assertEqual(sujo.stdout, limpo.stdout,
                         'o dump mudou com credencial no ambiente ou binário no PATH')

        saida = json.loads(limpo.stdout)
        self.assertNotIn('ok', [s['status'] for s in saida['sem_config']['servicos']],
                         'sem configuração não existe leitura boa')
        codex = [s for s in saida['sem_config']['servicos'] if s['id'] == 'codex'][0]
        self.assertEqual(codex['status'], 'unconfigured')
        # Em inglês a mensagem é o próprio msgid: o texto vem do produto, não do teste.
        em_ingles = json.loads(run_dump({}, language='en.UTF-8').stdout)
        codex_en = [s for s in em_ingles['sem_config']['servicos'] if s['id'] == 'codex'][0]
        self.assertEqual(codex_en['message'], 'Codex CLI not found.')

    def test_the_report_says_what_the_isolation_substituted_and_removed(self):
        """O relatório em stderr é a parte visível do isolamento: sem ele, a prova é invisível."""
        sujo = run_dump({'DEEPSEEK_API_KEY': 'chave-da-maquina'})
        self.assertEqual(sujo.returncode, 0, sujo.stderr)
        relatorio = sujo.stderr.strip().splitlines()[-1]
        self.assertIn('rede: 0 consultas', relatorio)
        self.assertIn('workers em processo: 9', relatorio)
        self.assertIn('DEEPSEEK_API_KEY', relatorio)      # foi tirada do ambiente
        self.assertIn('sandbox /tmp/', relatorio)


class IsolationGuardTests(unittest.TestCase):
    """A guarda tem de falhar diante de acesso real — e as fixtures têm de ser usadas."""

    def test_a_network_query_is_a_violation(self):
        with isolation.Isolation() as rodada:
            import providers
            with self.assertRaises(providers.Unavailable):
                providers.request('https://api.exemplo.invalid/v1/usage')
            self.assertEqual(rodada.calls['rede'], 1)
            with self.assertRaises(SystemExit) as falha:
                rodada.assert_clean()
        self.assertIn('consulta de rede', str(falha.exception))

    def test_a_credential_file_outside_the_sandbox_is_refused(self):
        with isolation.Isolation() as rodada:
            import credentials
            self.assertEqual(credentials.read_file('/etc/passwd'), {})
            self.assertTrue(any('fora do sandbox' in motivo for motivo in rodada.violations),
                            rodada.violations)
            with self.assertRaises(SystemExit):
                rodada.assert_clean()

    def test_the_keyring_fixture_is_what_the_resolution_reads(self):
        with isolation.Isolation(keyring={'DEEPSEEK_API_KEY': 'do-cofre-fixture'}) as rodada:
            import credentials
            self.assertEqual(credentials.service_value('deepseek', {}), 'do-cofre-fixture')
            self.assertEqual(credentials.service_value('openrouter', {}), None)
            self.assertEqual(rodada.calls['cofre_leitura'], 2)
            # A rodada de evidência não grava credencial em lugar nenhum: gravar é violação.
            with self.assertRaises(RuntimeError):
                credentials.keyring_set('OPENROUTER_API_KEY', 'valor')
            self.assertIn('gravação no cofre do sistema', rodada.violations)
            rodada.violations.remove('gravação no cofre do sistema')
            rodada.assert_clean()

    def test_every_path_the_product_resolves_stays_in_the_sandbox(self):
        with isolation.Isolation() as rodada:
            for nome, caminho in rodada.product_paths().items():
                self.assertTrue(rodada.inside(Path(caminho)), f'{nome}: {caminho}')
            self.assertGreaterEqual(len(rodada.product_paths()), 6)
            rodada.assert_clean(expect=())   # aqui nenhuma credencial é resolvida

    def test_a_substitution_that_is_not_used_fails_the_run(self):
        """Isolamento não exercitado não prova nada: a fixture não usada é falha da rodada."""
        with isolation.Isolation() as rodada:
            with self.assertRaises(SystemExit) as falha:
                rodada.assert_clean(expect=('nada_disso_existe',))
        self.assertIn('nada_disso_existe', str(falha.exception))

    def test_the_credential_file_fixture_is_read_by_the_product_reader(self):
        with isolation.Isolation() as rodada:
            import credentials
            import i18n
            arquivo = rodada.path('credenciais.env')
            arquivo.write_text('DEEPSEEK_API_KEY=exemplo\nLINHA SEM IGUAL\n', encoding='utf-8')
            descartadas = []
            self.assertEqual(credentials.read_file(str(arquivo), descartadas),
                             {'DEEPSEEK_API_KEY': 'exemplo'})
            self.assertEqual(credentials.source_label(('DEEPSEEK_API_KEY',),
                                                      {'credentials_path': str(arquivo)}),
                             i18n._('from the indicated file'))   # a camada é o arquivo
            rodada.assert_clean()


if __name__ == '__main__':
    unittest.main()
