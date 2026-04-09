#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from osfclient.api import OSF


ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "osf"
PROJECT_ID = "xpf3q"

REMOTE_TO_LOCAL = {
    "/Analyses in the Main Text/shin et al 2023 data v001.RData": TARGET_DIR / "shin et al 2023 data v001.RData",
    "/Analyses in the Main Text/shin et al 2023 simulated ai move data v001.RData": TARGET_DIR / "shin et al 2023 simulated ai move data v001.RData",
    "/Analyses in the Main Text/shin et al 2023 analyses in the main text v01.R": TARGET_DIR / "shin et al 2023 analyses in the main text v01.R",
    "/Analyses in the Main Text/fig 1 panel a v01.png": TARGET_DIR / "fig 1 panel a v01.png",
    "/Analyses in the Main Text/fig 1 panel b v01.png": TARGET_DIR / "fig 1 panel b v01.png",
    "/Analyses in the Main Text/fig 1 panel c v01.png": TARGET_DIR / "fig 1 panel c v01.png",
    "/Analyses in the Main Text/fig 1 panel d v01.png": TARGET_DIR / "fig 1 panel d v01.png",
    "/Analyses in the Main Text/fig 2 v01.png": TARGET_DIR / "fig 2 v01.png",
    "/Analyses in the Main Text/fig 3 v01.png": TARGET_DIR / "fig 3 v01.png",
}


def main() -> None:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    project = OSF().project(PROJECT_ID)
    files = {file_.path: file_ for file_ in project.storage("osfstorage").files}
    missing = [path for path in REMOTE_TO_LOCAL if path not in files]
    if missing:
        joined = "\n".join(missing)
        raise SystemExit(f"Missing expected OSF files:\n{joined}")

    for remote_path, local_path in REMOTE_TO_LOCAL.items():
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with local_path.open("wb") as handle:
            files[remote_path].write_to(handle)
        print(f"Fetched {remote_path} -> {local_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
