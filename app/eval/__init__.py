"""Evaluation harness: fixture-backed smoke tests plus optional live checks.

Set EVAL_LIVE=1 to hit the real UniProt and BioLM APIs instead of the
recorded fixtures in app/eval/fixtures/.
"""

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
