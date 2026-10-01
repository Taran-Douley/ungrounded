"""Reading a catalogue from an MCP server.

A fake stdio server stands in for a real one, so every path -- paging,
noise on stdout, required environment, crashes, hangs, protocol errors --
runs offline in a second.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ungrounded.mcp import list_tools, parse_env  # noqa: E402
from ungrounded.providers import SetupError  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "src")

FAKE_SERVER = textwrap.dedent('''
    import json, os, sys, time
    mode = sys.argv[1] if len(sys.argv) > 1 else "ok"
    if mode == "crash":
        print("fatal: missing configuration FOO_URL", file=sys.stderr, flush=True)
        sys.exit(1)
    if mode == "needs-env" and os.environ.get("FAKE_TOKEN") != "x":
        print("FAKE_TOKEN is required", file=sys.stderr, flush=True)
        sys.exit(1)
    PAGES = [
        [{"name": "fetch_page", "description": "Fetch a page.",
          "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}},
                          "required": ["url"]}}],
        [{"name": "search", "inputSchema": {"type": "object",
          "properties": {"q": {"type": "string"}}}},
         {"name": "no_schema", "description": "A tool with no input schema."}],
    ]
    def send(m):
        sys.stdout.write(json.dumps(m) + "\\n"); sys.stdout.flush()
    print("server starting up", flush=True)          # log noise on stdout
    for line in sys.stdin:
        m = json.loads(line)
        if "id" not in m:
            continue                                   # notifications
        if mode == "hang":
            time.sleep(30)
        if m["method"] == "initialize":
            send({"jsonrpc": "2.0", "method": "notifications/message", "params": {}})
            send({"jsonrpc": "2.0", "id": m["id"], "result": {
                "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "1"}}})
        elif m["method"] == "tools/list":
            if mode == "rpc-error":
                send({"jsonrpc": "2.0", "id": m["id"],
                      "error": {"code": -32603, "message": "not authorised"}})
                continue
            if mode == "empty":
                send({"jsonrpc": "2.0", "id": m["id"], "result": {"tools": []}})
                continue
            page = int((m.get("params") or {}).get("cursor") or 0)
            res = {"tools": PAGES[page]}
            if page + 1 < len(PAGES):
                res["nextCursor"] = str(page + 1)
            send({"jsonrpc": "2.0", "id": m["id"], "result": res})
''')


class FakeServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = os.path.join(cls.tmp.name, "fake_mcp.py")
        with open(cls.server, "w") as fh:
            fh.write(FAKE_SERVER)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cmd(self, mode="ok"):
        return [sys.executable, self.server, mode]


class ListTools(FakeServer):
    def test_reads_every_page_in_anthropic_schema(self):
        tools = list_tools(self.cmd())
        self.assertEqual([t["name"] for t in tools], ["fetch_page", "search", "no_schema"])
        self.assertEqual(tools[0]["input_schema"]["required"], ["url"])
        self.assertEqual(tools[1]["description"], "")
        self.assertEqual(tools[2]["input_schema"], {"type": "object", "properties": {}})

    def test_accepts_a_command_string(self):
        cmd = " ".join(f'"{c}"' for c in self.cmd())
        self.assertEqual(len(list_tools(cmd)), 3)

    def test_passes_environment_to_the_server(self):
        with self.assertRaises(SetupError):
            list_tools(self.cmd("needs-env"))
        self.assertEqual(len(list_tools(self.cmd("needs-env"), env={"FAKE_TOKEN": "x"})), 3)

    def test_crash_reports_the_servers_own_message(self):
        with self.assertRaises(SetupError) as cm:
            list_tools(self.cmd("crash"))
        self.assertIn("missing configuration FOO_URL", str(cm.exception))

    def test_hang_times_out_with_a_clear_message(self):
        with self.assertRaises(SetupError) as cm:
            list_tools(self.cmd("hang"), timeout=1)
        self.assertIn("did not answer 'initialize'", str(cm.exception))

    def test_protocol_error_is_reported(self):
        with self.assertRaises(SetupError) as cm:
            list_tools(self.cmd("rpc-error"))
        self.assertIn("not authorised", str(cm.exception))

    def test_no_tools_explains_what_to_check(self):
        with self.assertRaises(SetupError) as cm:
            list_tools(self.cmd("empty"))
        self.assertIn("--mcp-env", str(cm.exception))

    def test_missing_program_is_a_setup_error(self):
        with self.assertRaises(SetupError) as cm:
            list_tools(["definitely-not-a-real-mcp-server-binary"])
        self.assertIn("was not found", str(cm.exception))

    def test_parse_env(self):
        self.assertEqual(parse_env(["A=1", "B=x=y"]), {"A": "1", "B": "x=y"})
        self.assertEqual(parse_env(None), {})
        with self.assertRaises(SetupError):
            parse_env(["NOEQUALS"])


def cli(*args):
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.run([sys.executable, "-m", "ungrounded.cli", *args],
                          capture_output=True, text=True, env=env, timeout=120)


class Cli(FakeServer):
    def mcp(self, mode="ok"):
        return " ".join(f'"{c}"' for c in self.cmd(mode))

    def test_tools_writes_the_catalogue(self):
        out = os.path.join(self.tmp.name, "tools.json")
        r = cli("tools", "--mcp", self.mcp(), "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(json.load(open(out))), 3)

    def test_run_measures_the_servers_tools(self):
        r = cli("run", "--model", "mock", "--mcp", self.mcp(), "--decoy-name", "search",
                "--runs", "1", "--json", "--quiet")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["decoy"], "search")

    def test_tools_and_mcp_are_exclusive(self):
        r = cli("run", "--model", "mock", "--tools", "x.json", "--mcp", self.mcp())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not allowed with", r.stderr)

    def test_server_failure_is_not_a_traceback(self):
        r = cli("tools", "--mcp", self.mcp("crash"))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("missing configuration FOO_URL", r.stderr)


if __name__ == "__main__":
    unittest.main()
