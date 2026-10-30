# PyInstaller spec for the Windows desktop build (onedir, windowed).
#
#   pip install ".[windows]"
#   pyinstaller packaging/windows/nfl-playoff-rankings-mc-sim.spec
#
# Output: dist/nfl-playoff-rankings-mc-sim/nfl-playoff-rankings-mc-sim.exe (+ _internal/). Run from the
# repo root. See doc/technical.md, "Windows desktop build".

import os

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

# OR-Tools ships native DLLs and protobuf modules PyInstaller can't see statically.
ortools_datas, ortools_binaries, ortools_hiddenimports = collect_all("ortools")

a = Analysis(
    [os.path.join(SPECPATH, "nfl_playoff_rankings_mc_sim.py")],
    pathex=[ROOT],
    binaries=ortools_binaries,
    datas=[
        (os.path.join(ROOT, "frontend"), "frontend"),
        # Window icon of the tkinter control window (src/desktop.py).
        (os.path.join(SPECPATH, "icon.ico"), "."),
        # server.py reads the app version from the installed package metadata.
        *copy_metadata("nfl-playoff-rankings-mc-sim"),
        *ortools_datas,
    ],
    hiddenimports=ortools_hiddenimports,
    excludes=["pytest", "hypothesis"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nfl-playoff-rankings-mc-sim",
    icon=os.path.join(SPECPATH, "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="nfl-playoff-rankings-mc-sim",
    upx=False,
)
