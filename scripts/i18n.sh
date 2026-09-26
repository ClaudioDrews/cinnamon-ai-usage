#!/bin/sh
# Extrai os msgids, atualiza o catálogo pt_BR e compila o .mo.
#
# O comando é idempotente: rodar de novo depois de traduzir (ou de acrescentar
# string nova no código) não perde tradução — o msgmerge casa por msgid e só
# acrescenta as entradas novas, vazias, para alguém preencher.
#
# O .mo é versionado de propósito: quem instala o applet a partir do repositório
# não tem xgettext nem msgfmt na máquina, e o shell do Cinnamon lê .mo, não .po.
set -eu
cd "$(dirname "$0")/.."

DOMAIN='ai-usage@claudio.drews'
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT INT TERM

# '--from-code=UTF-8' porque o texto tem acento, travessão e reticências.
xgettext --from-code=UTF-8 --language=JavaScript --keyword=_ \
    -o "$WORK/applet.pot" applet/applet.js
xgettext --from-code=UTF-8 --language=Python --keyword=_ --keyword=_t --keyword=_n:1,2 \
    -o "$WORK/backend.pot" backend/*.py
# Sem --location: o arquivo que o gerador produz fica em diretório temporário e a
# referência levaria o caminho desta máquina para dentro do catálogo versionado.
python3 scripts/xlet_strings.py > "$WORK/xlet_strings.py"
xgettext --from-code=UTF-8 --language=Python --keyword=_ --no-location \
    -o "$WORK/xlet.pot" "$WORK/xlet_strings.py"

msgcat -o "locale/$DOMAIN.pot" "$WORK/applet.pot" "$WORK/backend.pot" "$WORK/xlet.pot"
msgmerge --quiet --update --backup=none "locale/pt_BR.po" "locale/$DOMAIN.pot"
mkdir -p "locale/pt_BR/LC_MESSAGES"
msgfmt --check --statistics -o "locale/pt_BR/LC_MESSAGES/$DOMAIN.mo" locale/pt_BR.po

echo "msgids no template: $(msgattrib --no-obsolete --no-fuzzy locale/$DOMAIN.pot | grep -c '^msgid ')"
echo "catálogo compilado: locale/pt_BR/LC_MESSAGES/$DOMAIN.mo"
