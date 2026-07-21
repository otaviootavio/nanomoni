"""Tests for the generate_plots CLI wrapper and directory helpers."""

import os
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch


from bench_plotter.generate_plots import clean_plots_directory, main


class TestCleanPlotsDirectory:
    def test_clean_existing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "plot1.png").touch()
            (temp_path / "plot2.png").touch()
            (temp_path / "data.txt").write_text("keep me")

            clean_plots_directory(temp_path)

            remaining = os.listdir(temp_dir)
            assert "data.txt" in remaining
            assert "plot1.png" not in remaining
            assert "plot2.png" not in remaining

    def test_clean_nonexistent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            new_dir = Path(temp_dir) / "new_directory"
            clean_plots_directory(new_dir)
            assert new_dir.exists()
            assert new_dir.is_dir()


class TestMainFunction:
    """``main`` parses args and delegates to ``generate_plots_from_benchmark``.

    The pipeline is imported lazily inside ``main`` (to keep ``--help`` cheap),
    so it is patched at its definition site in the pipeline package.
    """

    def _run_main(self, argv: List[str], intervals_content: str) -> MagicMock:
        with tempfile.TemporaryDirectory() as tmp:
            intervals_path = Path(tmp) / "timing.json"
            intervals_path.write_text(intervals_content)
            output = str(Path(tmp) / "plots")
            full_argv = (
                ["generate_plots", str(intervals_path)]
                + argv
                + [
                    "--output",
                    output,
                ]
            )
            with patch(
                "bench_plotter.pipeline.generate_plots_from_benchmark"
            ) as mock_gen:
                with patch("sys.argv", full_argv):
                    main()
            return mock_gen

    def test_main_defaults(self) -> None:
        mock_gen = self._run_main([], "[]")
        mock_gen.assert_called_once()
        kwargs = mock_gen.call_args[1]
        assert kwargs["num_points"] == 100
        assert kwargs["parallel"] is True
        assert kwargs["workers"] is None

    def test_main_custom_interpol(self) -> None:
        mock_gen = self._run_main(["--interpol", "200"], "[]")
        assert mock_gen.call_args[1]["num_points"] == 200

    def test_main_no_parallel(self) -> None:
        mock_gen = self._run_main(["--no-parallel"], "[]")
        assert mock_gen.call_args[1]["parallel"] is False

    def test_main_workers(self) -> None:
        mock_gen = self._run_main(["--workers", "4"], "[]")
        assert mock_gen.call_args[1]["workers"] == 4
