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


if __name__ == '__main__':
    unittest.main()
