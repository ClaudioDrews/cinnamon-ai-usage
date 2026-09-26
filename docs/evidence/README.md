# Evidence

The four GTK captures and the dumps in this directory are the artefacts this round is
checked against. Every path is relative to the repository root; none of them is a path
of the machine that produced them, and none of the images carries real account data.

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
  person reads in Portuguese. The third has no Portuguese left in the visible text.
- `texts-credentials-en.json`, `texts-credentials-pt_BR.json` — every text the credentials
  window shows, read from the widget tree by the capture harness: title, section labels,
  buttons, status lines and field examples.

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
  and requires the same id and the rise in consumption to be seen.
- **The visible text in Portuguese is unchanged** — the byte-identical dump above, against
  the commit that was reviewed.
