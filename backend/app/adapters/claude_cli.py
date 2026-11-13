"""StructuredModel over the Claude Code CLI (`claude -p --json-schema`), e.g. Opus for taste profiling.

Uses the machine's Claude login. ANTHROPIC_API_KEY is removed from the child env by default because an
invalid/unrelated key there overrides the login.
"""
import json
import os
import subprocess


class ClaudeCLIError(RuntimeError):
    pass


class ClaudeCLI:
    def __init__(self, model: str = "claude-opus-5-5", binary: str = "claude", timeout_s: int = 600,
                 drop_env: tuple[str, ...] = ("ANTHROPIC_API_KEY",), runner=subprocess.run):
        self.model, self._binary, self._timeout, self._drop, self._run = model, binary, timeout_s, drop_env, runner

    def command(self, schema: dict) -> list[str]:
        return [self._binary, "-p", "--model", self.model, "--output-format", "json", "--json-schema", json.dumps(schema),
                "--no-session-persistence", "--strict-mcp-config", "--tools", ""]

    def generate(self, prompt: str, schema: dict) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in self._drop}
        proc = self._run(self.command(schema), input=prompt, capture_output=True, text=True, timeout=self._timeout, env=env)
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise ClaudeCLIError(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[:500]}") from e
        if out.get("is_error") or not isinstance(out.get("structured_output"), dict):
            raise ClaudeCLIError(f"claude failed: {str(out.get('result'))[:500]}")
        return out["structured_output"]
