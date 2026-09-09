#!/usr/bin/env python3
"""Verify Bonfire documentation.

Checks:
  1. Every relative Markdown link in docs/**/*.md and README.md points to an existing file.
  2. Every tests/features/*.feature file starts with a Feature line, and every
     Scenario has exactly one level tag (@unit, @contract, @e2e) and uses Given, When and Then.

Exit 0 and print OK when clean; otherwise print one problem per line and exit 1.
Set BONFIRE_DOCS_ROOT to check a different tree (used by the script's own test).
"""
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(os.environ.get("BONFIRE_DOCS_ROOT", pathlib.Path(__file__).resolve().parent.parent))
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
LEVELS = {"@unit", "@contract", "@e2e"}
STEP_WORDS = ("Given", "When", "Then")


def check_links() -> list[str]:
    problems = []
    files = sorted((ROOT / "docs").rglob("*.md")) if (ROOT / "docs").exists() else []
    if (ROOT / "README.md").exists():
        files.append(ROOT / "README.md")
    for md in files:
        text = md.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = target.split("#", 1)[0]
            if not (md.parent / path).exists():
                problems.append(f"{md.relative_to(ROOT)}: broken link {target}")
    return problems


def check_features() -> list[str]:
    problems = []
    feature_dir = ROOT / "tests" / "features"
    if not feature_dir.exists():
        return problems
    for feature in sorted(feature_dir.glob("*.feature")):
        rel = feature.relative_to(ROOT)
        lines = feature.read_text(encoding="utf-8").splitlines()
        if not any(line.strip().startswith("Feature:") for line in lines[:5]):
            problems.append(f"{rel}: no 'Feature:' line within the first 5 lines")
        pending_tags: set[str] = set()
        scenario = None
        seen: set[str] = set()

        def close() -> None:
            if scenario is not None:
                missing = [w for w in STEP_WORDS if w not in seen]
                if missing:
                    problems.append(f"{rel}: '{scenario}' lacks {', '.join(missing)}")

        for line in lines:
            s = line.strip()
            if s.startswith("@"):
                pending_tags |= set(s.split())
            elif s.startswith(("Scenario:", "Scenario Outline:")):
                close()
                scenario = s
                seen = set()
                levels = pending_tags & LEVELS
                if len(levels) != 1:
                    problems.append(f"{rel}: '{scenario}' must have exactly one of @unit, @contract, @e2e")
                pending_tags = set()
            elif scenario is not None:
                word = s.split(" ", 1)[0]
                if word in STEP_WORDS:
                    seen.add(word)
        close()
    return problems


def main() -> int:
    problems = check_links() + check_features()
    if problems:
        print("\n".join(problems))
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
