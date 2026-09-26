#!/bin/sh
# Monta a árvore que o repositório do Spices espera, para o PR do applet.
#
# Por que uma árvore separada, e não o repositório como está: o Cinnamon instala apenas o
# que estiver dentro de `files/UUID`, o validador do Spices recusa o campo `icon` no
# metadata.json, exige `icon.png` quadrado — e recusa o `.mo` compilado, que é justamente
# o que o `locale/` do projeto guarda. O `.po` e o `.pot` vão para `files/UUID/po/`, de
# onde o instalador do Spices os compila para `~/.local/share/locale` (a segunda pasta de
# catálogo dos dois leitores do applet), e é isso que traduz também a lista de applets e
# o diálogo de Preferências, que o Cinnamon resolve por conta própria.
#
# Uso: sh scripts/spices.sh [destino]   (padrão: build/spice; PYTHON=... para escolher o interpretador)
#      VALIDATE_SPICE=/caminho/do/validate-spice sh scripts/spices.sh
#
# Idempotente: o destino é apagado antes de ser montado de novo.
set -eu
cd "$(dirname "$0")/.."

UUID='ai-usage@claudio.drews'
DEST="${1:-build/spice}"
RAIZ="$DEST/$UUID"
APP="$RAIZ/files/$UUID"

rm -rf "$DEST"
mkdir -p "$APP/po" "$APP/backend" "$APP/assets"

# Arquivos de execução do applet: a mesma lista que o install.py copia, menos `locale/`.
for nome in applet.js metadata.json settings-schema.json stylesheet.css; do
    cp "applet/$nome" "$APP/$nome"
done
cp -r backend/. "$APP/backend/"
cp -r assets/. "$APP/assets/"
find "$APP/backend" -name __pycache__ -type d -prune -exec rm -rf {} +

# O validador do Spices confere o pacote por fora e não olha o interior de files/UUID:
# um caminho errado aqui passa por ele e só aparece na instalação. Estas conferências
# são a parte que o validador não faz.
for obrigatorio in applet.js metadata.json settings-schema.json stylesheet.css \
                  backend/collector.py backend/i18n.py backend/providers.py \
                  assets/robot-head-symbolic.svg; do
    [ -s "$APP/$obrigatorio" ] || { echo "Falta $obrigatorio no pacote (caminho errado?)." >&2; exit 1; }
done

# O catálogo vai como fonte: `.po` e `.pot` juntos em po/, nunca compilado.
cp locale/pt_BR.po "$APP/po/pt_BR.po"
cp "locale/$UUID.pot" "$APP/po/$UUID.pot"

# O ícone do pacote é PNG e quadrado (exigência do validador). O material do projeto é o
# robô simbólico, que no painel segue a cor do tema; aqui vale a forma.
gerar_icone() {
    for ferr in inkscape rsvg-convert convert; do
        command -v "$ferr" >/dev/null 2>&1 || continue
        case "$ferr" in
            inkscape)
                "$ferr" --export-type=png --export-filename="$APP/icon.png" \
                        --export-width=256 --export-height=256 \
                        assets/robot-head-symbolic.svg >/dev/null 2>&1 ;;
            rsvg-convert)
                "$ferr" -w 256 -h 256 -o "$APP/icon.png" assets/robot-head-symbolic.svg ;;
            convert)
                "$ferr" -background none -resize 256x256 \
                        assets/robot-head-symbolic.svg "$APP/icon.png" ;;
        esac
        [ -s "$APP/icon.png" ] && return 0
    done
    return 1
}
gerar_icone || { echo "Sem inkscape, rsvg-convert ou convert: não consegui gerar o icon.png." >&2; exit 1; }

# O campo `icon` é proibido no metadata.json do pacote (o ícone é o arquivo ao lado).
"${PYTHON:-python3}" - "$APP/metadata.json" <<'PY'
import json, sys
caminho = sys.argv[1]
with open(caminho, encoding='utf-8') as arquivo:
    dados = json.load(arquivo)
dados.pop('icon', None)
with open(caminho, 'w', encoding='utf-8') as arquivo:
    json.dump(dados, arquivo, ensure_ascii=False, indent=2)
    arquivo.write('\n')
PY

# No topo do pacote: o que o revisor e o site do Spices leem.
printf '{\n    "author": "ClaudioDrews",\n    "license": "MIT"\n}\n' > "$RAIZ/info.json"
cp docs/demo.png "$RAIZ/screenshot.png"
cp README.md LICENSE "$RAIZ/"

# Conferências locais que não dependem do validador externo.
if find "$RAIZ" -name '*.mo' | grep -q .; then
    echo "Catálogo compilado dentro do pacote: o Spices recusa. Nada foi publicado." >&2
    exit 1
fi
if [ ! -s "$APP/po/$UUID.pot" ] || [ ! -s "$APP/po/pt_BR.po" ]; then
    echo "Faltou .po ou .pot em po/: o validador exige os dois." >&2
    exit 1
fi

VALIDADOR="${VALIDATE_SPICE:-$(command -v validate-spice 2>/dev/null || true)}"
if [ -n "$VALIDADOR" ]; then
    ( cd "$DEST" && "${PYTHON:-python3}" "$VALIDADOR" "$UUID" )
else
    echo "Validador do Spices não encontrado (VALIDATE_SPICE ou validate-spice no PATH)." >&2
    echo "Para conferir antes do PR: git clone https://github.com/linuxmint/cinnamon-spices-applets" >&2
    echo "e rode: (cd $DEST && python3 <clone>/validate-spice $UUID)" >&2
fi

echo "Pacote em: $DEST"
find "$RAIZ" -maxdepth 2 -type f | sort | sed 's/^/  /'
