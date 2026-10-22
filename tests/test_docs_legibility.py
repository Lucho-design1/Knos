"""Docs legibility (TASK-CHAMPION T6): no prose paragraph of the README or docs/ runs past 60 words, the generated documents
included (scripts/split_paragraphs.py --strict; a generator splits its own)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_paragraph_runs_past_sixty_words_where_a_sentence_ends():
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "split_paragraphs.py"), "--check", "--strict"], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
