#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "PUBLIC_INPUT_MANIFEST.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    failures: list[str] = []

    for section_name in ("osf", "go_learning_eras"):
        for entry in manifest[section_name]["files"]:
            path = ROOT / entry["local_path"]
            if not path.exists():
                failures.append(f"Missing file: {entry['local_path']}")
                continue
            actual = sha256(path)
            if actual != entry["sha256"]:
                failures.append(
                    f"Hash mismatch for {entry['local_path']}: expected {entry['sha256']}, got {actual}"
                )

    if failures:
        raise SystemExit("\n".join(failures))

    print("All public-input hashes match the pinned manifest.")


if __name__ == "__main__":
    main()
