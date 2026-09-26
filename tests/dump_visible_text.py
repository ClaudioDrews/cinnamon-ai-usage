#!/usr/bin/env python3
"""Dump the text a person reads, to compare one tree against another in the same language.

Canonical and deterministic: it walks the demonstration with the nine services (labels,
messages, sources, metric labels), the diagnostics of every service, and a collection with no
configuration at all. Numbers and dates are left out on purpose, so the dump changes only when
a translated text changes.

**The isolation is built, not assumed** (see `isolation.py`): `HOME` and every `XDG_*` path of
the run point at an exclusive temporary directory under `/tmp`, the credential variables leave
the environment, and the system keyring, the credential file, the network, the local
executables, the process table and the worker process of the collection are all replaced by
fixtures. That is what "no configuration" means here: no credential of this machine, no query
to any service, no local binary. A run that reaches any of them fails instead of writing a
dump that claims an isolation it does not have. The earlier version of this harness pointed
only `XDG_CONFIG_HOME`/`XDG_CACHE_HOME` elsewhere and wrote Codex as `ok` in this very section,
because the `codex` installed on the machine answered the query.

The language comes from the environment, as in the product (`LANGUAGE=pt_BR.UTF-8`):

    LANGUAGE=pt_BR.UTF-8 python3 tests/dump_visible_text.py [tree] > text-pt_BR.json

With no argument it dumps the tree this script lives in; pass another directory to dump a
checkout of an older commit (`git archive <commit> | tar -x -C <dir>`) for the before/after
comparison. The stderr line reports what the isolation substituted, so a reader can see the
run went through the fixtures; stdout stays byte-comparable.
"""
import json
import sys
from pathlib import Path

aqui = Path(__file__).resolve().parent
arvore = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else aqui.parent
sys.path.insert(0, str(aqui))

from isolation import Isolation

with Isolation(tree=arvore) as iso:
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

    # Antes de qualquer saída: o dump só é escrito se o isolamento afirmado for o que houve.
    iso.assert_clean()

print(json.dumps(saida, ensure_ascii=False, sort_keys=True, indent=1))
print(iso.report(), file=sys.stderr)
