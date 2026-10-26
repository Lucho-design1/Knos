"""A demand result's permanent page /r/<id>: drawn from the report the server keeps, its QR code reads back to its own
address, an unknown id answers 404 with one sentence, and each state that is not a full answer says which. SYNTHETIC
reports only; nothing asks Qloo."""
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from knos_wanted import qr, result_page, server
from knos_wanted.qloo_mcp import InProcess, Qloo

H = "ab" * 32


def _grid(svg: str) -> list[list[bool]]:
    n, px, q = (int(re.search(f'data-{k}="(\\d+)"', svg)[1]) for k in ("modules", "px", "quiet"))
    g = [[False] * n for _ in range(n)]
    for x, y in re.findall(r"M(\d+),(\d+)h", svg):
        g[int(y) // px - q][int(x) // px - q] = True
    return g


def test_the_qr_code_reads_back_for_every_length_a_version_6_code_holds():
    for text in ("x", "https://knos.onrender.com/r/" + "0" * 16, "y" * 106):
        assert qr.read(qr.encode(text)) == text and qr.read(_grid(qr.svg(text))) == text
    assert qr._ecc([32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17], 10) == [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]


def test_r_serves_the_kept_report_and_an_unknown_id_says_so():
    st = server.State(Qloo(InProcess(), mode="mock", sleep=lambda s: None), None)
    st.reports[H] = {"hash": H, "idea": "a SYNTHETIC tea", "decision": {"verdict": "REFUSE"}, "matches": [], "calls": [], "where": []}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(st))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/r/{H[:16]}", timeout=10) as r:
            page = r.read().decode()
        assert r.status == 200 and "a SYNTHETIC tea" in page and 'data-state="empty"' in page and 'id="r-share"' in page and "@media print" in page
        svg = re.search(r"<svg.*?</svg>", page, re.S)[0]
        assert qr.read(_grid(svg)) == f"{base}/r/{H[:16]}"
        try:
            urllib.request.urlopen(f"{base}/r/{'0' * 16}", timeout=10)
            raise AssertionError("an unknown id answered")
        except urllib.error.HTTPError as e:
            assert e.code == 404 and 'data-state="error"' in e.read().decode()
    finally:
        httpd.shutdown()


def test_each_state_that_is_not_a_full_answer_is_one_sentence():
    assert result_page.state_of(None) == "error"
    assert result_page.state_of({"matches": [{"id": "x"}], "stale": {"code": 429}}) == "outage"
    assert result_page.state_of({"matches": []}) == "empty"
    assert result_page.state_of({"matches": [{"id": "x"}], "where": []}) == "thin"
    assert all(s.endswith(".") and s.count(".") == 1 for s in result_page.SAY.values())
