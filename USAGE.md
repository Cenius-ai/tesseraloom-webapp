# Using TesseraLoom

Three commands, one shared grid loader, one shared color numbering.

```bash
python3 tesseraloom.py --help          # commands, input forms, flags, exit codes
python3 tesseraloom.py <cmd> --help    # per-command help
```

The grid source is always the optional first positional argument:

| Form | Meaning |
| --- | --- |
| `grid.txt` | read the design from that file |
| `-` | read the design from stdin |
| omitted | read the design from stdin (same as `-`) |

If stdin is a terminal and no path was given, the tool refuses with one line
instead of hanging: `no grid on stdin; pass a grid PATH, use '-' for stdin, or
pipe a grid in`.

## layout — the numbered map

```bash
python3 tesseraloom.py layout sample_grid.txt --legend legend.txt
```

- the map keeps the grid's rows and columns; each code becomes its color number,
  right-aligned to the width of the largest number so multi-digit numbers do not
  break the shape;
- a single blank line separates the map from the legend;
- the legend lists number, code, and — when `--legend` is supplied — the name;
- numbers are assigned by first appearance (row by row, left to right), so
  `K B A / B A Z` numbers `K=1 B=2 A=3 Z=4` — not alphabetical.

### Undefined codes

`--legend PATH` is an independent known-code list (`CODE [name]` per line).
Any grid code missing from it produces exactly one warning on stderr, naming the
code and its first row and column, and the map still prints:

```
$ python3 tesseraloom.py layout examples/design_garden.txt --legend legend.txt
...
1  CRM  Crimson
2  GLD  Old gold
3  SGE
4  STN
tesseraloom: warning: undefined code SGE (first seen at row 2, column 2); not in legend.txt
tesseraloom: warning: undefined code STN (first seen at row 5, column 5); not in legend.txt
$ echo $?
0
```

Warnings are deduplicated per code: a code filling forty cells warns once.

## count — tiles per color

```bash
python3 tesseraloom.py count sample_grid.txt
```

```
NUM  CODE  COUNT
  1  WHT      36
  2  SLT      20
  3  CRM      22
  4  GLD      14
  5  IND       4
TOTAL 96
```

Rows follow color-number order; the last line is `TOTAL <n>`.

## cutlist — grouped cut list, text or CSV

```bash
python3 tesseraloom.py cutlist sample_grid.txt --legend legend.txt
python3 tesseraloom.py cutlist sample_grid.txt --format csv
python3 tesseraloom.py cutlist sample_grid.txt --format csv --out cutlist.csv
```

Text (the default — omitting `--format` gives byte-identical output to
`--format text`):

```
NUM  CODE  NAME         COUNT
  1  WHT   Chalk white     36
  ...
TOTAL 96
```

The name column is `-` when no `--legend` was given, and `undefined` when a legend
was given that does not define the code (which also warns on stderr).

CSV (`--format csv`) uses the header `number,code,name,count` and ends with the
row `TOTAL,,,96`; fields containing commas, quotes or newlines are quoted by the
`csv` module, so names like `Crimson, deep` survive a round trip.

`--out PATH` writes exactly the bytes that would have gone to stdout — stdout
stays empty. If the path cannot be written (missing directory, permission,
a directory), nothing is created and one line is printed:

```
$ python3 tesseraloom.py cutlist sample_grid.txt --out /no/such/dir/out.csv
tesseraloom: cannot write /no/such/dir/out.csv: no such directory
$ echo $?
1
```

## Piping

Because results go to stdout and warnings/errors to stderr, the tool is
pipeline-safe:

```bash
cat design.txt | python3 tesseraloom.py cutlist - --format csv > cutlist.csv
python3 tesseraloom.py count design.txt 2>/dev/null | tail -1     # TOTAL only
```

## Exit codes

| Code | Meaning | Example |
| --- | --- | --- |
| 0 | success, warnings included | `cutlist` with an undefined code |
| 1 | input/output error | ragged row, blank row, empty grid, missing file, unwritable `--out` |
| 2 | usage error | no command, unknown command or flag, `--format xml` |

Every error is exactly one stderr line; there are no tracebacks.

## Errors you can expect

```
tesseraloom: no such file: nope.txt
tesseraloom: grid.txt: row 3 has 5 codes, expected 3; the grid must be a rectangle
tesseraloom: grid.txt: row 2 is empty; every row needs at least one tile code
tesseraloom: grid is empty; pass a grid PATH, use '-' for stdin, or pipe a grid in
tesseraloom: no such legend file: legend.txt
tesseraloom: cannot write /no/such/dir/out.csv: no such directory
tesseraloom: unknown format: xml (allowed formats are text and csv) (see --help)
tesseraloom: unknown command: frobnicate (commands are layout, count, cutlist) (see --help)
```

## Scale

A 200x200 grid (40,000 tiles) parses, counts and renders in well under a second,
and the same grid and flags always produce byte-identical stdout.
