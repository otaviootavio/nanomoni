"""Tests for plotting module - the core functionality."""

import json
import os
import tempfile

import pytest

from bench_plotter.io_utils import load_json_data


class TestLoadJsonData:
    """Test JSON data loading functionality."""

    def test_load_valid_json(self) -> None:
        """Test loading valid JSON file."""
        test_data = {"key": "value"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            result = load_json_data(temp_path)
            assert result == test_data
        finally:
            os.unlink(temp_path)

    def test_load_nonexistent_file(self) -> None:
        """Test loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_json_data("/nonexistent/path.json")

    def test_load_invalid_json(self) -> None:
        """Test loading invalid JSON raises JSONDecodeError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(json.JSONDecodeError):
                load_json_data(temp_path)
        finally:
            os.unlink(temp_path)
