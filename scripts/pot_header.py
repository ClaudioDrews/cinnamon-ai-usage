#!/usr/bin/env python3
"""Reescreve o cabeçalho do template .pot no formato que os applets da loja usam.

O `msgcat` que junta os quatro catálogos (applet, backend, xlet e instalador) monta um
cabeçalho com as quatro versões empilhadas e as linhas `#-#-#-#-#` do próprio merge, o
que o `Project-Id-Version` duplicado denuncia. Aqui o cabeçalho é refeito a partir do
`applet/metadata.json`, com as mesmas linhas de comentário dos outros applets do Spices
(nome, domínio público, autor e ano) e o endereço de issues da loja.

Sem `POT-Creation-Date`: o .pot é versionado e a data mudaria a árvore a cada execução,
que é o mesmo motivo pelo qual o i18n.sh já apagava essa linha.

Uso: python3 scripts/pot_header.py locale/<uuid>.pot applet/metadata.json
"""
import json
import pathlib
import sys
from datetime import date

CABECALHO = """\
# {nome}
# This file is put in the public domain.
# {autor}, {ano}
#
#, fuzzy
msgid ""
msgstr ""
"Project-Id-Version: {uuid} {versao}\\n"
"Report-Msgid-Bugs-To: https://github.com/linuxmint/cinnamon-spices-applets/issues\\n"
"PO-Revision-Date: \\n"
"Last-Translator: \\n"
"Language-Team: \\n"
"Language: \\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"""


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Uso: python3 scripts/pot_header.py locale/<uuid>.pot applet/metadata.json")
    destino = pathlib.Path(sys.argv[1])
    meta = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))

    texto = destino.read_text(encoding="utf-8")
    # O cabeçalho é sempre a primeira entrada do arquivo: vai do início até a primeira
    # linha em branco. O resto do catálogo fica intacto.
    corte = texto.find("\n\n")
    if corte < 0:
        raise SystemExit(f"{destino}: não encontrei o fim do cabeçalho")
    corpo = texto[corte + 2:]

    cabecalho = CABECALHO.format(
        nome=meta["name"].upper(),
        autor=meta.get("author", "ClaudioDrews"),
        ano=date.today().year,
        uuid=meta["uuid"],
        versao=meta.get("version", "0.0.0"),
    )
    destino.write_text(cabecalho + "\n" + corpo, encoding="utf-8")
    print(f"cabeçalho do template: {meta['uuid']} {meta.get('version', '0.0.0')}")


if __name__ == "__main__":
    main()
