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
import tempfile
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

# Literais que PARECEM prosa e não são texto de tela. Nenhum deles é dívida: são nome de
# serviço, molde de formatação ou erro de programação, e cada um vem com o motivo. A lista
# é conferida por igualdade, então literal novo que pareça prosa falha no commit que o
# introduz — nas DUAS línguas: o detector antigo só olhava caractere não-ASCII, e por isso
# não via "Saldo", "Sem uso observado" nem texto em inglês fixo no código.
NOT_PROSE = {
    'collector.py': {},
    'credentials.py': {
        'Cinnamon AI Usage': 'nome do applet, gravado como rótulo da entrada no cofre',
    },
    'credentials_window.py': {
        'Grok / xAI': 'nome de serviço, não texto traduzível',
        'Nous Portal': 'nome de serviço, não texto traduzível',
        'OpenCode Go': 'nome de serviço, não texto traduzível',
    },
    'i18n.py': {},
    'providers.py': {
        'Claude Code': 'nome de serviço, não texto traduzível',
        'Codex app-server': 'nome de serviço, não texto traduzível',
        'Grok / xAI': 'nome de serviço, não texto traduzível',
        'Loopback only': 'erro de programação (ValueError), não texto de tela',
        'Meta AI (Muse Code)': 'nome de serviço, não texto traduzível',
        'Nous Portal': 'nome de serviço, não texto traduzível',
        'OpenCode Go': 'nome de serviço, não texto traduzível',
    },
    'window.py': {},
}

# Um molde de formatação (data, hora, dinheiro) tem espaço e mais de uma palavra sem ser
# frase: fica fora da conta pela forma, e por isso `i18n.py` não declara nenhum.
FORMAT_ONLY = re.compile(r"^[\w.\-/:@\[\]{}<>*+=#$%~^|]+$")


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


def persisted_msgids(path):
    """msgids que foram feitos para FICAR GRAVADOS, com a linha de origem.

    São os marcados com ``N_()`` (identificador que vai para o contrato/cache) e os passados
    como ``message_id=``/``label_id=`` — os dois caminhos pelos quais um texto sai do código
    e vira registro persistido.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'))
    achados = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else '')
        if name == 'N_' and node.args:
            valor = node.args[0]
            if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                achados.append((valor.value, node.lineno))
        for keyword in node.keywords:
            if keyword.arg in ('message_id', 'label_id'):
                valor = keyword.value
                if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                    achados.append((valor.value, node.lineno))
    return achados


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


def looks_like_prose(value):
    """Este literal parece texto que uma pessoa lê?

    A forma decide, não o alfabeto: duas ou mais palavras escritas, com letras de verdade
    dos dois lados, separadas por espaço, numa linha só e sem ser um token técnico (nome de
    campo, caminho, id, molde, código de status). É o que pega "Saldo total disponível",
    "Sem uso observado" e um "Refresh" fixo no código — prosa portuguesa sem acento e prosa
    inglesa que nunca trocaria de idioma, as duas invisíveis para o detector por acento.
    """
    if not isinstance(value, str) or len(value) < 4:
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]", value) or '\n' in value or '\t' in value:
        return False
    if FORMAT_ONLY.match(value.strip()):
        return False
    # Só marcadores e pontuação ('{value} {currency}', ' · ') não é frase: sem tirar os
    # marcadores, um molde de formatação com espaço passaria por prosa.
    if not re.search(r"[A-Za-zÀ-ÿ]{2,}", re.sub(r'\{[^}]*\}', '', value)):
        return False
    palavras = [palavra for palavra in re.split(r'\s+', value.strip())
                if re.search(r"[A-Za-zÀ-ÿ]{2,}", palavra)]
    return len(palavras) >= 2


def prose_outside_catalog(path, known):
    """Literais que parecem prosa e não estão no catálogo, em qualquer idioma.

    Fora da conta ficam docstring (documentação de quem mantém o código), comentário (que
    não é literal), o que já é msgid do catálogo e o que não parece frase. Sobra exatamente
    o que o usuário lê sem passar pela tradução.
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
        if looks_like_prose(node.value):
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
        """Nenhuma prosa fora do catálogo, e o que parece prosa está declarado com motivo.

        A comparação é por igualdade: prosa nova — em português com ou sem acento, ou em
        inglês — falha no commit que a introduz, e a lista declarada não pode crescer sem
        alguém escrever por que aquele literal não é texto de tela.
        """
        known = set(lookup())
        encontrado = {}
        for path in BACKEND:
            pendentes = prose_outside_catalog(path, known)
            if pendentes:
                encontrado[path.name] = sorted(set(pendentes))
        declarado = {nome: sorted(literais) for nome, literais in NOT_PROSE.items() if literais}
        self.assertEqual(encontrado, declarado,
                         'literal novo que parece prosa e não passa pelo catálogo')

    def test_the_detector_sees_prose_without_accents_and_in_english(self):
        """O detector é conferido por testemunhas: sem isto ele poderia não ver nada.

        Três testemunhas de prosa — uma com acento, uma sem acento nenhum e uma em inglês —
        e três de não-prosa: token técnico, molde de formatação e uma frase dentro de
        docstring (que o detector tem de ignorar).
        """
        for texto in ('Cota crítica', 'Saldo total disponivel', 'Refresh skipped'):
            self.assertTrue(looks_like_prose(texto), texto)
        for texto in ('balance', 'stale', '{value} {currency}', 'XAI_TEAM_ID', '127.0.0.1'):
            self.assertFalse(looks_like_prose(texto), texto)
        amostra = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)
        amostra.write('"""Docstring com prosa em português."""\n'
                      'def f():\n'
                      '    """Outra docstring com prosa."""\n'
                      '    # comentário com prosa em português\n'
                      '    return "Saldo total disponivel"\n')
        amostra.close()
        achados = prose_outside_catalog(Path(amostra.name), known=set())
        Path(amostra.name).unlink()
        self.assertEqual(achados, ['Saldo total disponivel'],
                         'o detector tem de ver prosa sem acento e ignorar docstring')

    def test_installer_messages_come_from_the_catalog(self):
        """O instalador também fala com uma pessoa: a mensagem dele é msgid.

        Fora do catálogo, quem instala em inglês lê português e quem instala em português
        lê inglês — as duas coisas já aconteceram com o texto que ficava preso no código.
        """
        instalador = (ROOT/'install.py').read_text(encoding='utf-8')
        self.assertNotIn("print('", instalador, 'mensagem do instalador presa no código')
        for chave in ('Installed in:', 'Catalog installed in:',
                      'Open the Cinnamon Applets settings and add AI usage to the panel.'):
            self.assertIn(chave, instalador, chave)
            self.assertIn(chave, catalog(), 'msgid do instalador fora do catálogo: %r' % chave)


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

    def test_persisted_identifiers_are_singular(self):
        """Identificador gravado tem de ser entrada de forma única no catálogo.

        O contrato não oferece seleção de plural em registro persistido: escolher a forma
        exigiria o número, que o registro guardado não carrega. Um msgid plural gravado como
        identificador sairia sempre na primeira forma — "1 dia" onde a coleta leu "3 dias" —
        ou cairia no texto gravado sem ninguém entender por quê. Por isso a conversão usa
        frase singular com o número por marcador.
        """
        plurais = {msgid for msgid, entrada in catalog().items() if entrada.get('plural')}
        self.assertTrue(plurais, 'o catálogo não tem plural nenhum: o teste perdeu o sentido')
        for path in BACKEND:
            for msgid, linha in persisted_msgids(path):
                self.assertNotIn(msgid, plurais,
                                 '%s:%d identificador persistido é plural: %r'
                                 % (path.name, linha, msgid))
        # O painel também carrega identificador para o contrato (`N_`), e ali o crivo é o mesmo.
        for msgid in re.findall(r"N_\(\s*'([^']+)'", APPLET.read_text(encoding='utf-8')):
            self.assertNotIn(msgid, plurais, 'applet.js: identificador persistido é plural: %r' % msgid)

    def test_entry_points_activate_the_language(self):
        """`_()` sem activate devolve msgid: sem esta chamada a janela sai sempre em inglês."""
        for name in ('collector.py', 'window.py', 'credentials_window.py'):
            source = (ROOT / 'backend' / name).read_text(encoding='utf-8')
            self.assertIn('i18n.activate(', source, name)


class PluralTests(unittest.TestCase):
    """A forma plural do painel tem de ser a mesma do catálogo e do backend.

    O painel não tem gettext: escolhe a forma por uma regra em código. Se essa regra discordar
    do `Plural-Forms` do catálogo compilado, o mesmo número sai singular no painel e plural na
    janela — e não se vê a olho, porque as duas frases parecem certas. O catálogo pt_BR declara
    `plural=(n > 1)`, então zero é singular: um `n === 1` genérico mostraria "0 dias".
    """

    def tearDown(self):
        with patch.dict('os.environ', {'LANGUAGE': 'en', 'LC_ALL': 'en', 'LANG': 'en'}):
            i18n.activate()

    def test_panel_rule_matches_the_catalog_header(self):
        expression = header_value('Plural-Forms', 'nplurals=2; plural=(n != 1);')
        match = re.search(r'plural\s*=\s*([^;]+)', expression)
        self.assertTrue(match, 'cabeçalho sem expressão de plural: %r' % expression)
        rule = match.group(1).strip()
        # A expressão é a do nosso próprio cabeçalho: só `n`, números e operadores entram.
        self.assertRegex(rule, r'^[\s\d()n<>!=&|+\-*/%?:.]+$')
        for n in (0, 1, 2, 3, 11, 100, 1000):
            expected = int(eval(rule, {'__builtins__': {}}, {'n': n}))
            self.assertEqual(i18n.LANGUAGES['pt_BR']['plural'](n), expected, (rule, n))

    def test_english_rule_differs_from_portuguese_exactly_at_zero(self):
        """Inglês não tem catálogo, mas a regra é a do idioma — e a diferença é o zero."""
        for n in (1, 2, 3, 11, 100):
            self.assertEqual(i18n.LANGUAGES['en']['plural'](n),
                             i18n.LANGUAGES['pt_BR']['plural'](n), n)
        self.assertEqual(i18n.LANGUAGES['pt_BR']['plural'](0), 0, 'zero é singular em pt_BR')
        self.assertEqual(i18n.LANGUAGES['en']['plural'](0), 1, 'zero é plural em inglês')

    def test_helper_answers_zero_one_and_two_in_both_languages(self):
        cases = (
            ('pt_BR', ('{days} dia', '{days} dia', '{days} dias')),
            ('en', ('{days} days', '{days} day', '{days} days')),
        )
        for code, expected in cases:
            i18n.activate(code)
            for n, form in zip((0, 1, 2), expected):
                self.assertEqual(i18n._n('{days} day', '{days} days', n), form, (code, n))
        # E a regra da tabela escolhe a mesma forma que o gettext do catálogo: aplicada às
        # formas reais de cada idioma, dá o que `_n` devolve — é o que garante que painel e
        # janela não escolhem formas diferentes para o mesmo número.
        for code, forms in (('pt_BR', ('{days} dia', '{days} dias')),
                            ('en', ('{days} day', '{days} days'))):
            i18n.activate(code)
            for n in (0, 1, 2, 5, 11, 100):
                self.assertEqual(i18n._n('{days} day', '{days} days', n),
                                 forms[i18n.LANGUAGES[code]['plural'](n)], (code, n))


class LanguageResolutionTests(unittest.TestCase):
    def tearDown(self):
        with patch.dict('os.environ', {'LANGUAGE': 'en', 'LC_ALL': 'en', 'LANG': 'en'}):
            i18n.activate()

    def test_explicit_setting_beats_the_environment(self):
        with patch.dict('os.environ', {'LANGUAGE': 'en_US.UTF-8'}):
            self.assertEqual(i18n.resolve('pt_BR'), 'pt_BR')
            self.assertEqual(i18n.resolve('pt-BR'), 'pt_BR')

    def test_environment_follows_the_gettext_order(self):
        """Ambiente misto resolve igual nos dois runtimes — é a regra do gettext.

        `LANGUAGE` manda sozinha: definida, o gettext ignora LC_ALL, LC_MESSAGES e LANG. Sem
        ela, vale a primeira variável definida. Antes o backend percorria as quatro e juntava
        candidatos: com LANGUAGE=fr_FR e LC_ALL=pt_BR.UTF-8 o painel respondia inglês (regra do
        GLib) e o backend respondia português — o mesmo usuário, dois idiomas, cada um numa
        janela. O inglês aqui não é capricho: é o que o resto do desktop mostra nesse ambiente.
        """
        cases = (
            ({'LANGUAGE': 'fr_FR', 'LC_ALL': 'pt_BR.UTF-8', 'LANG': 'pt_BR.UTF-8'}, 'en'),
            ({'LANGUAGE': 'fr_FR:pt_BR', 'LANG': 'en_US.UTF-8'}, 'pt_BR'),
            ({'LANGUAGE': 'pt_BR:en', 'LC_ALL': 'en_US.UTF-8', 'LANG': 'en_US.UTF-8'}, 'pt_BR'),
            ({'LC_ALL': 'pt_BR.UTF-8', 'LANG': 'en_US.UTF-8'}, 'pt_BR'),
            ({'LC_MESSAGES': 'pt_BR.UTF-8', 'LANG': 'en_US.UTF-8'}, 'pt_BR'),
            ({'LANGUAGE': '   ', 'LANG': 'pt_BR.UTF-8'}, 'pt_BR'),
            ({'LANG': 'pt_BR.UTF-8'}, 'pt_BR'),
            ({'LANG': 'C'}, 'en'),
            # Desvio deliberado do gettext nativo, documentado em docs/i18n.md: pedido explícito
            # em LANGUAGE vale mesmo com LC_ALL=C. O applet exporta o idioma fixado por LANGUAGE
            # justamente para os filhos, e painel e janela não podem discordar.
            ({'LANGUAGE': 'pt_BR', 'LC_ALL': 'C', 'LANG': 'C'}, 'pt_BR'),
            ({'LANG': 'pt_BR.UTF-8@euro'}, 'pt_BR'),
            ({}, 'en'),
        )
        for env, expected in cases:
            with patch.dict('os.environ', env, clear=True):
                self.assertEqual(i18n.resolve(), expected, env)

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

    def test_identical_translation_is_an_entry_not_a_miss(self):
        """Tradução idêntica ao original é entrada presente — não entrada ausente.

        `{hours} h` está no catálogo com o mesmo texto nos dois idiomas. Comparar a tradução
        com o msgid dava essa entrada como ausente: o registro sintético com `hours=3` e texto
        residual `99 h` saía `99 h` no backend e `3 h` no painel. Quem decide é a presença da
        entrada no catálogo, e aí o identificador com os argumentos vence nos dois runtimes.
        """
        catalog = i18n._load('pt_BR')
        self.assertTrue(i18n._has_entry(catalog, '{hours} h'),
                        'a premissa deste teste é a entrada existir com tradução idêntica')
        self.assertEqual(catalog.gettext('{hours} h'), '{hours} h')
        record = {'label_id': '{hours} h', 'label_args': {'hours': 3}, 'label': '99 h'}
        for code, expected in (('pt_BR', '3 h'), ('en', '3 h')):
            i18n.activate(code)
            self.assertEqual(i18n.record_text(record, 'label_id', 'label_args', 'label'),
                             expected, code)
        record['label_args'] = {'hours': 1}
        i18n.activate('pt_BR')
        self.assertEqual(i18n.record_text(record, 'label_id', 'label_args', 'label'), '1 h')

    def test_presence_check_reads_the_compiled_catalog(self):
        """A checagem de presença lê o .mo de verdade, não uma lista escrita à mão.

        Ela consulta o mapa interno do `GNUTranslations` (leitura apenas). Se o Python deixar
        de expô-lo, a checagem responde "ausente" para tudo e este teste falha — em vez de a
        interface perder o identificador e voltar ao texto gravado sem ninguém notar.
        """
        catalog = i18n._load('pt_BR')
        for msgid in ('Update', 'Critical quota', '{hours} h'):
            self.assertTrue(i18n._has_entry(catalog, msgid), msgid)
        self.assertFalse(i18n._has_entry(catalog, 'This msgid is not in the catalog'))
        # Idioma sem catálogo não tem entrada nenhuma: lá o identificador é a própria frase.
        self.assertFalse(i18n._has_entry(None, 'Update'))
        # Entrada com plural não vale como identificador: falta o número para escolher a
        # forma, e devolver sempre a primeira diria "1 dia" no lugar de "3 dias".
        self.assertFalse(i18n._has_entry(catalog, '{days} day'))
        self.assertEqual(catalog.ngettext('{days} day', '{days} days', 3), '{days} dias')
        plural_record = {'label_id': '{days} day', 'label_args': {},
                         'label': '3 dias'}
        self.assertEqual(i18n.record_text(plural_record, 'label_id', 'label_args', 'label'),
                         '3 dias')


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
