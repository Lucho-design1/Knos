"""The cutover of the published workflows on the 0.3.34 branch: every
caller, template, site page, SDK example and terms 3 document names drexthealpha/Knos/.github/workflows/...@<the same
commit>, and `scripts/release.py workflows` publishes into a worktree of the `workflows-<sha12>` tags of this repository."""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OLD, NEW = "drexthealpha/knos-workflows", "drexthealpha/Knos"
def _published_pin() -> str:
    """The published commit the examples name, read by pinned_workflows' own reader (a release moves it by design:
    `release.py workflows`, then `pinned_workflows.py stamp`). Never the placeholder; always a full commit sha."""
    spec = importlib.util.spec_from_file_location("pinned_workflows_pin", ROOT / "scripts" / "pinned_workflows.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pin = mod.pin()
    assert pin != mod.PLACEHOLDER and re.fullmatch(r"[0-9a-f]{40}", pin), pin
    return pin


PIN = _published_pin()


def _script(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_cutover", ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- the tree names one home, the new one ----------------------------------------------------------------------------

def test_every_caller_page_and_template_names_the_monorepo_at_the_same_commit():
    pub = _script("pinned_workflows")
    assert pub.home() == NEW and pub.pin() == PIN and pub.inconsistencies() == []
    callers = [*sorted((ROOT / "examples").glob("*.yml")), ROOT / ".github" / "workflows" / "knos.yml", ROOT / ".github" / "workflows" / "knos-check.yml",
               *sorted((ROOT / "templates").rglob("*.yml")), ROOT / "web" / "front.js", ROOT / "web" / "install.js"]
    named = 0
    for path in callers:
        text = path.read_text(encoding="utf-8")
        assert OLD + "/.github/workflows/" not in text and f"{OLD}/{PIN}" not in text, path
        for home, ref in re.findall(r"(drexthealpha/[\w-]+)/\.github/workflows/(?:fund|prove|check|attest)\.yml@([0-9a-f]{40})", text):
            assert (home, ref) == (NEW, PIN), path
            named += 1
    assert named >= 10
    # the JavaScript client's example and the offers an agent copies pin the same home
    assert f'wfRepo: "{NEW}", wfSha: "{PIN}"' in (ROOT / "sdk" / "settle" / "README.md").read_text(encoding="utf-8")
    for offer in ("agent_pays_agent", "x402_attested"):
        assert json.loads((ROOT / "examples" / offer / "offer.devnet.json").read_text(encoding="utf-8"))["wfRepo"] == NEW
    fixtures = (ROOT / "sdk" / "settle" / "fixtures.json").read_text(encoding="utf-8")
    assert f'"wf_repo": "{NEW}"' in fixtures and OLD not in fixtures


def test_a_commit_of_the_new_home_named_inside_the_wheel_is_caught(tmp_path, monkeypatch):
    pub = _script("pinned_workflows")
    root = tmp_path / "repo"
    for rel in ("README.md", "README.pypi.md", "src/knos/__init__.py", "terms/index.json"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, root / rel)
    monkeypatch.setattr(pub, "ROOT", root)
    assert pub.in_the_wheel() == []
    readme = root / "README.pypi.md"
    for line, home in ((f"uses: {NEW}/.github/workflows/prove.yml@{'c' * 40}", NEW), (f"{NEW}/{'c' * 40}/requirements/sign.txt", NEW),
                       (f"uses: {OLD}/.github/workflows/prove.yml@{'c' * 40}", OLD)):
        readme.write_text(line + "\n", encoding="utf-8")
        said = pub.in_the_wheel()
        assert len(said) == 1 and said[0].startswith(f"README.pypi.md names a commit of {home}, and it is part of the wheel"), line
    # a link to a commit of Knos that is not a published workflow is not the published set
    readme.write_text(f"https://github.com/{NEW}/blob/{'c' * 40}/README.md and {NEW}/.github/workflows/supplier.yml@{'c' * 40}\n", encoding="utf-8")
    assert pub.in_the_wheel() == []


# ---- terms 3: version 2 names the new home, version 1 stays -----------------------------------------------------------

@pytest.mark.parametrize("name", ["bug-fix", "dataset-batch", "migration"])
def test_version_2_of_each_terms_document_is_version_1_moved(name):
    from knos import terms3
    v1 = json.loads((ROOT / "terms" / "3" / name / "1.json").read_text(encoding="utf-8"))
    v2 = json.loads((ROOT / "terms" / "3" / name / "2.json").read_text(encoding="utf-8"))
    assert v2 == terms3.moved(v1) and v2["version"] == 2 and terms3.digest(v2) != terms3.digest(v1)
    assert OLD not in json.dumps(v2) and terms3.MONOREPO_WORKFLOWS in json.dumps(v2)
    assert OLD + "/.github/workflows/" in json.dumps(v1)                 # the version orders were funded on is kept
    assert terms3.evaluator_allowed(v2, terms3.GITHUB, "acme/widgets", terms3.MONOREPO_WORKFLOWS + "prove.yml@" + PIN) == "own"
    assert terms3.evaluator_allowed(v2, terms3.GITHUB, "acme/widgets", terms3.OLD_WORKFLOWS + "prove.yml@" + PIN) is None
    assert terms3.current(name) == terms3.moved(terms3.template(name))


def test_the_registry_publishes_nothing_more_and_support_resolution_keeps_its_version():
    reg = _script("terms_registry")
    assert reg.build(write=False) == []
    rows = {(r["name"], r["version"]) for r in reg.check3()}
    assert {("bug-fix", 2), ("dataset-batch", 2), ("migration", 2), ("support-resolution", 1)} <= rows
    assert ("support-resolution", 2) not in rows                          # it names no workflow: nothing to move


# ---- release.py workflows: a worktree of the `workflows-<sha12>` tags ------------------------------------------------------

def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A repository with an origin, one published set kept by its tag `workflows-<sha12>` (no branch), and a detached
    worktree at that tag."""
    if not shutil.which("git"):
        pytest.skip("needs git")
    origin, knos = tmp_path / "origin.git", tmp_path / "knos"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    knos.mkdir()
    _git("init", "-q", "-b", "main", cwd=knos)
    _git("config", "user.name", "t", cwd=knos)                                   # the commit release.py makes needs an author
    _git("config", "user.email", "t@example.com", cwd=knos)
    (knos / "README.md").write_text("knos\n", encoding="utf-8")
    _git("add", "-A", cwd=knos)
    _git("commit", "-q", "-m", "main", cwd=knos)
    _git("checkout", "-q", "--orphan", "workflows", cwd=knos)
    _git("rm", "-q", "-rf", ".", cwd=knos)
    (knos / "README.md").write_text("an earlier published set\n", encoding="utf-8")
    _git("add", "-A", cwd=knos)
    _git("commit", "-q", "-m", "knos 0.3.28: the workflows", cwd=knos)
    first = _git("rev-parse", "HEAD", cwd=knos)
    _git("tag", f"workflows-{first[:12]}", first, cwd=knos)
    _git("checkout", "-q", "main", cwd=knos)
    _git("branch", "-q", "-D", "workflows", cwd=knos)                           # the tag keeps the set: no branch
    _git("remote", "add", "origin", str(origin), cwd=knos)
    _git("push", "-q", "origin", "main", f"refs/tags/workflows-{first[:12]}", cwd=knos)
    _git("worktree", "add", "-q", "--detach", str(tmp_path / "wf"), f"workflows-{first[:12]}", cwd=knos)
    rel = _script("release")
    pub = _script("pinned_workflows")
    files = {".github/workflows/prove.yml": b"on: workflow_call\njobs: {}\n", "requirements/sign.txt": b"solders==1 --hash=sha256:" + b"0" * 64 + b"\n",
             "README.md": b"# the published set\n", "LICENSE": b"MIT\n"}
    monkeypatch.setattr(pub, "published", lambda lock, spec: dict(files))
    monkeypatch.setattr(pub, "_own_lock", lambda: "sign.txt")
    monkeypatch.setattr(pub, "_read", lambda name: "")
    monkeypatch.setattr(rel, "_load", lambda name: pub)
    monkeypatch.setattr(rel, "ROOT", knos)
    return rel, pub, files, knos, origin, tmp_path / "wf"


def test_release_workflows_commits_tags_and_pushes_the_tag_only(repo, capsys):
    rel, pub, files, knos, origin, wf = repo
    assert rel.workflows_cmd(wf) == 0
    sha = _git("rev-parse", "HEAD", cwd=wf)
    tag = f"workflows-{sha[:12]}"
    assert _git("rev-parse", "HEAD^{tree}", cwd=wf) == pub.tree_id(files)
    assert _git("rev-parse", f"{tag}^{{commit}}", cwd=knos) == sha
    remote = _git("ls-remote", str(origin), cwd=knos)
    assert f"{sha}\trefs/tags/{tag}" in remote and "refs/heads/workflows" not in remote, remote   # a tag, never a branch
    assert _git("rev-list", "--count", tag, cwd=knos) == "2"                   # the new set's parent is the earlier published set
    out = capsys.readouterr().out
    assert f"tagged {tag}" in out and f"Pushed {tag} to origin" in out and f"python scripts/pinned_workflows.py stamp {sha}" in out
    # again: nothing to commit, the same tag, nothing moves
    assert rel.workflows_cmd(wf) == 0 and _git("rev-parse", "HEAD", cwd=wf) == sha
    assert "nothing to commit" in capsys.readouterr().out


def test_release_workflows_without_the_push_leaves_origin_as_it_was(repo, capsys):
    rel, _pub, _files, knos, origin, wf = repo
    before = _git("ls-remote", str(origin), cwd=knos)
    assert rel.workflows_cmd(wf, push=False) == 0
    assert _git("ls-remote", str(origin), cwd=knos) == before and "Not pushed (--no-push)" in capsys.readouterr().out


def test_release_workflows_refuses_anything_but_a_detached_worktree_at_a_published_tag(repo, tmp_path):
    rel, _pub, _files, knos, _origin, wf = repo
    with pytest.raises(SystemExit, match="not a worktree at a published workflows-\\* tag"):
        rel.workflows_cmd(tmp_path / "nowhere")
    with pytest.raises(SystemExit, match="is on the branch main, not a detached HEAD"):
        rel.workflows_cmd(knos)                                                   # the main checkout
    old = tmp_path / "knos-workflows"                                             # a checkout of the old home: its own repository
    old.mkdir()
    _git("init", "-q", "-b", "main", cwd=old)
    (old / "x").write_text("x", encoding="utf-8")
    _git("add", "-A", cwd=old)
    _git("commit", "-q", "-m", "x", cwd=old)
    with pytest.raises(SystemExit, match="A checkout of drexthealpha/knos-workflows is the old home"):
        rel.workflows_cmd(old)
    _git("checkout", "-q", "--detach", "main", cwd=wf)                            # detached, but at a commit no tag publishes
    with pytest.raises(SystemExit, match="which no workflows-\\* tag names"):
        rel.workflows_cmd(wf)


def test_release_workflows_never_moves_a_published_tag(repo):
    rel, pub, files, knos, _origin, wf = repo
    rel.workflows_cmd(wf, push=False)
    sha = _git("rev-parse", "HEAD", cwd=wf)
    _git("tag", "-d", f"workflows-{sha[:12]}", cwd=knos)
    _git("tag", f"workflows-{sha[:12]}", "main", cwd=knos)                       # a tag of that name on another commit
    with pytest.raises(SystemExit, match="a published tag never moves"):
        rel.workflows_cmd(wf, push=False)
