import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.config import settings


@dataclass
class ToolResult:
    status: str          # "ok" | "error" | "insufficient_data"
    data: dict[str, Any] = field(default_factory=dict)
    stderr: str = ""
    exit_code: int = 0
    job_dir: Optional[Path] = None


class ToolRunner:
    """
    Executes WAT tools as subprocesses with per-job directory isolation.

    Each job gets its own directory so concurrent runs never share .tmp/ paths.
    All relative ".tmp/" references in input_spec are patched to absolute job_dir paths.
    """

    def __init__(self, tools_dir: Optional[Path] = None):
        self.tools_dir = tools_dir or settings.tools_dir

    def run_tool(
        self,
        tool_name: str,
        input_spec: dict[str, Any],
        job_dir: Path,
        timeout: int = 3600,
    ) -> ToolResult:
        job_dir.mkdir(parents=True, exist_ok=True)

        patched = self._patch_paths(input_spec, job_dir)

        input_file = job_dir / f"input_{tool_name}.json"
        input_file.write_text(json.dumps(patched, indent=2), encoding="utf-8")

        tool_path = self.tools_dir / f"{tool_name}.py"
        if not tool_path.exists():
            return ToolResult(
                status="error",
                stderr=f"Tool not found: {tool_path}",
                exit_code=1,
                job_dir=job_dir,
            )

        try:
            proc = subprocess.run(
                [sys.executable, str(tool_path), "--input-file", str(input_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(job_dir),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                status="error",
                stderr=f"Tool {tool_name} timed out after {timeout}s",
                exit_code=124,
                job_dir=job_dir,
            )

        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            # Check for known "insufficient data" exit from tools
            if "insufficient" in stderr.lower() or "minimum" in stderr.lower():
                return ToolResult(
                    status="insufficient_data",
                    stderr=stderr,
                    exit_code=proc.returncode,
                    job_dir=job_dir,
                )
            return ToolResult(
                status="error",
                stderr=stderr,
                exit_code=proc.returncode,
                job_dir=job_dir,
            )

        stdout = proc.stdout.strip()
        if not stdout:
            return ToolResult(status="ok", data={}, stderr=proc.stderr, job_dir=job_dir)

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            # Some tools print status line before JSON; try last valid JSON block
            for line in reversed(stdout.splitlines()):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                return ToolResult(
                    status="error",
                    stderr=f"Non-JSON output: {stdout[:200]}",
                    exit_code=proc.returncode,
                    job_dir=job_dir,
                )

        return ToolResult(status="ok", data=data, stderr=proc.stderr, job_dir=job_dir)

    def _patch_paths(self, spec: Any, job_dir: Path) -> Any:
        """Recursively replace '.tmp/' prefix in string values with job_dir."""
        if isinstance(spec, dict):
            return {k: self._patch_paths(v, job_dir) for k, v in spec.items()}
        if isinstance(spec, list):
            return [self._patch_paths(v, job_dir) for v in spec]
        if isinstance(spec, str) and spec.startswith(".tmp/"):
            return str(job_dir / spec[len(".tmp/"):])
        return spec
