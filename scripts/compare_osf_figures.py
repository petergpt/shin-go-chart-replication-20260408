from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def compare_pair(generated_path: Path, reference_path: Path) -> dict:
    generated_md5 = md5(generated_path)
    reference_md5 = md5(reference_path)

    generated_img = Image.open(generated_path).convert("RGBA")
    reference_img = Image.open(reference_path).convert("RGBA")

    result = {
      "generated_md5": generated_md5,
      "reference_md5": reference_md5,
      "byte_identical": generated_md5 == reference_md5,
      "generated_size": list(generated_img.size),
      "reference_size": list(reference_img.size),
      "same_size": generated_img.size == reference_img.size,
    }

    if generated_img.size == reference_img.size:
        a = np.asarray(generated_img, dtype=np.int16)
        b = np.asarray(reference_img, dtype=np.int16)
        diff = np.abs(a - b)
        result.update(
            {
                "pixel_identical": bool(np.array_equal(a, b)),
                "mean_abs_diff": float(diff.mean()),
                "max_abs_diff": int(diff.max()),
                "changed_pixels": int(np.count_nonzero(np.any(a != b, axis=2))),
                "total_pixels": int(a.shape[0] * a.shape[1]),
            }
        )

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-dir", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    generated_dir = Path(args.generated_dir).resolve()
    output_json = Path(args.output_json).resolve()

    refs = {
        name: ROOT / "osf" / name
        for name in (
            "fig 1 panel a v01.png",
            "fig 1 panel b v01.png",
            "fig 1 panel c v01.png",
            "fig 1 panel d v01.png",
            "fig 2 v01.png",
            "fig 3 v01.png",
        )
    }

    summary = {}
    for name, ref_path in refs.items():
        generated_path = generated_dir / name
        summary[name] = compare_pair(generated_path, ref_path)

    output_json.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
