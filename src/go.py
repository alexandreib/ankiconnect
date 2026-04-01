"""One-command: export deck then generate pick list."""
import os
import subprocess
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))

print("=== Exporting current deck ===")
subprocess.run([sys.executable, os.path.join(_DIR, "anki_hsk.py"), "export"], check=True)

print("\n=== Generating pick list ===")
subprocess.run([sys.executable, os.path.join(_DIR, "generate_new_words.py")], check=True)

print("\nDone. Edit pick_words.txt, then run:  python main.py pick")
