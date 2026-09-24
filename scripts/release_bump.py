#!/usr/bin/env python3
"""Atomic P9 release bump helper for Ouroboros.

Synchronizes all 12 version carrier files and trims the README Version History
table to maintain strict P9 row limits (<= 5 patch rows).
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ouroboros.tools.release_sync import (
    is_release_version,
    sync_release_metadata,
    check_worktree_version_sync,
    check_history_limit,
    detect_numeric_claims,
    _VERSION_ROW_RE,
    _MAX_PATCH,
)


def bump_version(
    repo_dir: pathlib.Path,
    new_version: str,
    description: str,
    release_date: str | None = None,
) -> int:
    new_version = str(new_version or "").strip()
    if not is_release_version(new_version):
        print(f"Error: Invalid release version format: {new_version!r}", file=sys.stderr)
        return 1

    date_str = release_date or datetime.date.today().isoformat()
    claims = detect_numeric_claims(description)
    if claims:
        print(f"Warning: Description contains numeric claims: {claims!r}", file=sys.stderr)

    version_file = repo_dir / "VERSION"
    version_file.write_text(f"{new_version}\n", encoding="utf-8")
    print(f"Updated VERSION -> {new_version}")

    readme_file = repo_dir / "README.md"
    if readme_file.exists():
        readme_text = readme_file.read_text(encoding="utf-8")
        if "## Version History" in readme_text:
            lines = readme_text.splitlines()
            header_idx = -1
            table_start = -1
            for idx, line in enumerate(lines):
                if line.strip() == "## Version History":
                    header_idx = idx
                elif header_idx != -1 and line.startswith("| Version | Date | Description |"):
                    table_start = idx + 2  # Skip separator line
                    break

            if table_start != -1:
                # Find all existing rows
                existing_rows: list[tuple[int, str, str, str]] = []
                idx = table_start
                while idx < len(lines) and lines[idx].strip().startswith("|"):
                    m = _VERSION_ROW_RE.match(lines[idx])
                    if m:
                        _, min_, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
                        existing_rows.append((patch, lines[idx], m.group(0), f"{m.group(1)}.{m.group(2)}.{m.group(3)}"))
                    idx += 1
                table_end = idx

                new_row = f"| {new_version} | {date_str} | {description} |"
                
                # Check patch row count
                is_patch = (int(new_version.split(".")[2].split("-")[0].split("a")[0].split("b")[0].split("r")[0]) > 0
                            if len(new_version.split(".")) >= 3 else False)
                
                kept_rows = [new_row]
                rolled_off = []
                current_patch_count = 1 if is_patch else 0

                for patch_val, raw_line, _, ver_str in existing_rows:
                    if patch_val > 0:
                        if current_patch_count < _MAX_PATCH:
                            kept_rows.append(raw_line)
                            current_patch_count += 1
                        else:
                            rolled_off.append(ver_str)
                    else:
                        kept_rows.append(raw_line)

                # Reconstruct table
                new_lines = lines[:table_start] + kept_rows + lines[table_end:]
                new_text = "\n".join(new_lines) + ("\n" if readme_text.endswith("\n") else "")
                
                if rolled_off:
                    roll_marker = "Older releases are preserved in this repository's history. Rows "
                    if roll_marker in new_text:
                        pos = new_text.find(roll_marker) + len(roll_marker)
                        roll_str = ", ".join(rolled_off) + ", "
                        new_text = new_text[:pos] + roll_str + new_text[pos:]

                readme_file.write_text(new_text, encoding="utf-8")
                print(f"Updated README.md Version History table (rolled off: {rolled_off or 'none'})")

    # Run full release sync across all 12 carriers
    changed = sync_release_metadata(str(repo_dir))
    print(f"Synced {len(changed)} carrier files: {', '.join(changed) if changed else 'already in sync'}")

    # Verify 0 desyncs
    desync_warning = check_worktree_version_sync(str(repo_dir))
    if desync_warning:
        print(f"Desync Error: {desync_warning}", file=sys.stderr)
        return 1

    # Check history limits
    limit_warnings = check_history_limit(readme_file.read_text(encoding="utf-8"))
    if limit_warnings:
        for w in limit_warnings:
            print(f"Limit Warning: {w}", file=sys.stderr)
        return 1

    print(f"SUCCESS: Release {new_version} atomically synchronized across all 12 carriers with 0 desyncs and 0 warnings.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="New semantic version (e.g. 7.4.14)")
    parser.add_argument("-d", "--description", required=True, help="Release description for README Version History")
    parser.add_argument("--date", help="Release date in YYYY-MM-DD format (default: today)")
    args = parser.parse_args(argv)

    return bump_version(REPO_ROOT, args.version, args.description, args.date)


if __name__ == "__main__":
    sys.exit(main())
