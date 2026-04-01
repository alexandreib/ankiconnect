"""Export deck, translate empty cards, update tags, push back to Anki."""
import os
import subprocess
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))

print("=== Exporting current deck ===")
subprocess.run([sys.executable, os.path.join(_DIR, "anki_hsk.py"), "export"], check=True)

print("\n=== Translating empty cards ===")
subprocess.run([sys.executable, os.path.join(_DIR, "cleanup_tags.py"), "--mode", "retranslate", "--scope", "empty"], check=True)

print("\n=== Updating tags (all cards) ===")
subprocess.run([sys.executable, os.path.join(_DIR, "cleanup_tags.py"), "--mode", "tags"], check=True)

print("\n=== Importing back to Anki ===")
subprocess.run([sys.executable, os.path.join(_DIR, "anki_hsk.py"), "import"], check=True)

print("\nDone. Empty cards have been translated and all tags updated.")
