"""A script that prints progress slowly — simulates a long-running task."""

import time
import sys

for i in range(1, 11):
    print(f"Processing step {i}/10 ...", flush=True)
    time.sleep(1)

print("DONE — all 10 steps completed", flush=True)
