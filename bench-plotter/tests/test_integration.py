"""Integration tests for the complete workflow."""

import json
import os
import tempfile
from typing import Any
from unittest.mock import patch

import pytest

from bench_plotter.generate_plots import generate_all_modes, main


class TestGenerateAllModesIntegration:
    def _write(self, path: str, data: Any) -> None:
        with open(path, "w") as f:
            json.dump(data, f)

    INTERVALS = [
        {
            "mode": "signature",
            "status": "success",
            "prometheus_timestamps": {"start_ms": 1000000, "finish_ms": 1000600},
        },
        {
            "mode": "paytree",
            "status": "success",
            "prometheus_timestamps": {"start_ms": 1000600, "finish_ms": 1001200},
        },
    ]

    def test_generate_all_modes_calls_process_all_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            intervals_path = os.path.join(tmp, "timing.json")
            self._write(intervals_path, self.INTERVALS)

            with patch("bench_plotter.plotting.process_all_modes") as mock_proc:
                generate_all_modes(
                    intervals_path=intervals_path,
                    output_dir=os.path.join(tmp, "plots"),
                    num_points=50,
                )
                mock_proc.assert_called_once()
                kwargs = mock_proc.call_args[1]
                assert kwargs["num_points"] == 50

    def test_generate_all_modes_creates_output_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            intervals_path = os.path.join(tmp, "timing.json")
            output_dir = os.path.join(tmp, "plots")
            self._write(intervals_path, self.INTERVALS)

            with patch("bench_plotter.plotting.process_all_modes"):
                generate_all_modes(intervals_path=intervals_path, output_dir=output_dir)

            assert os.path.exists(output_dir)

    def test_generate_all_modes_exits_on_missing_file(self) -> None:
        with pytest.raises(SystemExit):
            generate_all_modes(intervals_path="/nonexistent/timing.json")

    def test_main_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            intervals_path = os.path.join(tmp, "timing.json")
            self._write(intervals_path, self.INTERVALS)

            with patch("bench_plotter.generate_plots.generate_all_modes") as mock_gen:
                with patch(
                    "sys.argv", ["generate_plots", intervals_path, "--output", tmp]
                ):
                    main()
                mock_gen.assert_called_once_with(
                    intervals_path=intervals_path,
                    output_dir=tmp,
                    num_points=100,
                )
