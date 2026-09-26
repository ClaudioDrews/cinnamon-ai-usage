"""O pacote do Spices leva o README próprio da loja, não o do repositório.

O site do Spices mostra o README da raiz do pacote sem o resto do repositório:
link relativo (docs/, applet/) quebra, e instrução com install.py não faz sentido
para quem instala pelo Cinnamon. O teste monta o pacote num diretório
temporário e confere o texto e o mínimo do layout que o revisor vê.
"""
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
UUID = 'ai-usage@claudio.drews'
REPO = 'https://github.com/ClaudioDrews/cinnamon-ai-usage'
ICON_TOOLS = ('inkscape', 'rsvg-convert', 'convert')


def has_icon_tool():
    return any(shutil.which(tool) for tool in ICON_TOOLS)


class SpicesPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not has_icon_tool():
            raise unittest.SkipTest('sem inkscape, rsvg-convert ou convert')
        cls.tmp = tempfile.TemporaryDirectory(prefix='spice-pkg-')
        cls.addClassCleanup(cls.tmp.cleanup)
        subprocess.run(['sh', str(ROOT/'scripts/spices.sh'), cls.tmp.name],
                       cwd=ROOT, capture_output=True, check=True)
        cls.pkg = Path(cls.tmp.name)/UUID
        cls.app = cls.pkg/'files'/UUID

    def test_package_readme_is_the_store_text(self):
        packaged = (self.pkg/'README.md').read_bytes()
        self.assertEqual(packaged, (ROOT/'spice/README.md').read_bytes())

    def test_package_readme_has_no_relative_link_nor_installer(self):
        text = (self.pkg/'README.md').read_text(encoding='utf-8')
        for relative in re.findall(r'\]\((?!https?://|#|mailto:)([^)]*)\)', text):
            self.fail('link relativo no README da loja: %r' % relative)
        self.assertNotIn('install.py', text)
        self.assertIn(REPO, text)

    def test_portuguese_store_text_exists_with_absolute_links(self):
        source = ROOT/'spice/README.pt-BR.md'
        self.assertTrue(source.is_file())
        text = source.read_text(encoding='utf-8')
        for relative in re.findall(r'\]\((?!https?://|#|mailto:)([^)]*)\)', text):
            self.fail('link relativo no texto em português: %r' % relative)
        self.assertNotIn('install.py', text)
        self.assertIn(REPO, text)

    def test_layout_basics_the_reviewer_sees(self):
        metadata = json.loads((self.app/'metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['uuid'], UUID)
        self.assertNotIn('icon', metadata)
        self.assertFalse(list(self.pkg.rglob('*.mo')))
        header = (self.app/'icon.png').read_bytes()
        width, height = struct.unpack('>II', header[16:24])
        self.assertEqual((width, height), (256, 256))

    def test_what_the_applet_needs_is_inside_files_uuid(self):
        """O validador não desce em files/UUID: caminho errado aqui só aparece na instalação.

        O caso real que motivou este teste: `cp -r backend` num destino que já existe aninha
        `backend/backend/`, o applet fica sem backend e o validador responde "No errors found".
        """
        for obrigatorio in ('applet.js', 'metadata.json', 'settings-schema.json', 'stylesheet.css',
                            'backend/collector.py', 'backend/i18n.py', 'backend/providers.py',
                            'assets/robot-head-symbolic.svg'):
            self.assertTrue((self.app/obrigatorio).is_file(), obrigatorio)
        self.assertFalse((self.app/'backend/backend').exists(), 'backend aninhado no pacote')

    def test_catalog_travels_as_source(self):
        """Sem o .pot ao lado o validador recusa o pacote; sem o .po não há tradução nenhuma."""
        self.assertTrue((self.app/'po'/f'{UUID}.pot').is_file())
        self.assertTrue((self.app/'po'/'pt_BR.po').is_file())
        self.assertFalse((self.app/'locale').exists(), 'locale/ do projeto não vai no pacote')

    def test_store_root_has_what_a_reviewer_reads(self):
        info = json.loads((self.pkg/'info.json').read_text(encoding='utf-8'))
        self.assertEqual(info['author'], 'ClaudioDrews')
        self.assertNotIn(' ', info['author'])
        self.assertTrue((self.pkg/'screenshot.png').is_file())
        self.assertTrue((self.pkg/'LICENSE').is_file())


if __name__ == '__main__':
    unittest.main()
