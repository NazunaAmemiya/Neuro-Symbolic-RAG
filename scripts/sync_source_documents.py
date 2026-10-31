"""Download the shared corpus to the ignored local development source directory."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from huggingface_hub import snapshot_download

from backend.app.core.settings import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.hf_repo_id:
        raise SystemExit("Set HF_REPO_ID (or legacy REPO_ID) in .env before syncing.")

    target_dir = Path(settings.source_docs_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=settings.hf_repo_id,
        repo_type="dataset",
        token=settings.hf_token,
        local_dir=target_dir,
        allow_patterns=["Bidding_Law/**"],
        ignore_patterns=["**/~$*", "**/.cache/**"],
    )
    print(f"Corpus synced to {target_dir}")


if __name__ == "__main__":
    main()
