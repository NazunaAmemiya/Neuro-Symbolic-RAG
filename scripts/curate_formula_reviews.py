"""Expand visually reviewed formula groups into source-bound local review records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REVIEWER = "Visual formula audit 2026-11-12"

IMAGE_REVIEWS = {
    "641389c892e25c2c276238221c5e17a54dac6b809aaeea14f631c7c9433e4747": (
        r"S_j = \sum_{i=1}^{k} t_{ji} \ast W_{ji}"
    ),
    "7e1f9e2041ec76fd72d0598cb43c3ba876894b0ad8395ea0b297fd990d30a18f": (
        r"T = \sum_{j=1}^{n} S_j \ast W_j"
    ),
}

OWNERSHIP_OMML_HASHES = {
    "da3f09f79cd8b1cbd1221142081d7ab9784bed7f07960643af344e79c6ce9dda",
    "109e70e13052dcf09a394065867dc9a8a889dd4d8abf08898297f99aab713070",
    "40ed67603c5f7710452e8e79b7eb919e6d40f30897197537540424172cef12fe",
    "3a1f793462de350bf5d85c0fe53a8d92046bfa36fca1bd21d072fa9918b0337b",
}
OWNERSHIP_LATEX = r"\text{Tỷ lệ sở hữu vốn} = \sum_{i=1}^{n} X_i \times Y_i"

PARAGRAPH_REVIEWS = (
    {
        "source_path": (
            "Bidding_Law/06_2024_TT-BKHDT/3. Mẫu số 3B E-HSMT Xây lắp 2 túi.doc"
        ),
        "source_sha256": (
            "3061c502cfd5cbc7cd9b4900fbb8ea148b672c47095608b07d0cac97b10fcb99"
        ),
        "content_sha256": (
            "6c6d9bd1ad16ccd3d3bda26b619046becc7ff047a996dfc9a56fda257808c8b8"
        ),
        "latex": (
            r"\text{Điểm tổng hợp}_{\text{đang xét}} = "
            r"\left(\frac{G_{\text{thấp nhất}}}{G_{\text{đang xét}}}\times T + "
            r"\frac{\text{Điểm kỹ thuật}_{\text{đang xét}}}"
            r"{\text{Điểm kỹ thuật}_{\text{cao nhất}}}\times K\right)\times 100"
        ),
    },
    {
        "source_path": (
            "Bidding_Law/06_2024_TT-BKHDT/6. Mẫu số 4B E-HSMT hàng hóa 2 túi.docx"
        ),
        "source_sha256": (
            "15f3279e54109a933c30ce65ae2e50975773f3b494be036088cd9589a84f6646"
        ),
        "content_sha256": (
            "33fa07dd4de5826b6dc7e39493a9b66fb29d68b12d560ede1262982a9713d935"
        ),
        "latex": (
            r"\text{Điểm tổng hợp}_{\text{đang xét}} = "
            r"\left(\left(\frac{G_{\text{thấp nhất}}}{G_{\text{đang xét}}}"
            r"\times T + \frac{\text{Điểm kỹ thuật}_{\text{đang xét}}}"
            r"{\text{Điểm kỹ thuật}_{\text{cao nhất}}}\times K\right)\times 100"
            r"\right) + \Delta_{\text{ƯĐ}}"
        ),
    },
    {
        "source_path": (
            "Bidding_Law/06_2024_TT-BKHDT/9. Mẫu số 5B E-HSMT Phi tư vấn 2 túi.doc"
        ),
        "source_sha256": (
            "319dfdc462bee0d8fe0692ce1c7f6447838116916de98ebf8e0c968122ebd742"
        ),
        "content_sha256": (
            "ad529e84156d0e90def8c0eae07f099689661f4fa24c0bf953840a9dc18f6fe8"
        ),
        "latex": (
            r"\text{Điểm tổng hợp}_{\text{đang xét}} = "
            r"\left(\frac{G_{\text{thấp nhất}}}{G_{\text{đang xét}}}\times T + "
            r"\frac{\text{Điểm kỹ thuật}_{\text{đang xét}}}"
            r"{\text{Điểm kỹ thuật}_{\text{cao nhất}}}\times K\right)\times 100 "
            r"+ \Delta_{\text{ƯĐ}}"
        ),
    },
)


def curate(artifact_root: Path, review_path: Path) -> int:
    payload = (
        json.loads(review_path.read_text(encoding="utf-8"))
        if review_path.is_file()
        else {"reviews": []}
    )
    reviews = payload["reviews"]
    keys = {(item["source_sha256"], item["content_sha256"]) for item in reviews}
    manifest = json.loads((artifact_root / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest:
        artifact_dir = artifact_root / item["artifact_dir"]
        report = json.loads((artifact_dir / "report.json").read_text(encoding="utf-8"))
        assets = {asset["asset_id"]: asset for asset in report["assets"]}
        blocks = [
            json.loads(line)
            for line in (artifact_dir / "blocks.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        for block in blocks:
            metadata = block.get("metadata", {})
            content_hash = None
            latex = None
            package_path = None
            if (
                block["kind"] == "formula"
                and metadata.get("source_type") == "image"
                and block["asset_ids"]
            ):
                asset = assets[block["asset_ids"][0]]
                asset_path = artifact_dir / "assets" / (
                    f"{asset['asset_id']}-{Path(asset['filename']).name}"
                )
                content_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
                latex = IMAGE_REVIEWS.get(content_hash)
                package_path = asset["package_path"]
            elif block["kind"] == "formula" and metadata.get("source_type") == "omml":
                content_hash = metadata["content_sha256"]
                if content_hash in OWNERSHIP_OMML_HASHES:
                    latex = OWNERSHIP_LATEX
            if not latex or content_hash is None:
                continue
            key = (item["source_hash"], content_hash)
            if key in keys:
                continue
            review = {
                "source_path": item["source_file"],
                "source_sha256": item["source_hash"],
                "content_sha256": content_hash,
                "status": "reviewed_visual",
                "latex": latex,
                "reviewer": REVIEWER,
                "note": "Exact content SHA-256 matches a visually reviewed corpus formula.",
            }
            if package_path:
                review["package_path"] = package_path
            reviews.append(review)
            keys.add(key)

    for item in PARAGRAPH_REVIEWS:
        key = (item["source_sha256"], item["content_sha256"])
        if key in keys:
            continue
        reviews.append(
            {
                **item,
                "status": "reviewed_visual",
                "reviewer": REVIEWER,
                "note": "Transcribed from the rendered source formula page.",
            }
        )
        keys.add(key)

    reviews.sort(key=lambda item: (item["source_path"], item["content_sha256"]))
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        json.dumps({"reviews": reviews}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(reviews)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, default=Path("data/artifacts"))
    parser.add_argument(
        "--reviews", type=Path, default=Path("data/derived/formula_reviews.json")
    )
    args = parser.parse_args()
    print(f"review_records={curate(args.artifact_dir, args.reviews)}")


if __name__ == "__main__":
    main()
