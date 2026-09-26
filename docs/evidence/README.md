# Evidence

The four GTK captures and the dumps in this directory are the artefacts this round is
checked against. Every path is relative to the repository root; none of them is a path
of the machine that produced them, and none of the images carries real account data.

## Isolation

`tests/isolation.py` builds the isolation of both harnesses instead of asserting it. The
run works inside an exclusive sandbox under `/tmp` with `HOME` and every `XDG_*` path
pointed at it and the credential variables taken out of the environment, and a fixture
takes the place of the system keyring, the indicated credential file, the network, the
local executables, the process table (`providers.local_server_processes`) and the worker
process of the collection (`collector.worker`/`collector.launch_worker`). `assert_clean()`
fails the run that stops going through a fixture or that reaches the network, the keyring,
a local binary or a real process; the summary of what was substituted goes to **stderr**,
so stdout stays byte-comparable; the sandbox is removed at the end of the run. An earlier
version of these harnesses pointed only `XDG_CONFIG_HOME`/`XDG_CACHE_HOME` at a temporary
directory and claimed the same isolation while the keyring, the credential variables, the
login files and the `codex` installed on the machine were still reachable — the versioned
dump itself recorded Codex as `ok` in the section that says "no configuration".

Running the current harness against a tree older than the two seams reports the missing
seam on stderr (`providers.local_server_processes`, `collector.launch_worker`) instead of
hiding it. `tests/test_evidence_isolation.py` proves the whole thing: the dump comes out
identical with credentials planted in the environment and a fake `codex` on the `PATH`,
and the guard rejects a network query, a read outside the sandbox and a write to the
keyring.

## The four GTK captures

| what | language | path |
| --- | --- | --- |
| usage window, demonstration with the nine services | English | `docs/demo.png` |
| usage window, demonstration with the nine services | pt_BR | `docs/demo.pt-BR.png` |
| credentials window, synthetic configuration | English | `docs/evidence/window-credentials-en.png` |
| credentials window, synthetic configuration | pt_BR | `docs/evidence/window-credentials-pt_BR.png` |

Reproduced with a graphical session, without installing, activating or reloading the
applet in the panel:

```
$ LANGUAGE=pt_BR.UTF-8 python3 tests/smoke_gtk.py docs/demo.pt-BR.png
$ LANGUAGE=en.UTF-8     python3 tests/smoke_gtk.py docs/demo.png
$ LANGUAGE=pt_BR.UTF-8 python3 tests/smoke_gtk_credentials.py \
      docs/evidence/window-credentials-pt_BR.png docs/evidence/texts-credentials-pt_BR.json
$ LANGUAGE=en.UTF-8     python3 tests/smoke_gtk_credentials.py \
      docs/evidence/window-credentials-en.png docs/evidence/texts-credentials-en.json
```

Both harnesses activate the language the same way the product does and refuse to write a
capture when the resolved language does not show up in the widgets — a capture that
proves nothing fails the run instead of being filed as evidence.

## The dumps

- `text-de3b6b7-pt_BR.json`, `text-after-pt_BR.json`, `text-after-en.json` — canonical
  visible text, from `tests/dump_visible_text.py`: the demonstration with the nine
  services (labels, messages, origins, metric labels), the diagnostics of every service
  and a collection with no configuration at all. Dates and numbers are out on purpose, so
  the dump changes when a translated text changes. The first two are byte-identical
  (`diff` is empty): the corrections changed what the collection *stores*, not what a
  person reads in Portuguese. The third has no Portuguese left in the visible text. The
  line of the Codex diagnostics is the only one that changed when the isolation was fixed
  — before it, the `codex` of the machine answered and the dump said `ok` in the section
  with no configuration.
- `texts-credentials-en.json`, `texts-credentials-pt_BR.json` — every text the credentials
  window shows, read from the widget tree by the capture harness: title, section labels,
  buttons, status lines and field examples. One line carries the path of the sandbox of
  the run, which is different every time; the rest of the file is what is compared.

The "before" (`text-de3b6b7-pt_BR.json`) is produced by running the **current** harness
against a checkout of the old commit, inside the same isolation:

```
$ mkdir <dir> && git archive de3b6b7 | tar -x -C <dir>
$ LANGUAGE=pt_BR.UTF-8 python3 tests/dump_visible_text.py <dir> > docs/evidence/text-de3b6b7-pt_BR.json
```

The three `text-*.json` are byte-comparable across runs (`cmp` is empty), in either
direction of the harness: with no argument it dumps the tree it lives in, with a directory
it dumps that tree. The isolation summary never reaches stdout.

## What each artefact answers to

- **Storage keeps raw data, the presentation writes it** — `text-after-*.json` show the
  same reading in both languages from one collection, and
  `tests/test_i18n_providers.py::MessageIdentifierTests::test_the_same_record_reads_in_every_language_without_recollecting`
  walks Portuguese → English → Portuguese over a single record with a fractional window,
  a plan, a percentage above 100% and an origin. Both captures of the usage window show
  the same origin line in each language, which is what `Source: {source}` resolving an
  identifier looks like on screen.
- **The technical identifier does not follow the language** —
  `tests/test_backend.py::HistoryTests::test_the_antigravity_identifier_survives_a_language_change`
  compares two readings of the same quota, one collected in Portuguese and one in English,
  and requires the same id and the rise in consumption to be seen; the named model and the
  reading the previous version left on disk are covered by
  `tests/test_backend.py::HistoryTests::test_the_named_model_identifier_keeps_the_one_the_previous_version_saved`.
- **The visible text in Portuguese is unchanged** — the byte-identical dump above, against
  the commit that was reviewed.
- **The evidence does not depend on this machine** —
  `tests/test_evidence_isolation.py::DumpInvarianceTests::test_the_dump_is_the_same_with_credentials_in_the_environment_and_a_fake_codex`
  runs the dump twice, once with credentials in the environment and a fake `codex` on the
  `PATH`, and requires the two outputs to be equal.
