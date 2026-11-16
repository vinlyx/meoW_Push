"""Extract one version's section from CHANGELOG.md for a GitHub release.

Usage: python scripts/release_notes.py <tag> [output]

Falls back to the whole changelog when the tag has no dedicated section, so a
release never fails just because the notes are missing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def extract(changelog: str, tag: str) -> str:
    """Return the ``## <tag> ...`` section, or the whole file as a fallback."""
    for section in re.split(r"(?m)^## ", changelog)[1:]:
        heading = section.split(maxsplit=1)[0].strip()
        if heading == tag:
            return "## " + section.strip() + "\n"
    return changelog.strip() + "\n"


def main(argv: list[str]) -> int:
    tag = argv[1] if len(argv) > 1 else ""
    output = Path(argv[2] if len(argv) > 2 else "release-notes.md")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    notes = extract(changelog, tag)
    output.write_text(notes, encoding="utf-8")
    print("release notes for {0!r}: {1} chars -> {2}".format(tag, len(notes), output))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
