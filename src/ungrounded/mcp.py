"""Read a tool catalogue straight from an MCP server over stdio.

    from ungrounded.mcp import list_tools
    tools = list_tools(["npx", "-y", "@playwright/mcp"])

Starts the server, runs the MCP handshake, pages through ``tools/list`` and
stops the server. Tools come back in Anthropic schema (``name``,
``description``, ``input_schema``), which every provider adapter accepts.
Nothing is executed: the server is only asked what tools it has.

Pure stdlib, so it adds no dependency.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import threading
from collections import deque
from typing import Dict, List, Optional, Sequence, Union

from .providers import SetupError

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "ungrounded", "version": "0"}


class _Server:
    """A stdio MCP server with line-delimited JSON-RPC and timed reads."""

    def __init__(self, command: List[str], env: Optional[Dict[str, str]], timeout: float):
        self.command = command
        self.timeout = timeout
        full_env = os.environ.copy()
        full_env.update(env or {})
        try:
            self.proc = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", env=full_env, bufsize=1)
        except FileNotFoundError:
            raise SetupError(
                f"Could not start the MCP server: {command[0]!r} was not found.\n"
                "Check the command, or that the program is installed and on your PATH.")
        self.lines: "queue.Queue[Optional[str]]" = queue.Queue()
        self.stderr_tail: deque = deque(maxlen=20)
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        self.next_id = 1

    def _pump_stdout(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def _pump_stderr(self):
        for line in self.proc.stderr:
            self.stderr_tail.append(line.rstrip())

    def _fail(self, what: str) -> SetupError:
        tail = "\n".join(f"    {l}" for l in list(self.stderr_tail)[-8:] if l)
        cmd = " ".join(shlex.quote(c) for c in self.command)
        msg = f"MCP server {what}.\n  command: {cmd}"
        if tail:
            msg += f"\n  last output on stderr:\n{tail}"
        return SetupError(msg)

    def send(self, msg: dict) -> None:
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise self._fail("exited before the handshake finished")

    def request(self, method: str, params: dict) -> dict:
        rid = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            try:
                line = self.lines.get(timeout=self.timeout)
            except queue.Empty:
                raise self._fail(f"did not answer {method!r} within {self.timeout:.0f}s")
            if line is None:
                raise self._fail(f"exited while waiting for {method!r}")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # servers sometimes log to stdout; skip anything that isn't JSON
            if not isinstance(msg, dict) or msg.get("id") != rid:
                continue  # notifications, or server-to-client requests we don't serve
            if "error" in msg:
                err = msg["error"]
                raise self._fail(f"returned an error for {method!r}: "
                                 f"{err.get('message', err)}")
            return msg.get("result") or {}

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def _to_anthropic(tool: dict) -> dict:
    return {"name": tool["name"],
            "description": tool.get("description") or "",
            "input_schema": tool.get("inputSchema") or {"type": "object", "properties": {}}}


def list_tools(command: Union[str, Sequence[str]], env: Optional[Dict[str, str]] = None,
               timeout: float = 60.0) -> List[dict]:
    """Start an MCP server, list its tools, stop it.

    ``command`` is the server's start command, as a string or argv list.
    ``env`` adds environment variables on top of the current environment;
    some servers need a placeholder token just to start. ``timeout`` applies
    to each response (``npx`` may need a while to download the server the
    first time).
    """
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv:
        raise SetupError("--mcp needs the command that starts your MCP server, "
                         "e.g. --mcp \"npx -y @playwright/mcp\"")
    server = _Server(argv, env, timeout)
    try:
        server.request("initialize", {"protocolVersion": PROTOCOL_VERSION,
                                      "capabilities": {}, "clientInfo": CLIENT_INFO})
        server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools: List[dict] = []
        cursor = None
        for _ in range(1000):  # guard against a server that never stops paging
            result = server.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += [_to_anthropic(t) for t in result.get("tools", []) if t.get("name")]
            cursor = result.get("nextCursor")
            if not cursor:
                break
    finally:
        server.close()
    if not tools:
        raise SetupError(
            "The MCP server started but reported no tools. Some servers only expose "
            "tools once configured; check its documentation for required settings "
            "and pass them with --mcp-env KEY=VALUE.")
    return tools


def parse_env(pairs: Optional[Sequence[str]]) -> Dict[str, str]:
    """Turn ``["KEY=VALUE", ...]`` into a dict, with a clear error for bad input."""
    out: Dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p or p.startswith("="):
            raise SetupError(f"--mcp-env expects KEY=VALUE, got {p!r}")
        k, v = p.split("=", 1)
        out[k] = v
    return out
