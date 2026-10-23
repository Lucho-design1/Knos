"""Import Knos's journal export (enterprise.export(..., "journal"), GET /api/company/export?format=journal) into open source
ERPs through their own APIs, then read the entries back and compare them with the file.

  Odoo Community   XML-RPC (/xmlrpc/2/common + /xmlrpc/2/object): account.account per Knos account, one posted account.move
                   (journal entry) per order, read back from account.move.line.
  ERPNext          Frappe REST (/api/resource): Account per Knos account under the company's tree, one submitted Journal
                   Entry per order, read back from GL Entry.

Both are run against local containers; the recorded results are what the app's Teams
page shows (proofs.py). Every line of the file says TEST MONEY: devnet test units, never real money."""
from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
import xmlrpc.client
from collections import OrderedDict, defaultdict

# Knos account -> (short code, Odoo account_type, ERPNext parent group, ERPNext root type)
ACCOUNTS = {
    "Assets:Knos escrow": ("KNOS101", "asset_current", "Current Assets", "Asset"),
    "Assets:Refunds receivable": ("KNOS102", "asset_current", "Current Assets", "Asset"),
    "Liabilities:Milestone commitments": ("KNOS201", "liability_current", "Current Liabilities", "Liability"),
    "Expenses:Milestones paid": ("KNOS501", "expense", "Indirect Expenses", "Expense"),
}


class ImportError_(ValueError):
    pass


def entries(text: str) -> list[dict]:
    """The journal CSV as balanced entries: one per (reference, status), each with its debit and credit lines."""
    rows = list(csv.DictReader(io.StringIO(text)))
    need = {"date", "description", "account", "amount", "reference", "status"}
    if not rows or not need <= set(rows[0]):
        raise ImportError_("not a Knos journal export (columns: " + ", ".join(sorted(need)) + ")")
    out: "OrderedDict[tuple, dict]" = OrderedDict()
    for r in rows:
        if r["account"] not in ACCOUNTS:
            raise ImportError_(f"unknown account {r['account']!r}")
        cents = round(float(r["amount"]) * 100)
        e = out.setdefault((r["reference"], r["status"]), {"date": r["date"], "ref": f"{r['reference']} {r['status']}",
                                                           "description": r["description"], "lines": []})
        e["lines"].append({"account": r["account"], "debit": max(cents, 0), "credit": max(-cents, 0)})
    for e in out.values():
        if sum(x["debit"] for x in e["lines"]) != sum(x["credit"] for x in e["lines"]):
            raise ImportError_(f"entry {e['ref']} does not balance")
    return list(out.values())


def balances(es: list[dict]) -> dict[str, float]:
    b: dict[str, int] = defaultdict(int)
    for e in es:
        for x in e["lines"]:
            b[x["account"]] += x["debit"] - x["credit"]
    return {k: v / 100 for k, v in sorted(b.items())}


# ---- Odoo (XML-RPC) --------------------------------------------------------------------------------------------------
def to_odoo(text: str, url: str, db: str, user: str, password: str, proxy=xmlrpc.client.ServerProxy) -> dict:
    es = entries(text)
    common = proxy(f"{url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(db, user, password, {})
    if not uid:
        raise ImportError_("Odoo refused the sign-in")
    m = proxy(f"{url}/xmlrpc/2/object", allow_none=True)
    x = lambda model, method, *a, **kw: m.execute_kw(db, uid, password, model, method, list(a), kw)   # noqa: E731
    journal = x("account.journal", "search", [["type", "=", "general"]], limit=1)
    if not journal:
        raise ImportError_("Odoo has no general journal (install Invoicing/Accounting with a chart of accounts)")
    acc = {}
    for name, (code, kind, _, _) in ACCOUNTS.items():
        got = x("account.account", "search", [["code", "=", code]], limit=1)
        acc[name] = got[0] if got else x("account.account", "create", {"code": code, "name": f"{name} (TEST MONEY)", "account_type": kind})
    moves = []
    for e in es:
        old = x("account.move", "search", [["ref", "=", e["ref"]], ["state", "=", "posted"]], limit=1)
        if old:
            moves.append(old[0])
            continue
        mid = x("account.move", "create", {"move_type": "entry", "journal_id": journal[0], "date": e["date"], "ref": e["ref"],
                                           "line_ids": [(0, 0, {"account_id": acc[li["account"]], "name": e["description"][:120],
                                                                "debit": li["debit"] / 100, "credit": li["credit"] / 100})
                                                        for li in e["lines"]]})
        x("account.move", "action_post", [mid])
        moves.append(mid)
    lines = x("account.move.line", "search_read", [["move_id", "in", moves]], fields=["account_id", "debit", "credit", "parent_state"])
    code_of = {v: k for k, v in acc.items()}
    back: dict[str, int] = defaultdict(int)
    for li in lines:
        back[code_of[li["account_id"][0]]] += round(li["debit"] * 100) - round(li["credit"] * 100)
    read = {k: v / 100 for k, v in sorted(back.items())}
    want = balances(es)
    return {"erp": "Odoo Community", "entries": len(es), "moves": moves, "posted": all(li["parent_state"] == "posted" for li in lines),
            "read_back": read, "expected": want, "match": read == want}


# ---- ERPNext (Frappe REST) -------------------------------------------------------------------------------------------
class Frappe:
    def __init__(self, url: str, user: str, password: str, opener=None):
        import http.cookiejar
        self.url = url.rstrip("/")
        self.op = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call("POST", "/api/method/login", {"usr": user, "pwd": password})

    def call(self, method: str, path: str, body: dict | None = None, query: dict | None = None):
        u = self.url + path + ("?" + urllib.parse.urlencode(query) if query else "")
        req = urllib.request.Request(u, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Accept": "application/json", "Content-Type": "application/json"})
        try:
            with self.op.open(req, timeout=120) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise ImportError_(f"ERPNext answered HTTP {e.code} on {path}: {e.read()[:300].decode(errors='replace')}") from None

    def find(self, doctype: str, filters: list, fields=("name",)) -> list[dict]:
        return self.call("GET", f"/api/resource/{urllib.parse.quote(doctype)}",
                         query={"filters": json.dumps(filters), "fields": json.dumps(list(fields)), "limit_page_length": 500})["data"]

    def make(self, doctype: str, doc: dict) -> dict:
        return self.call("POST", f"/api/resource/{urllib.parse.quote(doctype)}", doc)["data"]


def to_erpnext(text: str, f: Frappe, company: str) -> dict:
    es = entries(text)
    abbr = f.find("Company", [["name", "=", company]], ["abbr"])
    if not abbr:
        raise ImportError_(f"ERPNext has no company {company!r}")
    abbr = abbr[0]["abbr"]
    acc = {}
    for name, (code, _, parent, _) in ACCOUNTS.items():
        label = f"{code} {name.replace(':', ' - ')} TEST MONEY"
        got = f.find("Account", [["account_name", "=", label], ["company", "=", company]])
        acc[name] = got[0]["name"] if got else f.make("Account", {"account_name": label, "parent_account": f"{parent} - {abbr}",
                                                                    "company": company, "is_group": 0})["name"]
    jes = []
    for e in es:
        old = f.find("Journal Entry", [["cheque_no", "=", e["ref"]], ["docstatus", "=", 1]])
        if old:
            jes.append(old[0]["name"])
            continue
        doc = f.make("Journal Entry", {"voucher_type": "Journal Entry", "company": company, "posting_date": e["date"],
                                       "cheque_no": e["ref"], "cheque_date": e["date"], "user_remark": e["description"][:140], "docstatus": 1,
                                       "accounts": [{"account": acc[li["account"]], "debit_in_account_currency": li["debit"] / 100,
                                                     "credit_in_account_currency": li["credit"] / 100} for li in e["lines"]]})
        jes.append(doc["name"])
    gl = f.find("GL Entry", [["voucher_no", "in", jes], ["is_cancelled", "=", 0]], ["account", "debit", "credit"])
    name_of = {v: k for k, v in acc.items()}
    back: dict[str, int] = defaultdict(int)
    for g in gl:
        back[name_of[g["account"]]] += round(float(g["debit"]) * 100) - round(float(g["credit"]) * 100)
    read = {k: v / 100 for k, v in sorted(back.items())}
    want = balances(es)
    return {"erp": "ERPNext", "entries": len(es), "journal_entries": jes, "gl_entries": len(gl), "read_back": read,
            "expected": want, "match": read == want}
