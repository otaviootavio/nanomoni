"""Tests for generate_plots module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch


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
    def test_main_calls_generate_all_modes_defaults(self) -> None:
        with patch("bench_plotter.generate_plots.generate_all_modes") as mock_gen:
            with patch("sys.argv", ["generate_plots"]):
                main()
            mock_gen.assert_called_once_with(
                intervals_path=None,
                output_dir="plots",
                num_points=100,
            )

    def test_main_passes_custom_output(self) -> None:
        with patch("bench_plotter.generate_plots.generate_all_modes") as mock_gen:
            with patch("sys.argv", ["generate_plots", "--output", "my_plots"]):
                main()
            mock_gen.assert_called_once_with(
                intervals_path=None,
                output_dir="my_plots",
                num_points=100,
            )

    def test_main_passes_custom_interpol(self) -> None:
        with patch("bench_plotter.generate_plots.generate_all_modes") as mock_gen:
            with patch("sys.argv", ["generate_plots", "--interpol", "200"]):
                main()
            mock_gen.assert_called_once_with(
                intervals_path=None,
                output_dir="plots",
                num_points=200,
            )

    def test_main_passes_explicit_intervals_path(self) -> None:
        with patch("bench_plotter.generate_plots.generate_all_modes") as mock_gen:
            with patch("sys.argv", ["generate_plots", "/some/path/timing.json"]):
                main()
            mock_gen.assert_called_once_with(
                intervals_path="/some/path/timing.json",
                output_dir="plots",
                num_points=100,
            )
