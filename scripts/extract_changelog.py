"""Print the CHANGELOG.md section body for a given version.

Usage:

    python scripts/extract_changelog.py 0.3.0

Reads ``CHANGELOG.md`` at the project root, locates the
``## [<version>]`` heading, and prints everything up to (but not
including) the next ``## [`` heading. Exits with status 1 if no
matching section is found so CI can fail loudly on a missing entry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"


def extract(version: str, text: str) -> str | None:
    # Match `## [0.3.0]` with optional trailing ` - 2026-04-19` etc.
    start_re = re.compile(
        rf"^##\s+\[{re.escape(version)}\](?:\s.*)?$",
        re.MULTILINE,
    )
    start = start_re.search(text)
    if start is None:
        return None

    end_re = re.compile(r"^##\s+\[", re.MULTILINE)
    end = end_re.search(text, start.end())
    body = text[start.end() : end.start() if end else len(text)]
    return body.strip()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <version>", file=sys.stderr)
        return 2
    version = argv[1]
    body = extract(version, CHANGELOG.read_text(encoding="utf-8"))
    if body is None:
        print(f"no CHANGELOG entry for version {version!r}", file=sys.stderr)
        return 1
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
