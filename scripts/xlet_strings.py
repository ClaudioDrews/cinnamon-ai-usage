#!/usr/bin/env python3
"""Imprime, em Python sintaticamente válido, as strings de metadata.json e
settings-schema.json para o xgettext.

``xgettext`` não lê JSON: sem isto, o nome e a descrição do applet (que o
cinnamon-settings traduz por ``translate(uuid, ...)``) e os rótulos das
preferências ficariam fora do catálogo e a interface de Applets mostraria inglês
para todo mundo. A saída é descartável — existe só para a extração, e o diretório
de trabalho quem cria é ``scripts/i18n.sh``.

Uso: ``python3 scripts/xlet_strings.py`` (texto do programa em stdout).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METADATA = ROOT / "applet/metadata.json"
SCHEMA = ROOT / "applet/settings-schema.json"
LAYOUT_TITLES = ("page", "section")
TRANSLATED_KEYS = ("description", "tooltip", "units")


def xlet_strings() -> list:
    """Toda string que o Cinnamon mostra a partir dos dois JSON, em ordem estável."""
    strings = []
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    for key in ("name", "description"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            strings.append(value)

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    layout = schema.get("layout") or {}
    for page in layout.get("pages") or []:
        block = layout.get(page)
        if not isinstance(block, dict):
            continue
        title = block.get("title")
        if isinstance(title, str) and title.strip():
            strings.append(title)
        for section in block.get("sections") or []:
            section_block = layout.get(section)
            if isinstance(section_block, dict) and isinstance(section_block.get("title"), str):
                strings.append(section_block["title"])
    for key, block in schema.items():
        if key == "layout" or not isinstance(block, dict):
            continue
        for field in TRANSLATED_KEYS:
            value = block.get(field)
            if isinstance(value, str) and value.strip():
                strings.append(value)
        for label in (block.get("options") or {}):
            if isinstance(label, str) and label.strip():
                strings.append(label)
    unique = []
    for text in strings:
        if text not in unique:
            unique.append(text)
    return unique


def main() -> None:
    print("# Gerado por scripts/xlet_strings.py — não é importado por código nenhum.")
    print("# Existe para as strings de metadata.json e settings-schema.json entrarem")
    print("# no catálogo: o xgettext não lê JSON.")
    for text in xlet_strings():
        print("_(" + json.dumps(text, ensure_ascii=False) + ")")


if __name__ == "__main__":
    main()
