"""Explicit source-bound formula transcriptions reviewed against original media."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FormulaReview:
    source_sha256: str
    content_sha256: str
    latex: str
    reviewer: str


class FormulaReviewIndex:
    def __init__(self, reviews: list[FormulaReview]) -> None:
        self._reviews: dict[tuple[str, str], FormulaReview] = {}
        for review in reviews:
            key = (review.source_sha256, review.content_sha256)
            if key in self._reviews:
                raise ValueError(f"Duplicate formula review for {key}")
            self._reviews[key] = review

    def get(self, source_sha256: str, content_sha256: str) -> FormulaReview | None:
        return self._reviews.get((source_sha256, content_sha256))


def load_formula_reviews(path: Path) -> FormulaReviewIndex:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("reviews"), list):
        raise TypeError("Formula review file must contain a reviews array")
    reviews = []
    for item in payload["reviews"]:
        if not isinstance(item, dict) or item.get("status") != "reviewed_visual":
            raise ValueError("Every formula review must have status reviewed_visual")
        source_hash = item.get("source_sha256")
        content_hash = item.get("content_sha256")
        latex = item.get("latex")
        reviewer = item.get("reviewer")
        if not all(isinstance(value, str) and value.strip() for value in (latex, reviewer)):
            raise ValueError("A reviewed formula needs nonempty latex and reviewer")
        if not all(
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
            for value in (source_hash, content_hash)
        ):
            raise ValueError("Formula review hashes must be lowercase SHA-256 digests")
        reviews.append(FormulaReview(source_hash, content_hash, latex.strip(), reviewer.strip()))
    return FormulaReviewIndex(reviews)
