"""End-to-end tests for the TesseraLoom single-file CLI.

Every test drives the real command line in a subprocess so the stdout/stderr
split and the exit codes are the things under test.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tesseraloom.py"

sys.path.insert(0, str(ROOT))
import tesseraloom  # noqa: E402  (path set up above on purpose)


def run_cli(*args: str, stdin_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


def write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture()
def grid_file(tmp_path: Path) -> Path:
    return write(tmp_path, "grid.txt", "K B A\nB A Z\n")


@pytest.fixture()
def counts_grid(tmp_path: Path) -> Path:
    # A appears 3 times, B twice, C once -> 6 tiles, first appearance A, B, C
    return write(tmp_path, "counts.txt", "A B C\nA B A\n")


@pytest.fixture()
def legend_file(tmp_path: Path) -> Path:
    return write(tmp_path, "legend.txt", "K Crimson\nB Slate\n")


# --- F1: input, validation, stable numbering --------------------------------


def test_layout_numbers_colors_by_first_appearance(grid_file: Path) -> None:
    result = run_cli("layout", str(grid_file))
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == "1 2 3"
    assert lines[1] == "2 3 4"
    legend = [line for line in lines if line and line[0].isdigit() and "  " in line]
    assert [line[:4] for line in legend] == ["1  K", "2  B", "3  A", "4  Z"]
    assert result.stderr == ""


def test_layout_from_stdin_matches_file_run(grid_file: Path) -> None:
    from_file = run_cli("layout", str(grid_file))
    from_dash = run_cli("layout", "-", stdin_text=grid_file.read_text())
    from_omitted = run_cli("layout", stdin_text=grid_file.read_text())
    assert from_dash.returncode == from_omitted.returncode == from_file.returncode == 0
    assert from_dash.stdout == from_file.stdout
    assert from_omitted.stdout == from_file.stdout
    assert from_dash.stderr == from_omitted.stderr == from_file.stderr == ""


def test_pads_numbers_so_the_grid_shape_survives(tmp_path: Path) -> None:
    codes = " ".join(f"C{index}" for index in range(1, 13))
    grid = write(tmp_path, "wide.txt", f"{codes}\n{codes}\n")
    result = run_cli("layout", str(grid))
    assert result.returncode == 0
    map_lines = result.stdout.splitlines()[:2]
    assert map_lines[0] == map_lines[1]
    assert map_lines[0].startswith(" 1  2")
    assert map_lines[0].endswith("12")


def test_ragged_row_is_one_error_line_and_no_output(tmp_path: Path) -> None:
    grid = write(tmp_path, "ragged.txt", "A B C\nA B C\nA B C D E\n")
    result = run_cli("layout", str(grid))
    assert result.returncode == 1
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert "row 3" in result.stderr
    assert "5" in result.stderr and "3" in result.stderr


def test_blank_row_is_one_error_line(tmp_path: Path) -> None:
    grid = write(tmp_path, "blank.txt", "A B C\n\nA B C\n")
    result = run_cli("layout", str(grid))
    assert result.returncode == 1
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert "row 2 is empty" in result.stderr


def test_trailing_blank_line_is_reported_with_its_row(tmp_path: Path) -> None:
    grid = write(tmp_path, "trailing.txt", "A B C\nA B C\n\n")
    result = run_cli("layout", str(grid))
    assert result.returncode == 1
    assert len(result.stderr.splitlines()) == 1
    assert "row 3 is empty" in result.stderr


def test_empty_grid_points_at_path_and_dash(tmp_path: Path) -> None:
    grid = write(tmp_path, "empty.txt", "")
    result = run_cli("layout", str(grid))
    assert result.returncode == 1
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert "grid is empty" in result.stderr
    assert "PATH" in result.stderr and "'-'" in result.stderr


def test_missing_file_is_one_line_naming_the_path() -> None:
    result = run_cli("layout", "nope.txt")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "tesseraloom: no such file: nope.txt\n"


# --- usage and help --------------------------------------------------------


def test_no_arguments_prints_usage_and_exits_2() -> None:
    result = run_cli()
    assert result.returncode == 2
    for token in ("layout", "count", "cutlist", "PATH", "-"):
        assert token in result.stdout
    assert len(result.stderr.splitlines()) == 1
    assert "no command given" in result.stderr


def test_help_documents_commands_flags_and_exit_codes() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    for token in (
        "layout",
        "count",
        "cutlist",
        "PATH",
        "-",
        "(--legend)",
        "(--format)",
        "(--out)",
        "EXIT CODES",
        "--legend",
        "--format",
        "--out",
    ):
        assert token.strip("()") in result.stdout
    assert "success (warnings allowed)" in result.stdout
    assert "usage error" in result.stdout


@pytest.mark.parametrize("command", ["layout", "count", "cutlist"])
def test_per_command_help_exits_zero(command: str) -> None:
    result = run_cli(command, "--help")
    assert result.returncode == 0
    assert f"tesseraloom {command}" in result.stdout
    assert "EXIT CODES" in result.stdout


def test_unknown_command_is_one_line_usage_error() -> None:
    result = run_cli("frobnicate")
    assert result.returncode == 2
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert "frobnicate" in result.stderr


def test_unknown_flag_is_one_line_usage_error() -> None:
    result = run_cli("layout", "--bogus")
    assert result.returncode == 2
    assert len(result.stderr.splitlines()) == 1
    assert "--bogus" in result.stderr


def test_version_flag() -> None:
    result = run_cli("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"tesseraloom {tesseraloom.VERSION}"


# --- F2: legend names and undefined-code warnings ---------------------------


def test_legend_names_appear_and_undefined_codes_warn(grid_file: Path, legend_file: Path) -> None:
    result = run_cli("layout", str(grid_file), "--legend", str(legend_file))
    assert result.returncode == 0
    assert "Crimson" in result.stdout
    assert "Slate" in result.stdout
    assert "1 2 3" in result.stdout  # the map still renders
    warnings = result.stderr.splitlines()
    assert len(warnings) == 2
    assert "undefined code A" in warnings[0] and "row 1, column 3" in warnings[0]
    assert "undefined code Z" in warnings[1] and "row 2, column 3" in warnings[1]


def test_undefined_warning_is_deduplicated_per_code(tmp_path: Path) -> None:
    grid = write(tmp_path, "zeds.txt", "Z A\nZ Z\nZ Z\n")
    legend = write(tmp_path, "legend.txt", "A Amber\n")
    result = run_cli("layout", str(grid), "--legend", str(legend))
    assert result.returncode == 0
    warnings = result.stderr.splitlines()
    assert len(warnings) == 1
    assert "undefined code Z" in warnings[0]
    assert "row 1, column 1" in warnings[0]


def test_missing_legend_file_is_one_line_and_exits_1(grid_file: Path) -> None:
    result = run_cli("layout", str(grid_file), "--legend", "nope.txt")
    assert result.returncode == 1
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert "nope.txt" in result.stderr


def test_legend_without_names_keeps_the_map_clean(tmp_path: Path) -> None:
    grid = write(tmp_path, "grid.txt", "K B\n")
    legend = write(tmp_path, "legend.txt", "K\nB\n")
    result = run_cli("layout", str(grid), "--legend", str(legend))
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.splitlines() == ["1 2", "", "1  K", "2  B"]


# --- F3: counts ------------------------------------------------------------


def test_count_rows_in_color_number_order_plus_total(counts_grid: Path) -> None:
    result = run_cli("count", str(counts_grid))
    assert result.returncode == 0
    body = [line for line in result.stdout.splitlines() if line.strip()]
    assert body[0].split() == ["NUM", "CODE", "COUNT"]
    rows = [line.split() for line in body[1:-1]]
    assert rows == [["1", "A", "3"], ["2", "B", "2"], ["3", "C", "1"]]
    assert body[-1] == "TOTAL 6"
    assert result.stderr == ""


def test_count_from_stdin_matches_file_run(counts_grid: Path) -> None:
    from_file = run_cli("count", str(counts_grid))
    from_dash = run_cli("count", "-", stdin_text=counts_grid.read_text())
    assert from_dash.returncode == from_file.returncode == 0
    assert from_dash.stdout == from_file.stdout


def test_count_warns_but_still_counts_undefined_codes(tmp_path: Path) -> None:
    grid = write(tmp_path, "grid.txt", "K A\nA A\n")
    legend = write(tmp_path, "legend.txt", "K Crimson\n")
    result = run_cli("count", str(grid), "--legend", str(legend))
    assert result.returncode == 0
    assert "TOTAL 4" in result.stdout
    rows = [line.split() for line in result.stdout.splitlines()[1:-1]]
    assert rows == [["1", "K", "1"], ["2", "A", "3"]]
    warnings = result.stderr.splitlines()
    assert len(warnings) == 1
    assert "undefined code A" in warnings[0]


def test_count_rejects_a_ragged_grid(tmp_path: Path) -> None:
    grid = write(tmp_path, "ragged.txt", "A B\nA B C\n")
    result = run_cli("count", str(grid))
    assert result.returncode == 1
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1


# --- cut list --------------------------------------------------------------


def test_cutlist_text_default_groups_by_color_code(counts_grid: Path) -> None:
    result = run_cli("cutlist", str(counts_grid))
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0].split() == ["NUM", "CODE", "NAME", "COUNT"]
    assert [line.split() for line in lines[1:4]] == [
        ["1", "A", "-", "3"],
        ["2", "B", "-", "2"],
        ["3", "C", "-", "1"],
    ]
    assert lines[-1] == "TOTAL 6"


def test_cutlist_csv_has_header_rows_and_total_row(counts_grid: Path) -> None:
    result = run_cli("cutlist", str(counts_grid), "--format", "csv")
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == "number,code,name,count"
    assert lines[1:4] == ["1,A,-,3", "2,B,-,2", "3,C,-,1"]
    assert lines[-1] == "TOTAL,,,6"


def test_cutlist_explicit_text_matches_the_default(counts_grid: Path) -> None:
    default = run_cli("cutlist", str(counts_grid))
    explicit = run_cli("cutlist", str(counts_grid), "--format", "text")
    assert explicit.returncode == default.returncode == 0
    assert explicit.stdout == default.stdout


def test_cutlist_out_writes_exact_bytes_and_keeps_stdout_empty(
    counts_grid: Path, tmp_path: Path
) -> None:
    expected = run_cli("cutlist", str(counts_grid), "--format", "csv")
    out_path = tmp_path / "out.csv"
    result = run_cli("cutlist", str(counts_grid), "--format", "csv", "--out", str(out_path))
    assert result.returncode == 0
    assert result.stdout == ""
    assert out_path.read_text(encoding="utf-8") == expected.stdout


def test_cutlist_out_in_missing_directory_creates_nothing(
    counts_grid: Path, tmp_path: Path
) -> None:
    out_path = tmp_path / "no" / "such" / "dir" / "out.csv"
    result = run_cli("cutlist", str(counts_grid), "--out", str(out_path))
    assert result.returncode == 1
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert str(out_path) in result.stderr
    assert not out_path.exists()


def test_unknown_format_is_a_usage_error(counts_grid: Path) -> None:
    result = run_cli("cutlist", str(counts_grid), "--format", "xml")
    assert result.returncode == 2
    assert result.stdout == ""
    assert len(result.stderr.splitlines()) == 1
    assert "xml" in result.stderr
    assert "text" in result.stderr and "csv" in result.stderr


def test_cutlist_marks_and_warns_undefined_codes(tmp_path: Path) -> None:
    grid = write(tmp_path, "grid.txt", "K Z\nZ Z\n")
    legend = write(tmp_path, "legend.txt", "K Crimson\n")
    result = run_cli("cutlist", str(grid), "--legend", str(legend))
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert "Crimson" in lines[1]
    assert "undefined" in lines[2]
    assert lines[-1] == "TOTAL 4"
    warnings = result.stderr.splitlines()
    assert len(warnings) == 1
    assert "undefined code Z" in warnings[0]


def test_csv_quotes_names_containing_commas_and_quotes(tmp_path: Path) -> None:
    grid = write(tmp_path, "grid.txt", "K B\n")
    legend = write(tmp_path, "legend.txt", 'K Crimson, deep\nB Slate "blue"\n')
    result = run_cli("cutlist", str(grid), "--legend", str(legend), "--format", "csv")
    assert result.returncode == 0
    rows = list(csv.reader(io.StringIO(result.stdout)))
    assert rows[0] == ["number", "code", "name", "count"]
    assert rows[1] == ["1", "K", "Crimson, deep", "1"]
    assert rows[2] == ["2", "B", 'Slate "blue"', "1"]
    assert rows[3] == ["TOTAL", "", "", "2"]


# --- non-functional --------------------------------------------------------


def test_output_is_byte_identical_across_runs(grid_file: Path, legend_file: Path) -> None:
    first = run_cli("cutlist", str(grid_file), "--legend", str(legend_file), "--format", "csv")
    second = run_cli("cutlist", str(grid_file), "--legend", str(legend_file), "--format", "csv")
    assert first.stdout == second.stdout
    assert first.stderr == second.stderr


def test_two_hundred_by_two_hundred_grid_is_fast(tmp_path: Path) -> None:
    codes = ["CR", "SL", "GD", "IN", "WH", "SG", "TP", "RB"]
    rows = [
        " ".join(codes[(row + column) % len(codes)] for column in range(200)) for row in range(200)
    ]
    grid = write(tmp_path, "big.txt", "\n".join(rows) + "\n")
    started = time.monotonic()
    result = run_cli("count", str(grid))
    elapsed = time.monotonic() - started
    assert result.returncode == 0
    assert "TOTAL 40000" in result.stdout
    assert elapsed < 1.0, f"200x200 grid took {elapsed:.2f}s"


def test_sample_fixtures_smoke_all_three_commands() -> None:
    for command in ("layout", "count", "cutlist"):
        result = run_cli(command, "sample_grid.txt", "--legend", "legend.txt")
        assert result.returncode == 0, result.stderr
        assert "Traceback" not in result.stderr
        assert result.stderr == ""
        assert result.stdout.strip() != ""


def test_example_garden_design_warns_about_two_undefined_codes() -> None:
    result = run_cli("layout", "examples/design_garden.txt", "--legend", "legend.txt")
    assert result.returncode == 0
    warnings = result.stderr.splitlines()
    assert len(warnings) == 2
    assert any("SGE" in line for line in warnings)
    assert any("STN" in line for line in warnings)


def test_main_is_importable_and_callable(capsys: pytest.CaptureFixture) -> None:
    assert tesseraloom.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"tesseraloom {tesseraloom.VERSION}"
