"""Idioma da interface: resolução, catálogo e formatação.

Nada de tradução se prova aqui. Provam-se as três coisas que a tradução quebra em
silêncio: um idioma só vale com catálogo presente (sem .mo o texto sai em inglês,
nunca num idioma que catálogo nenhum cobre); todo msgid que o código pede está
traduzido (string nova sem tradução falha aqui, e não na tela do usuário); e
número, data e dinheiro seguem o idioma resolvido, não o locale do processo.

O catálogo conferido é ``locale/pt_BR.po`` e o compilado é o ``.mo`` que o shell do
Cinnamon e o gettext do Python carregam: por isso o teste exige que os dois
existam e que o .mo responda.
"""
import json
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
import i18n
import xlet_strings

CATALOG_DIR = ROOT / 'locale'
PO = CATALOG_DIR / 'pt_BR.po'
MO = CATALOG_DIR / 'pt_BR' / 'LC_MESSAGES' / (i18n.DOMAIN + '.mo')

CALL = re.compile(r"""_(?:_t)?\(\s*(['"])((?:[^'"\\\n]|\\.)*)\1""")
PLURAL_CALL = re.compile(r"""_n\(\s*(['"])((?:[^'"\\\n]|\\.)*)\1\s*,\s"""
                         r"""(['"])((?:[^'"\\\n]|\\.)*)\3""")


def parse_po(path):
    """msgid/msgid_plural -> msgstr, com continuação de linha (o msgmerge quebra)."""
    entries, current, field = [], None, None
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('msgid_plural '):
            current['plural'] = decode(line)
            current['plural_strs'] = []
            field = 'plural'
        elif line.startswith('msgid '):
            current = {'id': decode(line), 'str': '', 'plural': None, 'plural_strs': []}
            entries.append(current)
            field = 'id'
        elif line.startswith('msgstr['):
            current['plural_strs'].append(decode(line))
            field = 'plural_strs'
        elif line.startswith('msgstr '):
            current['str'] = decode(line)
            field = 'str'
        elif line.startswith('"') and current is not None:
            text = decode('msgid ' + line)
            if field == 'id':
                current['id'] += text
            elif field == 'str':
                current['str'] += text
            elif field == 'plural':
                current['plural'] += text
            elif field == 'plural_strs' and current['plural_strs']:
                current['plural_strs'][-1] += text
    return entries


def decode(line):
    match = re.match(r'^[a-z_]+(?:\[\d\])?\s+(".*")$', line)
    return json.loads(match.group(1)) if match else ''


def unescape(text):
    """O literal do JS para o Python: só as barras invertidas mudam de sentido."""
    return text.replace("\\'", "'").replace('\\"', '"').replace('\\\\', '\\')


def source_calls():
    """Toda chamada de tradução no código: `_(...)` e `_n(singular, plural, n)`."""
    sources = [ROOT / 'applet/applet.js'] + sorted((ROOT / 'backend').glob('*.py'))
    singles, plurals = set(), set()
    for path in sources:
        text = path.read_text(encoding='utf-8')
        for _, msgid in CALL.findall(text):
            singles.add(unescape(msgid))
        for _, singular, _, plural in PLURAL_CALL.findall(text):
            plurals.add(unescape(singular))
            plurals.add(unescape(plural))
    return singles, plurals


class LanguageResolutionTests(unittest.TestCase):
    def tearDown(self):
        with patch.dict('os.environ', {'LANGUAGE': 'en', 'LC_ALL': 'en', 'LANG': 'en'}):
            i18n.activate()

    def test_explicit_setting_beats_the_environment(self):
        with patch.dict('os.environ', {'LANGUAGE': 'en_US.UTF-8'}):
            self.assertEqual(i18n.resolve('pt_BR'), 'pt_BR')
            self.assertEqual(i18n.resolve('pt-BR'), 'pt_BR')

    def test_environment_is_read_most_specific_first(self):
        env = {'LANGUAGE': 'pt_BR:en', 'LC_ALL': 'en_US.UTF-8', 'LANG': 'en_US.UTF-8'}
        with patch.dict('os.environ', env):
            self.assertEqual(i18n.resolve(), 'pt_BR')
        env = {'LC_ALL': 'pt_BR.UTF-8', 'LANG': 'en_US.UTF-8'}
        with patch.dict('os.environ', env, clear=True):
            self.assertEqual(i18n.resolve(), 'pt_BR')

    def test_language_without_catalog_falls_back_to_english(self):
        """Sem catálogo francês, a interface sai em inglês — não em francês pela metade."""
        self.assertEqual(i18n.resolve('fr_FR'), 'en')
        with patch.dict('os.environ', {'LANGUAGE': 'de_DE', 'LANG': 'de_DE'}, clear=True):
            self.assertEqual(i18n.resolve(), 'en')

    def test_aliases_and_c_locale(self):
        for tag, expected in (('pt', 'pt_BR'), ('pt_PT', 'pt_BR'), ('C', 'en'),
                              ('POSIX', 'en'), ('en_GB.UTF-8', 'en')):
            self.assertEqual(i18n.normalize(tag), expected, tag)
        self.assertEqual(i18n.normalize('ru_RU'), '')

    def test_activate_loads_the_catalog_and_gives_english_as_msgid(self):
        self.assertEqual(i18n.activate('pt_BR'), 'pt_BR')
        self.assertEqual(i18n._('Update'), 'Atualizar')
        self.assertEqual(i18n.language(), 'pt_BR')
        i18n.activate('en')
        self.assertEqual(i18n._('Update'), 'Update')

    def test_settings_options_and_language_table_agree(self):
        """Opção no settings-schema sem idioma em LANGUAGES (ou o contrário) não se vê a olho."""
        schema = json.loads((ROOT / 'applet/settings-schema.json').read_text(encoding='utf-8'))
        options = set(schema['language']['options'].values())
        self.assertEqual(options - {'auto'}, set(i18n.LANGUAGES))
        self.assertEqual(schema['language']['default'], 'auto')

    def test_entry_points_activate_the_language(self):
        """`_()` sem activate devolve msgid: sem esta chamada a janela sai sempre em inglês."""
        for name in ('collector.py', 'window.py', 'credentials_window.py'):
            source = (ROOT / 'backend' / name).read_text(encoding='utf-8')
            self.assertIn('i18n.activate(', source, name)


class CatalogTests(unittest.TestCase):
    def test_compiled_catalog_answers(self):
        self.assertTrue(MO.is_file(), 'rode scripts/i18n.sh: o .mo versionado é o que o shell lê')
        self.assertEqual(i18n.activate('pt_BR'), 'pt_BR')
        self.assertEqual(i18n._('No reading yet; use Update or See all.'),
                         'Sem leitura ainda; use Atualizar ou Ver todos.')

    def test_every_msgid_in_the_sources_is_translated(self):
        singles, plurals = source_calls()
        self.assertGreater(len(singles), 30, 'extração de msgid quebrou')
        entries = parse_po(PO)
        translated = {e['id']: e['str'] for e in entries}
        # Numa entrada de plural o singular é o msgid e o plural o msgid_plural: os dois
        # precisam estar no catálogo, e a chave aqui aceita qualquer um dos dois.
        plural_ids = {}
        for entry in entries:
            if entry['plural']:
                plural_ids[entry['id']] = entry['plural_strs']
                plural_ids[entry['plural']] = entry['plural_strs']
        for msgid in sorted(singles):
            self.assertIn(msgid, translated, 'msgid sem entrada no catálogo pt_BR')
            self.assertTrue(translated[msgid].strip(), 'msgid sem tradução: %r' % msgid)
        for msgid in sorted(plurals):
            self.assertIn(msgid, plural_ids, 'msgid de plural fora do catálogo pt_BR')
            self.assertTrue(any(text.strip() for text in plural_ids[msgid]),
                            'plural sem tradução: %r' % msgid)

    def test_xlet_json_strings_are_in_the_catalog(self):
        """Nome, descrição e rótulos vêm de JSON, que o xgettext não lê: é o gerador que os traz."""
        placed = {entry['id'] for entry in parse_po(PO)}
        strings = xlet_strings.xlet_strings()
        self.assertIn('AI usage', strings)
        self.assertIn('Automatic (system language)', strings)
        for text in strings:
            self.assertIn(text, placed, 'string do xlet fora do catálogo: %r' % text)

    def test_catalog_has_no_untranslated_entry(self):
        for entry in parse_po(PO):
            self.assertTrue(entry['str'].strip() or entry['plural_strs'],
                            'entrada sem tradução no catálogo: %r' % entry['id'])

    def test_catalog_has_no_obsolete_entry(self):
        """Entrada obsoleta é tradução aposentada em silêncio — e o msgfmt a deixa fora do .mo.

        Acontece quando o msgid deixa de ser extraído: sem --keyword para a função que
        carrega o texto, o xgettext aposenta a entrada e a interface volta ao inglês sem
        nenhum erro.
        """
        obsolete = [line for line in PO.read_text(encoding='utf-8').splitlines()
                    if line.startswith('#~')]
        self.assertEqual(obsolete, [], 'tradução obsoleta no catálogo (msgid não é mais extraído?)')


class FormattingTests(unittest.TestCase):
    moment = datetime(2026, 9, 26, 14, 35, tzinfo=timezone(timedelta(hours=-3)))

    def test_numbers_follow_the_language_not_the_process_locale(self):
        self.assertEqual(i18n.number(1234.5, 2, 'pt_BR'), '1234,50')
        self.assertEqual(i18n.number(1234.5, 2, 'en'), '1234.50')
        self.assertEqual(i18n.percent(42, 1, 'pt_BR'), '42,0%')
        self.assertEqual(i18n.percent(42, 1, 'en'), '42.0%')

    def test_money_order_follows_the_language(self):
        self.assertEqual(i18n.money(7.02, 'USD', 'pt_BR'), '7,02 USD')
        self.assertEqual(i18n.money(7.02, 'USD', 'en'), 'USD 7.02')
        self.assertEqual(i18n.money(7.02, None, 'en'), '7.02')

    def test_datetime_and_time(self):
        self.assertEqual(i18n.datetime_text(self.moment, code='pt_BR'), '26/09/2026 14:35')
        self.assertEqual(i18n.datetime_text(self.moment, code='en'), 'Sep 26, 2026 2:35 PM')
        self.assertEqual(i18n.time_text(self.moment, 'pt_BR'), '14:35')
        self.assertEqual(i18n.time_text(self.moment, 'en'), '2:35 PM')
        self.assertEqual(i18n.datetime_text(self.moment, with_time=False, code='en'), 'Sep 26, 2026')

    def test_missing_percent_is_never_zero(self):
        self.assertEqual(i18n.percent(None, code='pt_BR'), 'percentual indisponível')
        self.assertEqual(i18n.percent(None, code='en'), 'percentage unavailable')
        self.assertEqual(i18n.number('7', code='pt_BR'), 'indisponível')

    def test_duration_and_relative_are_translated(self):
        self.assertEqual(i18n.activate('pt_BR'), 'pt_BR')
        self.assertEqual(i18n.duration(45), 'menos de 2 minutos')
        self.assertEqual(i18n.duration(3 * 3600), '3 h')
        self.assertEqual(i18n.duration(3 * 86400), '3 dias')
        self.assertEqual(i18n.relative(self.moment,
                                       now=self.moment + timedelta(hours=3)), 'há 3 h')
        i18n.activate('en')
        self.assertEqual(i18n.duration(3 * 3600), '3 h')
        self.assertEqual(i18n.duration(3 * 86400), '3 days')
        self.assertEqual(i18n.relative(self.moment,
                                       now=self.moment + timedelta(hours=3)), '3 h ago')
        # Instante no futuro (relógio adiantado na origem) não vira duração: é 'agora'.
        self.assertEqual(i18n.relative(self.moment, now=self.moment - timedelta(seconds=5)), 'now')

    def test_placeholders_do_not_reformat_numbers(self):
        self.assertEqual(i18n._f('{label}: {percent} used',
                                 label='Janela de 5 h', percent=i18n.percent(42, 1, 'pt_BR')),
                         'Janela de 5 h: 42,0% used')
        self.assertEqual(i18n._f('{count} more', count=3), '3 more')


if __name__ == '__main__':
    unittest.main()
