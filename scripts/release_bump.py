#!/usr/bin/env python3
"""Atomic P9 release bump helper for Ouroboros.

Synchronizes all 12 version carrier files and trims the README Version History
table to maintain strict P9 row limits (<= 5 patch rows).
"""

from __future__ import annotations

import argparse
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ouroboros.tools.release_sync import bump_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="New semantic version (e.g. 7.4.14)")
    parser.add_argument("-d", "--description", required=True, help="Release description for README Version History")
    parser.add_argument("--date", help="Release date in YYYY-MM-DD format (default: today)")
    parser.add_argument("--repo", type=pathlib.Path, default=REPO_ROOT, help="Target repository directory (default: repo root)")
    args = parser.parse_args(argv)

    return bump_version(args.repo, args.version, args.description, args.date)


if __name__ == "__main__":
    sys.exit(main())
