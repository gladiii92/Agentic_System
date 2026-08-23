"""
Kurzer Zusatz-Check -- wo liegt ai-review.exe WIRKLICH? (Chat-Verlauf
2026-08-23, Fortsetzung des cwd-Bugs)
"""
import subprocess
result = subprocess.run(["where", "ai-review"], capture_output=True, text=True, shell=True)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
