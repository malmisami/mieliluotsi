"""Regenerate the synthetic pilot cohort used by the impact view and the professional's client list.

The backend also creates the file automatically on first use. Example:

    backend/.venv/bin/python scripts/generate_synthetic_cohort.py --size 50000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.config import settings  # noqa: E402
from app.support.cohort import generate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate a synthetic LUVN-like cohort CSV (all people are fictional).')
    parser.add_argument('--size', type=int, default=settings.SUPPORT_COHORT_SIZE, help='number of synthetic people')
    parser.add_argument('--seed', type=int, default=20260923, help='random seed (same seed = same file)')
    parser.add_argument('--out', type=Path, default=Path(settings.SUPPORT_COHORT_PATH), help='output CSV path')
    args = parser.parse_args()
    generate(args.out, args.size, args.seed)
    print(f'Wrote {args.size} synthetic people to {args.out}')


if __name__ == '__main__':
    main()
