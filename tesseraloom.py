#!/usr/bin/env python3
"""TesseraLoom: map mosaic tile codes to a numbered layout, count tiles per
color, and export a cut list grouped by color code.

Single file, standard library only, no network, no persistence. The only file
ever written is an explicit ``--out`` path.

Exit codes: 0 success (warnings allowed), 1 input/output error, 2 usage error.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NoReturn

PROG = "tesseraloom"
VERSION = "1.0.0"
TAGLINE = "map mosaic tile codes to a numbered layout, count tiles, export a cut list"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

STDIN = "-"

COMMANDS = ("layout", "count", "cutlist")
FORMATS = ("text", "csv")

# --- committed design tokens (archetype cli / family calm-precise) ----------
# accent oklch(0.58 0.12 205) == #008d9c; the terminal surface is dark, the type
# is monospace, alignment replaces chrome. ANSI truecolor is used for help
# headings only, on a color-capable TTY, never for data output and never on
# stderr.
ACCENT_ANSI = "\x1b[38;2;0;141;156m"
RESET_ANSI = "\x1b[0m"
RULE_CHAR = "\u2500"
RULE_WIDTH = 60

LABEL_WIDTH = 18


# --- errors ----------------------------------------------------------------


class TesseraError(Exception):
    """An input/output problem: rendered as one stderr line, exit code 1."""


class UsageError(Exception):
    """A command-line misuse: rendered as one stderr line, exit code 2."""


class _HelpRequested(Exception):
    def __init__(self, command: str | None) -> None:
        super().__init__(command)
        self.command = command


class _VersionRequested(Exception):
    pass


# --- data model ------------------------------------------------------------


@dataclass(frozen=True)
class ColorNumber:
    """A distinct tile code with its stable 1-based number and first cell."""

    code: str
    number: int
    first_row: int
    first_column: int


@dataclass
class DesignGrid:
    source: str
    rows: list[list[str]]
    colors: list[ColorNumber]
    numbers: dict[str, int]

    @property
    def width(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def tile_count(self) -> int:
        return sum(len(row) for row in self.rows)


@dataclass(frozen=True)
class Legend:
    source_path: str
    entries: dict[str, str | None]


@dataclass(frozen=True)
class TileCount:
    code: str
    number: int
    count: int


@dataclass(frozen=True)
class CutListRow:
    number: int
    code: str
    name: str
    count: int


@dataclass(frozen=True)
class CommandOutput:
    text: str
    warnings: tuple[str, ...]
    out_path: str | None = None


# --- input -----------------------------------------------------------------


def _stdin_is_tty() -> bool:
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


def read_source(source: str, kind: str) -> str:
    """Read UTF-8 text from a path or from stdin ('-')."""
    if source == STDIN:
        try:
            return sys.stdin.read()
        except UnicodeDecodeError:
            raise TesseraError("stdin is not valid UTF-8 text") from None
    try:
        with open(source, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        raise TesseraError(f"no such {kind}: {source}") from None
    except IsADirectoryError:
        raise TesseraError(f"{kind} is a directory: {source}") from None
    except PermissionError:
        raise TesseraError(f"cannot read {kind}: {source} (permission denied)") from None
    except UnicodeDecodeError:
        raise TesseraError(f"{kind} is not UTF-8 text: {source}") from None
    except OSError:
        raise TesseraError(f"cannot read {kind}: {source}") from None


def read_grid_text(source: str) -> str:
    if source == STDIN and _stdin_is_tty():
        raise TesseraError(
            "no grid on stdin; pass a grid PATH, use '-' for stdin, or pipe a grid in"
        )
    return read_source(source, "file")


def parse_grid_rows(text: str, label: str) -> list[list[str]]:
    """Split a typed grid into rows of codes; enforce a non-empty rectangle."""
    rows: list[list[str]] = []
    width = 0
    for index, line in enumerate(text.splitlines(), start=1):
        codes = line.split()
        if not codes:
            raise TesseraError(
                f"{label}: row {index} is empty; every row needs at least one tile code"
            )
        if not rows:
            width = len(codes)
        elif len(codes) != width:
            raise TesseraError(
                f"{label}: row {index} has {len(codes)} codes, expected {width};"
                " the grid must be a rectangle"
            )
        rows.append(codes)
    if not rows:
        raise TesseraError("grid is empty; pass a grid PATH, use '-' for stdin, or pipe a grid in")
    return rows


def number_colors(rows: Sequence[Sequence[str]]) -> list[ColorNumber]:
    """Assign 1..N in first-appearance reading order (row by row, left to right)."""
    colors: list[ColorNumber] = []
    seen: dict[str, ColorNumber] = {}
    for row_index, row in enumerate(rows, start=1):
        for column_index, code in enumerate(row, start=1):
            if code not in seen:
                color = ColorNumber(
                    code=code,
                    number=len(colors) + 1,
                    first_row=row_index,
                    first_column=column_index,
                )
                seen[code] = color
                colors.append(color)
    return colors


def load_grid(source: str) -> DesignGrid:
    label = "<stdin>" if source == STDIN else source
    rows = parse_grid_rows(read_grid_text(source), label)
    colors = number_colors(rows)
    numbers = {color.code: color.number for color in colors}
    return DesignGrid(source=label, rows=rows, colors=colors, numbers=numbers)


def load_legend(path: str) -> Legend:
    text = read_source(path, "legend file")
    entries: dict[str, str | None] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        code = parts[0]
        name = parts[1].strip() if len(parts) > 1 else ""
        if code in entries:  # first definition wins, order kept
            continue
        entries[code] = name or None
    return Legend(source_path=path, entries=entries)


# --- computation -----------------------------------------------------------


def tile_counts(grid: DesignGrid) -> list[TileCount]:
    counts = Counter(code for row in grid.rows for code in row)
    return [
        TileCount(code=color.code, number=color.number, count=counts[color.code])
        for color in grid.colors
    ]


def cut_list_rows(grid: DesignGrid, legend: Legend | None) -> list[CutListRow]:
    rows: list[CutListRow] = []
    for count in tile_counts(grid):
        if legend is None:
            name = "-"
        elif count.code in legend.entries:
            name = legend.entries[count.code] or "-"
        else:
            name = "undefined"
        rows.append(CutListRow(number=count.number, code=count.code, name=name, count=count.count))
    return rows


def undefined_warnings(grid: DesignGrid, legend: Legend | None) -> list[str]:
    """One deduplicated warning per grid code the legend does not define."""
    if legend is None:
        return []
    warnings: list[str] = []
    for color in grid.colors:
        if color.code not in legend.entries:
            warnings.append(
                f"undefined code {color.code} (first seen at row {color.first_row},"
                f" column {color.first_column}); not in {legend.source_path}"
            )
    return warnings


# --- rendering -------------------------------------------------------------


def render_layout(grid: DesignGrid, legend: Legend | None) -> str:
    number_width = len(str(max(color.number for color in grid.colors)))
    code_width = max(len(color.code) for color in grid.colors)
    lines: list[str] = [
        " ".join(f"{grid.numbers[code]:>{number_width}}" for code in row) for row in grid.rows
    ]
    lines.append("")
    for color in grid.colors:
        entry = f"{color.number:>{number_width}}  {color.code:<{code_width}}"
        name = legend.entries.get(color.code) if legend is not None else None
        if name:
            entry = f"{entry}  {name}"
        lines.append(entry.rstrip())
    return "\n".join(lines) + "\n"


def _align(cells: Sequence[str], widths: Sequence[int], right: Sequence[bool]) -> str:
    """Join padded cells with two spaces; numeric columns are right-aligned."""
    padded = [
        f"{cell:>{width}}" if align_right else f"{cell:<{width}}"
        for cell, width, align_right in zip(cells, widths, right)
    ]
    return "  ".join(padded)


def render_counts(grid: DesignGrid) -> str:
    counts = tile_counts(grid)
    total = sum(count.count for count in counts)
    widths = [
        max(len("NUM"), *(len(str(count.number)) for count in counts)),
        max(len("CODE"), *(len(count.code) for count in counts)),
        max(len("COUNT"), len(str(total)), *(len(str(count.count)) for count in counts)),
    ]
    lines = [_align(("NUM", "CODE", "COUNT"), widths, (True, False, True))]
    for count in counts:
        lines.append(
            _align((str(count.number), count.code, str(count.count)), widths, (True, False, True))
        )
    lines.append(f"TOTAL {total}")
    return "\n".join(lines) + "\n"


def render_cutlist_text(rows: Sequence[CutListRow], total: int) -> str:
    widths = [
        max(len("NUM"), *(len(str(row.number)) for row in rows)),
        max(len("CODE"), *(len(row.code) for row in rows)),
        max(len("NAME"), *(len(row.name) for row in rows)),
        max(len("COUNT"), len(str(total)), *(len(str(row.count)) for row in rows)),
    ]
    lines = [_align(("NUM", "CODE", "NAME", "COUNT"), widths, (True, False, False, True))]
    for row in rows:
        lines.append(
            _align(
                (str(row.number), row.code, row.name, str(row.count)),
                widths,
                (True, False, False, True),
            )
        )
    lines.append(f"TOTAL {total}")
    return "\n".join(lines) + "\n"


def render_cutlist_csv(rows: Sequence[CutListRow], total: int) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["number", "code", "name", "count"])
    for row in rows:
        writer.writerow([row.number, row.code, row.name, row.count])
    writer.writerow(["TOTAL", "", "", total])
    return buffer.getvalue()


def render_cutlist(grid: DesignGrid, legend: Legend | None, fmt: str) -> str:
    rows = cut_list_rows(grid, legend)
    total = sum(row.count for row in rows)
    if fmt == "csv":
        return render_cutlist_csv(rows, total)
    return render_cutlist_text(rows, total)


# --- output ----------------------------------------------------------------


def write_output_file(path: str, text: str) -> None:
    """Write the whole output in one go; nothing partial is left behind."""
    if os.path.isdir(path):
        raise TesseraError(f"cannot write {path}: is a directory")
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except FileNotFoundError:
        raise TesseraError(f"cannot write {path}: no such directory") from None
    except PermissionError:
        raise TesseraError(f"cannot write {path}: permission denied") from None
    except OSError:
        raise TesseraError(f"cannot write {path}: write failed") from None


# --- command dispatch ------------------------------------------------------


def run_command(args: argparse.Namespace) -> CommandOutput:
    fmt = getattr(args, "format", "text") or "text"
    out_path = getattr(args, "out", None)
    if fmt not in FORMATS:
        raise UsageError(f"unknown format: {fmt} (allowed formats are text and csv)")
    if getattr(args, "out", None) is not None and not out_path:
        raise UsageError("--out needs a file PATH")
    if args.legend == STDIN:
        raise UsageError("--legend needs a file PATH; stdin is reserved for the grid")

    grid = load_grid(args.grid)
    legend = load_legend(args.legend) if args.legend is not None else None
    warnings = tuple(undefined_warnings(grid, legend))

    if args.command == "layout":
        return CommandOutput(text=render_layout(grid, legend), warnings=warnings)
    if args.command == "count":
        return CommandOutput(text=render_counts(grid), warnings=warnings)
    if args.command == "cutlist":
        return CommandOutput(
            text=render_cutlist(grid, legend, fmt), warnings=warnings, out_path=out_path
        )
    raise UsageError(f"unknown command: {args.command} (commands are {', '.join(COMMANDS)})")


# --- help ------------------------------------------------------------------

HELP_SECTIONS: dict[str, dict[str, object]] = {
    "layout": {
        "summary": "print the grid as color numbers, then a legend in number order",
        "usage": [f"{PROG} layout [GRID] [--legend PATH]"],
        "options": [("--legend PATH", "known codes, one 'CODE [name]' per line")],
        "notes": [
            "The map replaces every tile code with its color number, padded so",
            "multi-digit numbers keep the grid shape. A blank line separates the",
            "map from the legend, which lists number, code and any legend name.",
            "Codes missing from --legend print one warning each on stderr and the",
            "exit code stays 0.",
        ],
        "examples": [
            f"{PROG} layout sample_grid.txt",
            f"cat design.txt | {PROG} layout - --legend legend.txt",
        ],
    },
    "count": {
        "summary": "print one row per color code with its tile count, plus a total",
        "usage": [f"{PROG} count [GRID] [--legend PATH]"],
        "options": [("--legend PATH", "known codes, one 'CODE [name]' per line")],
        "notes": [
            "Rows are in color-number order (first appearance in the grid), the",
            "last line reads 'TOTAL <n>'. Codes missing from --legend print one",
            "warning each on stderr and the exit code stays 0.",
        ],
        "examples": [
            f"{PROG} count sample_grid.txt",
            f"{PROG} count sample_grid.txt --legend legend.txt",
        ],
    },
    "cutlist": {
        "summary": "print or write a cut list grouped by color code, plus a total",
        "usage": [f"{PROG} cutlist [GRID] [--legend PATH] [--format text|csv] [--out PATH]"],
        "options": [
            ("--legend PATH", "known codes, one 'CODE [name]' per line"),
            ("--format FORMAT", "text (default) or csv"),
            ("--out PATH", "write the cut list to PATH instead of stdout"),
        ],
        "notes": [
            "Text columns are number, code, name, count followed by 'TOTAL <n>'.",
            "The name is '-' when --legend is absent and 'undefined' when a legend",
            "was given that does not define the code. CSV header is",
            "number,code,name,count and the last row is TOTAL,,,<n>.",
        ],
        "examples": [
            f"{PROG} cutlist sample_grid.txt --legend legend.txt",
            f"{PROG} cutlist sample_grid.txt --format csv",
            f"{PROG} cutlist sample_grid.txt --format csv --out cutlist.csv",
        ],
    },
}


def _accent(text: str, color: bool) -> str:
    return f"{ACCENT_ANSI}{text}{RESET_ANSI}" if color else text


def _rule() -> str:
    return RULE_CHAR * RULE_WIDTH


def _row(label: str, text: str) -> str:
    return f"  {label:<{LABEL_WIDTH}}{text}".rstrip()


def _block(title: str, lines: Sequence[str], color: bool) -> list[str]:
    return ["", _accent(title, color), *lines]


def _exit_code_lines() -> list[str]:
    return [
        _row("0", "success (warnings allowed)"),
        _row("1", "input or output error"),
        _row("2", "usage error"),
    ]


def _grid_source_lines() -> list[str]:
    return [
        _row("PATH", "read the grid from a file"),
        _row("-", "read the grid from stdin"),
        _row("(omitted)", "read the grid from stdin, same as -"),
        "  one row per line, whitespace-separated tile codes, and a",
        "  non-empty rectangle",
    ]


def render_help(command: str | None, color: bool = False) -> str:
    if command is None:
        return _render_root_help(color)
    return _render_command_help(command, color)


def _render_root_help(color: bool) -> str:
    lines: list[str] = [
        f"{_accent(PROG + ' ' + VERSION, color)}  {TAGLINE}",
        _rule(),
    ]
    lines += _block(
        "USAGE",
        [f"  {PROG} <command> [GRID] [options]", f"  {PROG} --help | --version"],
        color,
    )
    lines += _block(
        "COMMANDS",
        [
            _row("layout", "numbered layout map plus a legend"),
            _row("count", "tile counts per color code, plus a total"),
            _row("cutlist", "cut list grouped by color code, text or CSV"),
        ],
        color,
    )
    lines += _block("GRID SOURCE", _grid_source_lines(), color)
    lines += _block(
        "OPTIONS",
        [
            _row("--legend PATH", "known codes, one 'CODE [name]' per line"),
            _row("--format FORMAT", "cutlist only: text (default) or csv"),
            _row("--out PATH", "cutlist only: write to PATH instead of stdout"),
            _row("-h, --help", "show this help; after a command, that command's help"),
            _row("--version", "show the version"),
        ],
        color,
    )
    lines += _block("EXIT CODES", _exit_code_lines(), color)
    lines += _block(
        "EXAMPLES",
        [
            f"  {PROG} layout sample_grid.txt",
            f"  {PROG} count sample_grid.txt --legend legend.txt",
            f"  {PROG} cutlist sample_grid.txt --format csv --out cutlist.csv",
            f"  cat design.txt | {PROG} layout -",
        ],
        color,
    )
    return "\n".join(lines) + "\n"


def _render_command_help(command: str, color: bool) -> str:
    info = HELP_SECTIONS[command]
    usage: Sequence[str] = info["usage"]  # type: ignore[assignment]
    options: Sequence[tuple[str, str]] = info["options"]  # type: ignore[assignment]
    notes: Sequence[str] = info["notes"]  # type: ignore[assignment]
    examples: Sequence[str] = info["examples"]  # type: ignore[assignment]

    lines: list[str] = [
        f"{_accent(PROG + ' ' + command, color)}  {info['summary']}",
        _rule(),
    ]
    lines += _block("USAGE", [f"  {line}" for line in usage], color)
    lines += _block(
        "GRID SOURCE",
        [_row("GRID", "grid PATH, or - / omitted to read stdin")] + _grid_source_lines()[3:],
        color,
    )
    lines += _block(
        "OPTIONS",
        [_row(label, text) for label, text in options] + [_row("-h, --help", "show this help")],
        color,
    )
    lines += _block("OUTPUT", [f"  {note}" for note in notes], color)
    lines += _block("EXIT CODES", _exit_code_lines(), color)
    lines += _block("EXAMPLES", [f"  {example}" for example in examples], color)
    return "\n".join(lines) + "\n"


# --- argument parsing ------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    """argparse with one-line errors instead of a usage dump."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


class _HelpAction(argparse.Action):
    def __init__(self, option_strings, dest, command=None, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(option_strings, dest, nargs=0, **kwargs)
        self.command = command

    def __call__(self, parser, namespace, values, option_string=None):  # type: ignore[no-untyped-def]
        raise _HelpRequested(self.command)


class _VersionAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):  # type: ignore[no-untyped-def]
        raise _VersionRequested()


def _add_grid_arguments(parser: argparse.ArgumentParser, help_command: str | None) -> None:
    parser.add_argument("grid", nargs="?", default=STDIN, metavar="GRID")
    parser.add_argument("--legend", metavar="PATH", default=None)
    parser.add_argument(
        "-h", "--help", action=_HelpAction, command=help_command, dest="help_requested"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog=PROG, add_help=False, allow_abbrev=False)
    parser.add_argument("-h", "--help", action=_HelpAction, command=None, dest="help_requested")
    parser.add_argument("-V", "--version", action=_VersionAction, dest="version_requested")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for command in COMMANDS:
        subparser = subparsers.add_parser(
            command, add_help=False, allow_abbrev=False, prog=f"{PROG} {command}"
        )
        _add_grid_arguments(subparser, command)
        if command == "cutlist":
            subparser.add_argument("--format", metavar="FORMAT", default="text")
            subparser.add_argument("--out", metavar="PATH", default=None)
    return parser


def parse_args(arguments: Sequence[str]) -> argparse.Namespace:
    argv = list(arguments)
    if argv and not argv[0].startswith("-") and argv[0] not in COMMANDS:
        raise UsageError(f"unknown command: {argv[0]} (commands are {', '.join(COMMANDS)})")
    return build_parser().parse_args(argv)


# --- process plumbing ------------------------------------------------------


def _configure_text_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue  # best effort: a wrapped stream may refuse, which is fine


def _color_enabled(stream) -> bool:  # type: ignore[no-untyped-def]
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") in ("", "dumb"):
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _report(message: str, code: int) -> int:
    sys.stderr.write(f"{PROG}: {message}\n")
    sys.stderr.flush()
    return code


def _silence_stdout() -> None:
    # A downstream reader closed the pipe (`| head`); point stdout at devnull so
    # interpreter shutdown does not print an ignored-exception notice.
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass


def _dispatch(argv: Sequence[str]) -> int:
    _configure_text_streams()
    try:
        args = parse_args(argv)
    except _HelpRequested as request:
        sys.stdout.write(render_help(request.command, color=_color_enabled(sys.stdout)))
        return EXIT_OK
    except _VersionRequested:
        sys.stdout.write(f"{PROG} {VERSION}\n")
        return EXIT_OK
    except UsageError as error:
        return _report(f"{error} (see --help)", EXIT_USAGE)

    if args.command is None:
        sys.stdout.write(render_help(None, color=_color_enabled(sys.stdout)))
        sys.stdout.flush()
        return _report("no command given; run layout, count or cutlist", EXIT_USAGE)

    try:
        output = run_command(args)
        if output.out_path is not None:
            write_output_file(output.out_path, output.text)
        else:
            sys.stdout.write(output.text)
            sys.stdout.flush()
    except UsageError as error:
        return _report(f"{error} (see --help)", EXIT_USAGE)
    except TesseraError as error:
        return _report(str(error), EXIT_ERROR)

    for warning in output.warnings:
        sys.stderr.write(f"{PROG}: warning: {warning}\n")
    sys.stderr.flush()
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Console entry point; returns the process exit code."""
    arguments = list(sys.argv[1:]) if argv is None else list(argv)
    try:
        return _dispatch(arguments)
    except BrokenPipeError:
        _silence_stdout()
        return EXIT_OK
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
