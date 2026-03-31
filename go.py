"""One-command: export deck then generate pick list."""
import subprocess
import sys

print("=== Exporting current deck ===")
subprocess.run([sys.executable, "anki_hsk.py", "export"], check=True)

print("\n=== Generating pick list ===")
subprocess.run([sys.executable, "generate_new_words.py"], check=True)

print("\nDone. Edit pick_words.txt, then run:  python anki_hsk.py pick")
