"""Idioma da interface: resolução, catálogo, política do cache e formatação.

Nada de tradução se prova aqui. Provam-se as coisas que a tradução quebra em silêncio:

- um idioma só vale com catálogo presente (sem .mo o texto sai em inglês, nunca num
  idioma que catálogo nenhum cobre);
- todo msgid que o código pede está no catálogo — incluindo os que passam por ``_t()``,
  por ``N_()`` e pelos parâmetros ``message_id``/``label_id``, e não só os de ``_()``;
- o .po cheio não garante .mo utilizável: entrada fuzzy, plural incompleto, msgid sem
  correspondência ou marcador perdido na tradução passam despercebidos até a tela;
- texto que fica no cache é exibido pelo identificador, no idioma em vigor — não pelo
  texto gravado no idioma da coleta antiga.

O catálogo conferido é ``locale/pt_BR.po`` e o compilado é o ``.mo`` que o shell do
Cinnamon e o gettext do Python carregam: por isso o teste exige que os dois existam e
que o .mo responda.
"""
import ast
import json
import re
import struct
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

BACKEND = sorted((ROOT / 'backend').glob('*.py'))
APPLET = ROOT / 'applet' / 'applet.js'

# Funções que carregam msgid no Python: `_()` mostra agora, `_t()` mostra em outro
# idioma, `_n()` decide plural, `N_()` marca texto que fica guardado. `_t(` tem de ser
# reconhecido como tal: um regex ingênuo (`_(?:_t)?`) casa `__t(` e não casa `_t(` —
# foi assim que a cobertura ignorou 4 chamadas reais.
PY_CALLS = {'_', '_t', 'N_'}
PY_PLURALS = {'_n'}

# Dívida declarada por arquivo: literais em português que o usuário lê e que ainda não
# passam pelo catálogo (mensagem de erro dos provedores, rótulo de métrica, texto das
# janelas). O número só muda em commit que traduz — conversão derruba, texto novo sem
# catálogo estoura o teste no commit que o introduziu. Fase 2 zera esta tabela.
PENDING_PROSE = {
    'collector.py': 11,
    'credentials.py': 6,
    'credentials_window.py': 25,
    'i18n.py': 0,
    'providers.py': 59,
    'window.py': 34,
}


def decode(line):
    match = re.match(r'^[a-z_]+(?:\[\d\])?\s+(".*")$', line)
    return json.loads(match.group(1)) if match else ''


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


def catalog():
    """O que o .po diz, por msgid: formas traduzidas e o msgid do plural (se houver)."""
    table = {}
    for entry in parse_po(PO):
        if not entry['id']:
            continue                                    # cabeçalho
        table[entry['id']] = {'text': entry['plural_strs'] if entry['plural'] else [entry['str']],
                              'plural': entry['plural']}
    return table


def lookup():
    """msgid -> tradução, aceitando tanto o singular quanto o plural de uma entrada."""
    table = dict(catalog())
    for msgid, entry in catalog().items():
        if entry['plural']:
            table[entry['plural']] = {'text': entry['text'], 'plural': None}
    return table


def parse_mo(path):
    """O .mo lido cru, sem gettext: é o artefato que o shell lê, e é ele que se confere.

    Formato (GNU gettext): magic, revisão, contagem, offset das originais, offset das
    traduções, hash; as tabelas são pares (tamanho, offset) e as strings vêm separadas
    por NUL — msgid ``singular\\0plural`` e msgstr com uma forma por NUL.
    """
    data = path.read_bytes()
    magic, _, count, originals, translations, _ = struct.unpack_from('<6I', data, 0)
    assert magic == 0x950412de, 'não é um .mo nativo (little-endian)'
    table = {}
    for i in range(count):
        def read(offset):
            length, at = struct.unpack_from('<2I', data, offset)
            return data[at:at + length].decode('utf-8')
        msgid = read(originals + i * 8)
        if not msgid:
            continue
        parts = msgid.split('\u0000')
        table[parts[0]] = {'text': read(translations + i * 8).split('\u0000'),
                           'plural': parts[1] if len(parts) > 1 else None}
    return table


def header_value(name, default=''):
    """Campo do cabeçalho do .po, como ``Plural-Forms``."""
    header = parse_po(PO)[0]['str']
    match = re.search(r'^%s:\s*(.*)$' % re.escape(name), header, re.M)
    return match.group(1).strip() if match else default


def py_msgids(path):
    """msgids que um fonte Python carrega, pelo AST — não por regex.

    O AST resolve o que a regex não vê: concatenação implícita (``"a " "b"`` é um msgid
    só), chamadas dentro de argumento padrão e valor de constante, e keyword como
    ``message_id=``/``label_id=``. ``f-string`` num msgid é falta: msgid tem de ser
    literal, senão nem o xgettext nem a cobertura o enxergam.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'))
    singles, plurals, offences = set(), set(), []

    def take(node, plural=False):
        if node is None:
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            (plurals if plural else singles).add(node.value)
        elif isinstance(node, ast.JoinedStr):
            offences.append(('f-string', getattr(node, 'lineno', 0)))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else '')
        if name in PY_CALLS:
            take(node.args[0] if node.args else None)
        elif name in PY_PLURALS and len(node.args) >= 2:
            take(node.args[0], plural=True)
            take(node.args[1], plural=True)
        for keyword in node.keywords:
            if keyword.arg in ('message_id', 'label_id'):
                take(keyword.value)
    return singles, plurals, offences


def js_msgids(text):
    """msgids do applet: ``_()``, ``N_()`` e ``_n()``, com ``+`` de string juntado."""
    def literals(rest):
        """Consome a sequência de literais concatenados que começa em ``rest``."""
        value, rest = '', rest
        while True:
            match = re.match(r"""\s*(['"])((?:[^'"\\\n]|\\.)*)\1""", rest)
            if not match:
                break
            value += match.group(2)
            rest = rest[match.end():]
            join = re.match(r"""\s*\+\s*(?=['"])""", rest)
            if not join:
                break
            rest = rest[join.end():]
        return value, rest

    singles, plurals = set(), set()
    pattern = re.compile(r"""(?<!\w)(_t|_n|_|N_)\(([^\n]*)""")
    for match in pattern.finditer(text):
        name, rest = match.group(1), match.group(2)
        first, rest = literals(rest)
        if not first and not rest.strip().startswith(('"', "'")):
            continue
        if name == '_n':
            if not re.match(r"""\s*,\s*(?=['"])""", rest):
                continue
            second, _ = literals(rest[rest.index(',') + 1:])
            plurals.update([first, second])
        else:
            singles.add(first)
    return singles, plurals


def unescape(text):
    """O literal do JS para o Python: só as barras invertidas mudam de sentido."""
    return text.replace("\\'", "'").replace('\\"', '"').replace('\\\\', '\\')


def source_calls():
    """Todos os msgid do código, pelo AST no Python e pelo literal no applet."""
    singles, plurals, offences = set(), set(), []
    for path in BACKEND:
        found_s, found_p, found_o = py_msgids(path)
        singles |= found_s
        plurals |= found_p
        offences += [(path.name, kind, line) for kind, line in found_o]
    found_s, found_p = js_msgids(APPLET.read_text(encoding='utf-8'))
    singles |= {unescape(text) for text in found_s}
    plurals |= {unescape(text) for text in found_p}
    return singles, plurals, offences


def prose_outside_catalog(path, known):
    """Literais em português que o usuário lê e que ainda não passam pelo catálogo.

    Fora da conta ficam docstring, comentário (que não é literal) e o que já é msgid do
    catálogo — a dívida é prosa portuguesa que ainda não tem tradução nenhuma.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, 'body', [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    pending = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings or node.value in known:
            continue
        if any(ord(char) > 127 for char in node.value):
            pending.append(node.value)
    return pending


class ExtractionTests(unittest.TestCase):
    """A cobertura só vale se enxergar as chamadas reais — foi um regex que falhou antes."""

    def test_python_extraction_covers_t_and_n_and_marker(self):
        import tempfile
        source = (
            'def f(code, n):\n'
            '    a = _("plain")\n'
            '    b = _t("other", code)\n'
            '    c = _n("one", "many", n)\n'
            '    d = N_("kept as msgid")\n'
            '    e = __t("decoy")\n'
            '    g = service("x", message_id=N_("from keyword " "joined"))\n'
            '    return a, b, c, d, e, g\n'
        )
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / 'sample.py'
            path.write_text(source, encoding='utf-8')
            singles, plurals, offences = py_msgids(path)
        self.assertIn('plain', singles)
        self.assertIn('other', singles, 'msgid passado a _t() tem de ser coberto')
        self.assertIn('kept as msgid', singles)
        self.assertIn('from keyword joined', singles, 'concatenação implícita é um msgid só')
        self.assertNotIn('decoy', singles, '__t não é função de tradução')
        self.assertEqual(plurals, {'one', 'many'})
        self.assertEqual(offences, [])

    def test_python_extraction_refuses_fstring_msgid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / 'sample.py'
            path.write_text('def f(code):\n    return _t(f"HTTP {code}", "en")\n',
                            encoding='utf-8')
            _, _, offences = py_msgids(path)
        self.assertEqual([kind for kind, _ in offences], ['f-string'],
                         'msgid montado em f-string não entra em catálogo nenhum')

    def test_javascript_extraction_joins_concatenation(self):
        singles, plurals = js_msgids("const a = _('part one ' + 'and two');\n"
                                     "const b = _n('{n} day', '{n} days', n);\n"
                                     "const c = __t('decoy');\n")
        self.assertIn('part one and two', singles)
        self.assertIn('{n} day', plurals)
        self.assertIn('{n} days', plurals)
        self.assertNotIn('decoy', singles)

    def test_every_msgid_in_the_sources_is_translated(self):
        singles, plurals, offences = source_calls()
        self.assertEqual(offences, [], 'msgid em f-string: escreva o literal')
        self.assertGreater(len(singles), 40, 'extração de msgid quebrou')
        entries = lookup()
        for msgid in sorted(singles | plurals):
            self.assertIn(msgid, entries, 'msgid sem entrada no catálogo pt_BR')
            self.assertTrue(any(text.strip() for text in entries[msgid]['text']),
                            'msgid sem tradução: %r' % msgid)

    def test_prose_outside_the_catalog_is_declared(self):
        known = set(lookup())
        found = {}
        for path in BACKEND:
            pending = prose_outside_catalog(path, known)
            if pending:
                found[path.name] = len(pending)
        declared = {name: count for name, count in PENDING_PROSE.items() if count}
        self.assertEqual(found, declared,
                         'prosa nova sem catálogo (traduza e ajuste PENDING_PROSE)')


class CatalogTests(unittest.TestCase):
    def test_compiled_catalog_answers(self):
        self.assertTrue(MO.is_file(), 'rode scripts/i18n.sh: o .mo versionado é o que o shell lê')
        self.assertEqual(i18n.activate('pt_BR'), 'pt_BR')
        self.assertEqual(i18n._('No reading yet; use Update or See all.'),
                         'Sem leitura ainda; use Atualizar ou Ver todos.')

    def test_catalog_rejects_fuzzy_entry(self):
        """Fuzzy é tradução que o msgfmt não compila: a tela volta ao inglês e ninguém vê."""
        fuzzy = [line for line in PO.read_text(encoding='utf-8').splitlines()
                 if line.startswith('#,') and 'fuzzy' in line]
        self.assertEqual(fuzzy, [], 'entrada fuzzy no catálogo: ela não chega ao .mo')

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

    def test_plural_forms_are_complete(self):
        """nplurals do cabeçalho manda: entrada de plural com forma faltando não se vê a olho."""
        nplurals = int(header_value('Plural-Forms', 'nplurals=2').split('nplurals=')[1].split(';')[0])
        for entry in parse_po(PO):
            if not entry['plural']:
                continue
            self.assertEqual(len(entry['plural_strs']), nplurals,
                             'plural com %d formas em vez de %d: %r'
                             % (len(entry['plural_strs']), nplurals, entry['id']))
            for form in entry['plural_strs']:
                self.assertTrue(form.strip(), 'forma plural vazia: %r' % entry['id'])

    def test_compiled_catalog_matches_the_po(self):
        """O .mo é o artefato: toda entrada do .po tem de estar nele, e nada a mais.

        Entrada fuzzy, plural truncado ou catálogo velho só aparecem aqui.
        """
        po_table, mo_table = catalog(), parse_mo(MO)
        self.assertEqual(sorted(mo_table), sorted(po_table),
                         'msgid no .po sem correspondência no .mo (rode scripts/i18n.sh)')
        for msgid, entry in po_table.items():
            self.assertEqual(mo_table[msgid]['text'], entry['text'],
                             'tradução do .mo difere do .po em %r' % msgid)

    def test_placeholders_survive_translation(self):
        """Marcador perdido na tradução vira frase sem número — ou quebrada."""
        for msgid, entry in catalog().items():
            if not msgid:
                continue
            forms = entry['text']
            for form in forms:
                self.assertEqual(sorted(re.findall(r'\{(\w+)\}', msgid)),
                                 sorted(re.findall(r'\{(\w+)\}', form)),
                                 'marcadores diferentes entre msgid e tradução: %r' % msgid)

    def test_xlet_json_strings_are_in_the_catalog(self):
        """Nome, descrição e rótulos vêm de JSON, que o xgettext não lê: é o gerador que os traz."""
        placed = set(catalog())
        strings = xlet_strings.xlet_strings()
        self.assertIn('AI usage', strings)
        self.assertIn('Automatic (system language)', strings)
        for text in strings:
            self.assertIn(text, placed, 'string do xlet fora do catálogo: %r' % text)

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

    def test_session_language_and_preference_cross_every_way(self):
        """Idioma da sessão e preferência são eixos diferentes: o pedido explícito vence.

        É o caso que a revisão reproduziu no applet — preferência em inglês, sessão em
        português, e a interface metade em cada idioma.
        """
        cases = (
            # sessão, pedido, texto esperado, número esperado
            ('pt_BR.UTF-8', 'en', 'Update', '1234.50'),
            ('en_US.UTF-8', 'pt_BR', 'Atualizar', '1234,50'),
            ('pt_BR.UTF-8', None, 'Atualizar', '1234,50'),
            ('en_US.UTF-8', None, 'Update', '1234.50'),
        )
        for session, requested, text, number in cases:
            with patch.dict('os.environ',
                            {'LANGUAGE': session, 'LC_ALL': session, 'LANG': session},
                            clear=True):
                i18n.activate(requested)
                self.assertEqual(i18n._('Update'), text, (session, requested))
                self.assertEqual(i18n.number(1234.5), number, (session, requested))

    def test_fixed_language_without_catalog_is_english_not_the_session(self):
        """Pedido que não pode ser honrado cai no inglês, nunca no idioma da sessão."""
        with patch.dict('os.environ', {'LANGUAGE': 'pt_BR.UTF-8', 'LANG': 'pt_BR.UTF-8'},
                        clear=True):
            self.assertEqual(i18n.activate('fr_FR'), 'en')
            self.assertEqual(i18n._('Update'), 'Update')
            self.assertEqual(i18n.number(1234.5), '1234.50')


class CachedTextPolicyTests(unittest.TestCase):
    """Política dos textos que ficam no cache: o identificador manda, o texto é recurso.

    Sem isto, trocar o idioma deixava na tela a mensagem gravada no idioma da coleta
    anterior — e forçar uma coleta não resolve falha, offline nem coleta pausada.
    """

    def setUp(self):
        i18n.activate('pt_BR')

    def tearDown(self):
        with patch.dict('os.environ', {'LANGUAGE': 'en', 'LC_ALL': 'en', 'LANG': 'en'}):
            i18n.activate()

    def test_record_with_identifier_follows_the_current_language(self):
        record = {'message_id': 'Failed to read the service data; try refreshing.',
                  'message': 'Falha ao ler os dados do serviço; tente atualizar.'}
        self.assertEqual(i18n.record_text(record),
                         'Falha ao ler os dados do serviço; tente atualizar.')
        i18n.activate('en')
        self.assertEqual(i18n.record_text(record),
                         'Failed to read the service data; try refreshing.')

    def test_reading_saved_in_portuguese_appears_in_english(self):
        """O caso do revisor: leitura em pt_BR, preferência em inglês, sem recolher nada."""
        saved_in_pt = {'message_id': 'Last reading available; refresh pending.',
                       'message': 'Última leitura disponível; atualização pendente.',
                       'message_args': {}}
        i18n.activate('en')
        self.assertEqual(i18n.record_text(saved_in_pt),
                         'Last reading available; refresh pending.')
        i18n.activate('pt_BR')
        self.assertEqual(i18n.record_text(saved_in_pt),
                         'Última leitura disponível; atualização pendente.')

    def test_arguments_are_filled_and_kept_raw(self):
        """Marcador recebe valor bruto e não é reformatado.

        É por isso que número formatado não entra em msgid de rótulo: quem formata é a
        apresentação, com o idioma em vigor (`formatPercent` no applet, `i18n.percent` na
        janela). O que a coleta formatou fica no idioma em que ela formatou.
        """
        record = {'label_id': '{label}: {percent} used',
                  'label_args': {'label': 'Janela de 5 h', 'percent': '42,0%'},
                  'label': 'Janela de 5 h: 42,0% usado'}
        self.assertEqual(i18n.record_text(record, 'label_id', 'label_args', 'label'),
                         'Janela de 5 h: 42,0% usado')
        i18n.activate('en')
        self.assertEqual(i18n.record_text(record, 'label_id', 'label_args', 'label'),
                         'Janela de 5 h: 42,0% used')
        self.assertEqual(i18n._f('{label}: {percent} used', label='Opus', percent=42),
                         'Opus: 42 used')

    def test_missing_or_unknown_identifier_falls_back_to_the_saved_text(self):
        self.assertEqual(i18n.record_text({'message': 'Frase antiga, sem identificador.'}),
                         'Frase antiga, sem identificador.')
        self.assertEqual(i18n.record_text({'message_id': 'Not in the catalog',
                                           'message': 'Texto gravado.'}),
                         'Texto gravado.')
        self.assertEqual(i18n.record_text({}), '')
        self.assertEqual(i18n.record_text(None), '')

    def test_identifier_of_case_not_matched(self):
        """Identificador que é outra frase do catálogo não pode ser usado a esmo."""
        record = {'message_id': 'Update', 'message': 'texto gravado'}
        self.assertEqual(i18n.record_text(record, 'message_id', 'message_args', 'message'),
                         'Atualizar')


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
