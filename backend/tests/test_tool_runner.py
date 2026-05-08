import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.tool_runner import ToolResult, ToolRunner


@pytest.fixture
def runner(tmp_path):
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    return ToolRunner(tools_dir=tools_dir)


@pytest.fixture
def job_dir(tmp_path):
    d = tmp_path / "jobs" / "test-job"
    d.mkdir(parents=True)
    return d


def _write_tool(tools_dir: Path, name: str, script: str) -> None:
    (tools_dir / f"{name}.py").write_text(script)


class TestToolRunnerPathPatching:
    def test_patches_tmp_prefix_in_strings(self, runner, job_dir):
        spec = {"input": ".tmp/sequences.fasta", "output": ".tmp/results.json"}
        patched = runner._patch_paths(spec, job_dir)
        assert patched["input"] == str(job_dir / "sequences.fasta")
        assert patched["output"] == str(job_dir / "results.json")

    def test_leaves_non_tmp_paths_unchanged(self, runner, job_dir):
        spec = {"db_path": "/data/mydb.sqlite", "threshold": 0.8}
        patched = runner._patch_paths(spec, job_dir)
        assert patched["db_path"] == "/data/mydb.sqlite"
        assert patched["threshold"] == 0.8

    def test_patches_nested_dicts(self, runner, job_dir):
        spec = {"nested": {"file": ".tmp/inner.json"}}
        patched = runner._patch_paths(spec, job_dir)
        assert patched["nested"]["file"] == str(job_dir / "inner.json")

    def test_patches_lists(self, runner, job_dir):
        spec = {"files": [".tmp/a.fasta", ".tmp/b.fasta"]}
        patched = runner._patch_paths(spec, job_dir)
        assert patched["files"] == [str(job_dir / "a.fasta"), str(job_dir / "b.fasta")]


class TestToolRunnerExecution:
    def test_returns_ok_on_valid_json_output(self, runner, job_dir, tmp_path):
        _write_tool(
            runner.tools_dir,
            "echo_tool",
            'import sys, json; print(json.dumps({"status": "ok", "count": 3}))',
        )
        result = runner.run_tool("echo_tool", {}, job_dir)
        assert result.status == "ok"
        assert result.data == {"status": "ok", "count": 3}

    def test_returns_error_on_nonzero_exit(self, runner, job_dir):
        _write_tool(
            runner.tools_dir,
            "failing_tool",
            'import sys; print("error: something broke", file=sys.stderr); sys.exit(1)',
        )
        result = runner.run_tool("failing_tool", {}, job_dir)
        assert result.status == "error"
        assert result.exit_code == 1
        assert "something broke" in result.stderr

    def test_returns_error_when_tool_missing(self, runner, job_dir):
        result = runner.run_tool("nonexistent_tool", {}, job_dir)
        assert result.status == "error"
        assert "not found" in result.stderr.lower()

    def test_writes_input_json_to_job_dir(self, runner, job_dir):
        _write_tool(runner.tools_dir, "passthrough", 'import json; print(json.dumps({}))')
        runner.run_tool("passthrough", {"key": "value"}, job_dir)
        input_file = job_dir / "input_passthrough.json"
        assert input_file.exists()
        data = json.loads(input_file.read_text())
        assert data["key"] == "value"

    def test_handles_insufficient_data_exit(self, runner, job_dir):
        _write_tool(
            runner.tools_dir,
            "min_data_tool",
            'import sys; print("Error: insufficient data, minimum 20 samples required", file=sys.stderr); sys.exit(1)',
        )
        result = runner.run_tool("min_data_tool", {}, job_dir)
        assert result.status == "insufficient_data"

    def test_timeout_returns_error(self, runner, job_dir):
        _write_tool(runner.tools_dir, "slow_tool", "import time; time.sleep(60)")
        result = runner.run_tool("slow_tool", {}, job_dir, timeout=1)
        assert result.status == "error"
        assert "timed out" in result.stderr.lower()
