"""PyInstaller entry script for the Windows desktop build (see nfl-playoff-sim.spec)."""

import multiprocessing
import os
import sys

# A windowed (no-console) build has no stdout/stderr; anything writing to them
# directly -- here or in a spawned simulation worker, which re-runs this
# script -- would crash.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

if __name__ == "__main__":
    # Must run before anything else: in a spawned worker it takes over and
    # runs the worker instead of starting a second app.
    multiprocessing.freeze_support()

    from src.desktop import main

    main()
