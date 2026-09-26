#!/usr/bin/env python3
"""Install a reviewed local copy. Does not enable the applet or restart Cinnamon."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile

UUID = 'ai-usage@claudio.drews'
ROOT = Path(__file__).resolve().parent

def readable_for_users(path):
    """Diretórios 0755 e arquivos 0644.

    O staging nasce de ``mkdtemp``, que cria em 0700: sem o ajuste, uma instalação em
    ``/usr/share/cinnamon/applets`` ficaria legível só pelo root e o applet não carregaria
    para os demais usuários. O padrão das pastas de applet do sistema é 0755.
    """
    for base, directories, files in os.walk(path):
        os.chmod(base, 0o755)
        for name in directories:
            os.chmod(Path(base)/name, 0o755)
        for name in files:
            os.chmod(Path(base)/name, 0o644)

def install_catalogs(destination):
    """Instala os catálogos onde o shell do Cinnamon os procura.

    O shell liga o domínio gettext do xlet a ``~/.local/share/locale``
    (``appletManager.js``) e não há como apontá-lo para dentro do applet: sem o
    ``.mo`` ali, o applet, o nome/descrição na lista de Applets e os rótulos das
    preferências ficam em inglês. A cópia dentro do applet serve ao backend Python,
    que procura primeiro no próprio ``locale/``.

    Devolve os caminhos gravados, para a instalação poder dizer o que fez.
    """
    written = []
    for source in sorted((ROOT/'locale').glob('*/LC_MESSAGES/*.mo')):
        language = source.parent.parent.name
        target = Path(destination).expanduser()/language/'LC_MESSAGES'/source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(0o644)
        written.append(target)
    return written

def install(destination, locale_destination=None):
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / UUID
    # Staging FORA da pasta de applets: criado dentro dela, o Cinnamon o enxerga como um
    # applet fantasma enquanto os arquivos são copiados.
    stage = Path(tempfile.mkdtemp(prefix='.ai-usage-stage-', dir=destination.parent))
    try:
        for name in ('applet.js', 'metadata.json', 'settings-schema.json', 'stylesheet.css'):
            shutil.copy2(ROOT/'applet'/name, stage/name)
        shutil.copytree(ROOT/'backend', stage/'backend', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copytree(ROOT/'assets', stage/'assets')
        shutil.copytree(ROOT/'locale', stage/'locale')
        shutil.copy2(ROOT/'README.md', stage/'README.md')
        shutil.copy2(ROOT/'LICENSE', stage/'LICENSE')
        readable_for_users(stage)
        if target.exists() or target.is_symlink():
            backups = destination.parent/'ai-usage-backups'
            backups.mkdir(exist_ok=True)
            backup = backups/(UUID+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            target.rename(backup)
            print('Cópia anterior preservada em:', backup)
        stage.rename(target)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    print('Instalado em:', target)
    catalogs = install_catalogs(locale_destination
                                or Path.home()/'.local/share/locale')
    for path in catalogs:
        print('Catálogo instalado em:', path)
    print('Abra as configurações de Applets do Cinnamon e adicione Uso de IA ao painel.')
    return target

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', default=str(Path.home()/'.local/share/cinnamon/applets'))
    parser.add_argument('--locale-destination', default=None,
                        help='onde gravar os catálogos (padrão: ~/.local/share/locale)')
    arguments = parser.parse_args()
    install(arguments.destination, arguments.locale_destination)
