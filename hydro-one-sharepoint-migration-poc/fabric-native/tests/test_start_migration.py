"""Tests for Start-FabricMigration.ps1 against a mock Fabric job API and a fake az.

The fake az reproduces what the real one does: it hands back a cached token until that
token is close to expiry. The mock API rejects an expired token with the same 401
TokenExpired body Hydro One saw (support case 2611050040004903).

Run:  python -m pytest tests -q
Set KEVIN_SCRIPT to also run the regression scenario against Hydro One's 27 Oct copy.
"""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "Start-FabricMigration.ps1"
WS = "11111111-1111-1111-1111-111111111111"
PIPE = "22222222-2222-2222-2222-222222222222"

FAKE_AZ_PY = r'''
import json, os, sys, time
state_file = os.environ["FAKE_AZ_STATE"]
with open(state_file) as f:
    st = json.load(f)
# Each entry is [token, seconds_left_when_issued]; the last one repeats.
tokens = st["tokens"]
i = min(st["calls"], len(tokens) - 1)
st["calls"] += 1
with open(state_file, "w") as f:
    json.dump(st, f)
tok, left = tokens[i]
exp = int(time.time()) + left
args = sys.argv[1:]
if "--query" in args:   # the old script asks for the bare token
    print(tok)
else:
    print(json.dumps({"accessToken": tok, "expires_on": exp,
                      "expiresOn": time.strftime("%Y-%m-%d %H:%M:%S.000000", time.localtime(exp)),
                      "tokenType": "Bearer"}))
'''


class Api:
    def __init__(self, jobs, expire_after=None, flaky_401=0, status_errors=0):
        # jobs: list of status sequences, one per run, e.g. [["InProgress", "Completed"]]
        self.jobs = [list(j) for j in jobs]
        self.expire_after = expire_after or {}   # token -> seconds after first use it expires
        self.first_seen = {}
        self.flaky_401 = flaky_401               # 401s to return on status GETs regardless of token
        self.status_errors = status_errors       # 500s to return on status GETs
        self.posts = []
        self.gets = 0
        self.lock = threading.Lock()


def make_handler(api):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body=None, headers=None):
            data = json.dumps(body).encode() if body is not None else b""
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _token_ok(self):
            tok = self.headers.get("Authorization", "").removeprefix("Bearer ")
            with api.lock:
                api.first_seen.setdefault(tok, time.time())
                limit = api.expire_after.get(tok)
                if limit is not None and time.time() - api.first_seen[tok] > limit:
                    return False
            return True

        def _expired(self):
            self._send(401, {"requestId": "x", "errorCode": "TokenExpired",
                             "message": "Access token has expired, resubmit with a new access token"})

        def do_GET(self):
            if not self._token_ok():
                return self._expired()
            if "/jobs/instances/" in self.path:
                n = int(self.path.rsplit("/", 1)[1])
                with api.lock:
                    api.gets += 1
                    if api.flaky_401 > 0:
                        api.flaky_401 -= 1
                        return self._expired()
                    if api.status_errors > 0:
                        api.status_errors -= 1
                        return self._send(500, {"errorCode": "InternalError"})
                    seq = api.jobs[n]
                    status = seq.pop(0) if len(seq) > 1 else seq[0]
                body = {"id": str(n), "status": status}
                if status == "Failed":
                    body["failureReason"] = {"errorCode": "ActivityFailed", "message": "notebook failed"}
                return self._send(200, body)
            if self.path.startswith(f"/v1/workspaces/{WS}/items"):
                return self._send(200, {"value": [{"id": PIPE, "displayName": "PL_Migrate_Master", "type": "DataPipeline"}]})
            self._send(404, {"errorCode": "NotFound"})

        def do_POST(self):
            if not self._token_ok():
                return self._expired()
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            with api.lock:
                n = len(api.posts)
                api.posts.append(body)
            port = self.server.server_address[1]
            self._send(202, None, {"Location": f"http://127.0.0.1:{port}/v1/workspaces/{WS}/items/{PIPE}/jobs/instances/{n}"})

    return H


@pytest.fixture
def env(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "fake_az.py").write_text(FAKE_AZ_PY)
    (bindir / "az.cmd").write_text(f'@"{sys.executable}" "%~dp0fake_az.py" %*\r\n')
    state = tmp_path / "az_state.json"

    def setup(tokens, sites=1):
        state.write_text(json.dumps({"tokens": tokens, "calls": 0}))
        cfg = {"sites": [{"siteUrl": f"https://contoso.sharepoint.com/sites/S{i}", "libraryName": "Documents",
                          "mode": "incremental"} for i in range(sites)]}
        cfgp = tmp_path / "config.json"
        cfgp.write_text(json.dumps(cfg))
        return cfgp

    def az_calls():
        return json.loads(state.read_text())["calls"]

    def run(api, cfgp, script=SCRIPT, extra=()):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(api))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            e = dict(os.environ)
            e["PATH"] = str(bindir) + os.pathsep + e["PATH"]
            e["FAKE_AZ_STATE"] = str(state)
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                   "-WorkspaceId", WS, "-ConfigPath", str(cfgp), "-PollSeconds", "1", *extra]
            if script == SCRIPT:
                cmd += ["-ApiRoot", f"http://127.0.0.1:{srv.server_address[1]}/v1"]
            p = subprocess.run(cmd, capture_output=True, text=True, env=e, timeout=300)
            return p.returncode, p.stdout + p.stderr
        finally:
            srv.shutdown()

    env.setup, env.run, env.az_calls = setup, run, az_calls
    return env


def test_cached_token_near_expiry_is_renewed_before_it_expires(env):
    # az first returns a cached token with 6 minutes left (inside the 10-minute margin),
    # then a fresh one. The API stops accepting the first after 3 seconds.
    cfg = env.setup([["tok-old", 360], ["tok-new", 3600]])
    api = Api([["InProgress"] * 6 + ["Completed"]], expire_after={"tok-old": 3})
    code, out = env.run(api, cfg)
    assert code == 0, out
    assert "401" not in out
    assert len(api.posts) == 1


def test_401_gets_a_new_token_and_retries_the_same_request(env):
    cfg = env.setup([["tok-a", 3600], ["tok-b", 3600]])
    api = Api([["InProgress", "Completed"]], flaky_401=1)
    code, out = env.run(api, cfg)
    assert code == 0, out
    assert "getting a new one and retrying" in out
    assert env.az_calls() >= 2          # the retry asked az again
    assert len(api.posts) == 1


def test_failed_status_checks_keep_polling_the_same_job(env):
    # Two 401s in a row (retry also rejected) and three 500s: the script must keep
    # watching the same job instance and must not submit another run.
    cfg = env.setup([["tok", 3600]])
    api = Api([["InProgress", "Completed"]], flaky_401=2, status_errors=3)
    code, out = env.run(api, cfg)
    assert code == 0, out
    assert "status check failed" in out
    assert len(api.posts) == 1


def test_parameters_are_sent_as_plain_values(env):
    cfg = env.setup([["tok", 3600]])
    api = Api([["Completed"]])
    code, out = env.run(api, cfg)
    assert code == 0, out
    params = api.posts[0]["executionData"]["parameters"]
    assert params == {"SiteUrl": "https://contoso.sharepoint.com/sites/S0", "LibraryName": "Documents",
                      "Mode": "incremental"}


def test_runs_libraries_in_turn(env):
    cfg = env.setup([["tok", 3600]], sites=2)
    api = Api([["InProgress", "Completed"], ["Completed"]])
    code, out = env.run(api, cfg)
    assert code == 0, out
    assert len(api.posts) == 2
    assert "All 2 library run(s) completed" in out


def test_failed_run_stops_and_exits_nonzero(env):
    cfg = env.setup([["tok", 3600]], sites=2)
    api = Api([["InProgress", "Failed"], ["Completed"]])
    code, out = env.run(api, cfg)
    assert code != 0
    assert "notebook failed" in out
    assert len(api.posts) == 1          # second library not started


def test_status_unknown_after_repeated_failures_does_not_start_next_library(env):
    cfg = env.setup([["tok", 3600]], sites=2)
    api = Api([["InProgress"]], status_errors=1000)
    code, out = env.run(api, cfg, extra=["-ContinueOnError"])
    assert code != 0
    assert "was NOT cancelled" in out
    assert len(api.posts) == 1          # even with -ContinueOnError


def test_whatif_makes_no_calls(env):
    cfg = env.setup([["tok", 3600]])
    api = Api([["Completed"]])
    code, out = env.run(api, cfg, extra=["-WhatIf"])
    assert code == 0, out
    assert env.az_calls() == 0 and not api.posts


KEVIN = os.environ.get("KEVIN_SCRIPT")


@pytest.mark.skipif(not KEVIN, reason="set KEVIN_SCRIPT to Hydro One's copy to reproduce the case")
def test_regression_hydro_one_copy_fails_on_near_expiry_token(env, tmp_path):
    # Same scenario as the first test, against the copy Hydro One ran. Its API root is
    # hardcoded, so it is pointed at the mock through a patched copy.
    cfg = env.setup([["tok-old", 360], ["tok-new", 3600]])
    api = Api([["InProgress"] * 6 + ["Completed"]], expire_after={"tok-old": 3})
    src = Path(KEVIN).read_text(encoding="utf-8")
    # Start the mock first so the port is known, then patch the URL in.
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(api))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        patched = tmp_path / "Kevin-Start-FabricMigration.ps1"
        patched.write_text(src.replace("https://api.fabric.microsoft.com/v1",
                                       f"http://127.0.0.1:{srv.server_address[1]}/v1"), encoding="utf-8")
        e = dict(os.environ)
        e["PATH"] = str(tmp_path / "bin") + os.pathsep + e["PATH"]
        e["FAKE_AZ_STATE"] = str(tmp_path / "az_state.json")
        p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(patched),
                            "-WorkspaceId", WS, "-ConfigPath", str(cfg), "-PollSeconds", "1"],
                           capture_output=True, text=True, env=e, timeout=300)
    finally:
        srv.shutdown()
    out = p.stdout + p.stderr
    assert p.returncode != 0
    assert "TokenExpired" in out
