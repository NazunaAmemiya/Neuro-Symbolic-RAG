"""Compare the live Hugging Face Office inventory with local source and ingest paths."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from huggingface_hub import HfApi

from backend.app.core.settings import get_settings
from backend.app.ingestion.source_catalog import SUPPORTED_SOURCE_SUFFIXES, document_code


def summarize_coverage(
    remote_paths: list[str], local_paths: set[str], prepared_paths: set[str]
) -> dict:
    office = sorted(
        path
        for path in remote_paths
        if path.startswith("Bidding_Law/")
        and PurePosixPath(path).suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES
        and not PurePosixPath(path).name.startswith("~$")
    )
    packages: dict[str, dict[str, object]] = defaultdict(lambda: {"primary": [], "attachments": []})
    for path in office:
        parts = PurePosixPath(path).parts
        package_name = parts[1] if len(parts) >= 3 else PurePosixPath(path).stem
        package_code = document_code(package_name)
        filename_code = document_code(PurePosixPath(path).stem)
        if package_code is None:
            raise ValueError(f"Hugging Face source has no package code: {path}")
        primary = len(parts) == 2 or filename_code == package_code
        bucket = packages[package_code]["primary" if primary else "attachments"]
        assert isinstance(bucket, list)
        bucket.append(path)
    remote_set = set(office)
    missing_local = sorted(remote_set - local_paths)
    missing_prepared = sorted(remote_set - prepared_paths)
    bad_packages = {
        code: group["primary"] for code, group in packages.items() if len(group["primary"]) != 1
    }
    return {
        "remote_office_files": len(office),
        "primary_files": sum(len(group["primary"]) for group in packages.values()),
        "attachment_files": sum(len(group["attachments"]) for group in packages.values()),
        "package_count": len(packages),
        "folder_package_count": len(
            {PurePosixPath(path).parts[1] for path in office if len(PurePosixPath(path).parts) > 2}
        ),
        "formats": dict(Counter(PurePosixPath(path).suffix.casefold() for path in office)),
        "local_source_paths_present": len(remote_set & local_paths),
        "prepared_paths_present": len(remote_set & prepared_paths),
        "missing_local_sources": missing_local,
        "missing_prepared_sources": missing_prepared,
        "extra_local_sources": sorted(local_paths - remote_set),
        "manifest_sources_not_in_remote": sorted(prepared_paths - remote_set),
        "packages_without_one_primary": bad_packages,
        "local_source_path_coverage_complete": not missing_local and not bad_packages,
        "prepared_path_coverage_complete": not missing_prepared and not bad_packages,
        "scope": "Path inventory only; source bytes and semantic content require separate checks.",
    }


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=Path(settings.source_docs_dir))
    parser.add_argument("--artifact-dir", type=Path, default=Path(settings.ingest_artifacts_dir))
    parser.add_argument("--output", type=Path, default=Path("data/derived/hf_coverage.json"))
    parser.add_argument("--revision", help="Pin a Hugging Face dataset commit SHA.")
    args = parser.parse_args()
    if not settings.hf_repo_id:
        parser.error("Set HF_REPO_ID (or REPO_ID) in .env")
    api = HfApi(token=settings.hf_token)
    revision = args.revision or api.repo_info(settings.hf_repo_id, repo_type="dataset").sha
    remote_paths = api.list_repo_files(settings.hf_repo_id, repo_type="dataset", revision=revision)
    local_paths = {
        path.relative_to(args.source_dir).as_posix()
        for path in args.source_dir.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES
        and not path.name.startswith("~$")
        and ".cache" not in path.relative_to(args.source_dir).parts
    }
    manifest_path = args.artifact_dir / "manifest.json"
    prepared_paths = (
        {
            row["source_file"].replace("\\", "/")
            for row in json.loads(manifest_path.read_text(encoding="utf-8"))
        }
        if manifest_path.is_file()
        else set()
    )
    result = summarize_coverage(remote_paths, local_paths, prepared_paths)
    result.update({"repo": settings.hf_repo_id, "revision": revision})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "revision": revision,
                "remote_office_files": result["remote_office_files"],
                "primary_files": result["primary_files"],
                "attachment_files": result["attachment_files"],
                "local_source_paths_present": result["local_source_paths_present"],
                "prepared_paths_present": result["prepared_paths_present"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    if (
        not result["local_source_path_coverage_complete"]
        or not result["prepared_path_coverage_complete"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
