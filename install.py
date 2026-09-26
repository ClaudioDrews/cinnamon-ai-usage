#!/usr/bin/env python3
"""Install a reviewed local copy. Does not enable the applet or restart Cinnamon."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import tempfile

UUID = 'ai-usage@claudio.local'
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

def install(destination):
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
    print('Abra as configurações de Applets do Cinnamon e adicione Uso de IA ao painel.')
    return target

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', default=str(Path.home()/'.local/share/cinnamon/applets'))
    install(parser.parse_args().destination)
