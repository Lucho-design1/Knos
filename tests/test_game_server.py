"""The players' page and JSON API, and the MCP tools: people and agents through the same door."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from _game import TASK, FakeJudge, attempt

from knos.autoresearch import task as artask
from knos.game import server, tools
from knos.game.engine import Game


@pytest.fixture()
def game(tmp_path):
    t = artask.load(TASK)
    return Game.create(tmp_path / "g", TASK, title="Server game", judge=FakeJudge(t))


@pytest.fixture()
def url(game):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(game))
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _get(u):
    with urllib.request.urlopen(u, timeout=10) as r:
        return r.status, r.headers, r.read().decode()


def _post(u, body):
    req = urllib.request.Request(u, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_a_person_plays_through_the_page_api(url, game):
    code, headers, page = _get(url + "/")
    assert code == 200 and "Knos game" in page and "/static/game.js" in page and "script-src 'self'" in headers["Content-Security-Policy"]
    assert _get(url + "/static/game.js")[0] == 200
    st = json.loads(_get(url + "/api/state")[2])
    assert st["title"] == "Server game" and st["editable"] == "train.py" and "sealed" in st["never_shown"]
    assert _get(url + "/api/baseline")[2] == game.baseline()
    assert _get(url + "/api/data?which=val")[2].startswith("x0,")
    code, me = _post(url + "/api/join", {"name": "ada", "payee": "So11111111111111111111111111111111111111112"})
    assert code == 200 and me["player"] and me["key"]
    code, a = _post(url + "/api/submit", {"player": me["player"], "key": me["key"], "file": attempt(game.baseline(), 0.81, 0.8)})
    assert code == 200 and a["decision"] == "scored" and a["shown"] == 0.81
    assert _post(url + "/api/submit", {"player": me["player"], "key": "wrong", "file": "x"}) == (400, {"error": "wrong player key"})
    code, mine = _post(url + "/api/mine", {"player": me["player"], "key": me["key"]})
    assert code == 200 and mine["attempts"][0]["n"] == 1
    board = json.loads(_get(url + "/api/board")[2])["board"]
    assert board[0]["name"] == "ada" and "key" not in json.dumps(board)
    assert _post(url + "/api/nothing", {})[0] == 404


def test_the_page_never_puts_server_text_into_html():
    js = (server.STATIC / "game.js").read_text()
    assert "innerHTML" not in js and "textContent" in js


def test_agents_play_the_same_game_over_mcp(game, monkeypatch):
    from knos import mcp
    monkeypatch.delenv(tools.ENV, raising=False)
    assert not any(t["name"].startswith("knos_game_") for t in mcp.Server().answer({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"])
    monkeypatch.setenv(tools.ENV, str(game.root))
    tools._GAMES[str(game.root)] = game                    # the server's process holds the game (here: with the fast judge)
    names = {t["name"] for t in mcp.Server().answer({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}
    assert {"knos_game_state", "knos_game_join", "knos_game_submit", "knos_game_board", "knos_game_mine", "knos_game_data"} <= names
    sub = next(t for t in mcp.GAME_TOOLS if t["name"] == "knos_game_submit")
    assert sub["_meta"]["knos/runsCode"] is True and sub["annotations"]["readOnlyHint"] is False
    s = mcp.Server()

    def call(name, args):
        got = s.answer({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})["result"]
        return got
    st = call("knos_game_state", {})["structuredContent"]
    assert st["untrusted"]["program"] and "train.py" == st["editable"]
    me = call("knos_game_join", {"name": "claude-player", "kind": "agent", "label": "Claude Agent SDK"})["structuredContent"]
    got = call("knos_game_submit", {"player": me["player"], "key": me["key"], "file": attempt(game.baseline(), 0.77, 0.7)})["structuredContent"]
    assert got["decision"] == "scored"
    bad = call("knos_game_submit", {"player": me["player"], "key": "nope", "file": "x"})
    assert bad["isError"] and "wrong player key" in bad["content"][0]["text"]
    assert call("knos_game_board", {})["structuredContent"]["board"][0]["label"] == "Claude Agent SDK"
    tools._GAMES.pop(str(game.root), None)
