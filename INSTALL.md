# Installing TesseraLoom

TesseraLoom is a single-file Python command-line tool. Nothing is downloaded at
run time and no service, database or env file is involved.

## 1. Prerequisites (check these first; the installer never installs them)

| Requirement | Why | Check |
| --- | --- | --- |
| Python 3.9+ | the tool is one stdlib-only module | `python3 -V` |
| pip (bundled with Python) | installs the optional `tesseraloom` console script | `python3 -m pip -V` |

No system packages are needed: no compiler, no `libsqlite3-dev`, no Node, no
Docker. The installer never calls `sudo`, `apt`, `apk`, `yum` or `brew`.

## 2. Install project-level dependencies + the console script

```bash
bash install.sh
```

What it does, in order, then exits:

1. `python3 -m pip install --upgrade pip setuptools wheel` (best effort — skipped
   with a note when the machine is offline);
2. `python3 -m pip install -e . --no-build-isolation`, which puts the
   `tesseraloom` command on your `PATH` (falls back to a build-isolated install,
   and warns without failing if neither works — the tool still runs as
   `python3 tesseraloom.py`);
3. `python3 -m pip install -r requirements-dev.txt` (the pytest runner);
4. a self check: `import tesseraloom`, `--version`, and one real `count` run.

`requirements.txt` is intentionally dependency-free: the runtime is the standard
library only. `requirements-dev.txt` pins the test runner (`pytest==9.1.1`).

## 3. Verify

```bash
python3 -m pytest          # 37 tests, no network, no fixtures to fetch
sh demo.sh                 # recorded end-to-end demo over the bundled fixtures
```

## 4. Run in dev

```bash
python3 tesseraloom.py --help
python3 tesseraloom.py layout sample_grid.txt --legend legend.txt
python3 tesseraloom.py cutlist sample_grid.txt --format csv --out cutlist.csv
```

There is no build step, no migration and no seed: the bundled fixtures
(`sample_grid.txt`, `legend.txt`, `examples/`) are the demo data and are read
in place.

## Uninstall

```bash
python3 -m pip uninstall tesseraloom
```

Nothing else was installed and no state was written outside your `--out` paths.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `tesseraloom: command not found` | the console script was not installed; use `python3 tesseraloom.py` or re-run `bash install.sh` |
| `tesseraloom: no grid on stdin; ...` | you ran a command with no path and stdin is a terminal; pass a PATH or pipe the grid (`... \| python3 tesseraloom.py layout -`) |
| `note: could not upgrade pip/...` during install | the machine is offline; everything still works with the installed toolchain |
| `warning: undefined code X ...` and exit code 0 | expected: the code is missing from the `--legend` file you supplied |
