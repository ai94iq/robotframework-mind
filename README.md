# robotframework-mind

Exact lookups over a Robot Framework test repo, for people and scripts. Ask
which tests cover a ticket, who calls a keyword or where an endpoint is used,
and get one line per hit with its `file:line` instead of reading whole suites.

It indexes:

- tests: name, tags (`bug:PROJ-123`, `role:...`, `op:GET /api/...`), first doc line, keyword calls
- user keywords: name, arguments, first doc line, calls, variables used
- variables from `*** Variables ***` and inline `VAR` statements, with their values
- suite and test setup/teardown calls
- JSON files under `docs/`, one entry per object key

## Requirements

Python 3.10+ and `robotframework` (the repo's own venv already has it). No
other packages.

## Run

From the test repo's venv:

```bash
python path/to/robot_mind.py --root <repo> ticket PROJ-123
python path/to/robot_mind.py --root <repo> kw "Open Profile Browser"
python path/to/robot_mind.py --root <repo> callers "Open Profile Browser"
python path/to/robot_mind.py --root <repo> tag role:role_quality_control
python path/to/robot_mind.py --root <repo> find /api/items/query
```

| Command | Returns |
|---|---|
| `ticket KEY` | tests and keywords whose tags, name or doc mention the key |
| `kw NAME` | every definition, matched the way Robot matches names (case, spaces and underscores ignored) |
| `callers NAME` | each call site: keyword, test or suite fixture, at the call line; falls back to substring when no exact name matches |
| `tag TAG` | tests with that tag; `role:*` matches a prefix |
| `find TEXT` | names, tags, docs, args, values and JSON entries containing the text, then the keywords that use a matching variable |

`--limit N` caps the lines (default 20). No hit prints `no match`. `--json`
prints the hits as a JSON array (each with `kind`, `name`, `file`, `line`; a
`callers` hit also carries `call_line`).

## How it stays current

The index lives in `~/.cache/robotframework-mind/`, one file per repo, never
in the repo. Each call compares file times and sizes and parses only changed
files. In a git repo it reads the files git tracks or would track, so
git-ignored probes and results stay out.

## Tests

```bash
python -m unittest tests.test_where
```

## Credits

The parsing approach follows the Robot Framework extractor in
[graphify](https://github.com/Graphify-Labs/graphify) by Safi Shamsi
(Apache-2.0): Robot's own `robot.api` parser with a `ModelVisitor`, and
keyword names normalized the way Robot resolves them. No graphify code is
copied. See `NOTICE`.
