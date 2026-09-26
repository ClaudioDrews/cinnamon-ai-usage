#!/usr/bin/env python3
"""Dump the text a person reads, to compare one tree against another in the same language.

Canonical and deterministic: it walks the demonstration with the nine services (labels,
messages, sources, metric labels), the diagnostics of every service, and a collection with no
configuration at all. Numbers and dates are left out on purpose, so the dump changes only when
a translated text changes.

The collection runs with `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` pointing at a temporary
directory: no credential of this machine is read, nothing is written to the real cache, and no
service is queried — "no configuration" means exactly that. The language comes from the
environment, as in the product (`LANGUAGE=pt_BR.UTF-8`).

    LANGUAGE=pt_BR.UTF-8 python3 tests/dump_visible_text.py [tree] > text-pt_BR.json

With no argument it dumps the tree this script lives in; pass another directory to dump a
checkout of an older commit (`git archive <commit> | tar -x -C <dir>`) for the before/after
comparison.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

arvore = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(arvore / "backend"))

sandbox = tempfile.TemporaryDirectory()
os.environ["XDG_CONFIG_HOME"] = sandbox.name
os.environ["XDG_CACHE_HOME"] = sandbox.name

import collector
import i18n
import providers

i18n.activate()
saida = {"demo": [], "diagnosticos": {}, "sem_config": None, "idioma": i18n.language()}

for servico in collector.demo()["services"]:
    saida["demo"].append({
        "id": servico["id"], "label": servico.get("label"), "status": servico["status"],
        "message": servico.get("message"), "source": servico.get("source"),
        "metricas": [{"id": m["id"], "label": m.get("label"), "kind": m["kind"]}
                     for m in servico.get("metrics", [])]})

for servico in sorted(providers.DIAGNOSTICS):
    try:
        saida["diagnosticos"][servico] = providers.diagnose(servico, {})
    except Exception as erro:                      # a falha também é texto a conferir
        saida["diagnosticos"][servico] = {"excecao": type(erro).__name__}

resultado = collector.collect(force=True)
saida["sem_config"] = {"notice": resultado.get("notice"),
                       "servicos": [{"id": s["id"], "status": s["status"],
                                     "message": s.get("message")}
                                    for s in resultado["services"]]}

print(json.dumps(saida, ensure_ascii=False, sort_keys=True, indent=1))
