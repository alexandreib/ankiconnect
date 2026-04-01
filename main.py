#!/usr/bin/env python3
"""Main entry point for Anki HSK vocabulary tools.

Usage:
  python main.py export [--format json|csv]
  python main.py import [--format json|csv]
  python main.py pick
  python main.py models
  python main.py cleanup [--mode ...] [--scope ...]
  python main.py generate
  python main.py go
  python main.py clean-empty
"""
import os
import subprocess
import sys

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")

COMMANDS = {
    "export":      ("anki_hsk.py",),
    "import":      ("anki_hsk.py",),
    "pick":        ("anki_hsk.py",),
    "models":      ("anki_hsk.py",),
    "cleanup":     ("cleanup_tags.py",),
    "generate":    ("generate_new_words.py",),
    "go":          ("go.py",),
    "clean-empty": ("clean_empty.py",),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("Commands:", ", ".join(COMMANDS))
        return

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print("Available:", ", ".join(COMMANDS))
        sys.exit(1)

    script = os.path.join(SRC_DIR, COMMANDS[cmd][0])
    extra = sys.argv[2:]

    # For anki_hsk.py commands, pass the subcommand name as first arg
    if COMMANDS[cmd][0] == "anki_hsk.py":
        extra = [cmd] + extra

    subprocess.run([sys.executable, script] + extra, check=True)


if __name__ == "__main__":
    main()
