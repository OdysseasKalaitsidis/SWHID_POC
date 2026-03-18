"""
main.py is retired. Use analyze.py instead:

    python analyze.py pkg:pypi/six@1.17.0
    python analyze.py pkg:cargo/serde@1.0.203
"""
import subprocess, sys
print("Note: main.py is retired. Forwarding to analyze.py...")
sys.exit(subprocess.call(["python", "analyze.py"] + sys.argv[1:]))
