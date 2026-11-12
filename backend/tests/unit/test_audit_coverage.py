from scripts.audit_hf_coverage import summarize_coverage
from scripts.audit_markdown_fidelity import _source_coverage


def test_markdown_audit_requires_every_office_attachment_in_manifest(tmp_path) -> None:
    package = tmp_path / "Bidding_Law" / "01_2024_TT-BKHDT"
    package.mkdir(parents=True)
    (package / "01_2024_TT-BKHDT.docx").write_bytes(b"primary")
    (package / "Mau so 4A.doc").write_bytes(b"form")
    (package / "Bang tinh.xlsx").write_bytes(b"workbook")
    (package / "ignored.md").write_text("derived", encoding="utf-8")
    manifest = [{"source_file": "Bidding_Law/01_2024_TT-BKHDT/01_2024_TT-BKHDT.docx"}]

    incomplete = _source_coverage(tmp_path, manifest)
    assert incomplete["complete"] is False
    assert incomplete["discovered_office_files"] == 3
    assert len(incomplete["unprepared_sources"]) == 2

    manifest.extend({"source_file": path} for path in incomplete["unprepared_sources"])
    assert _source_coverage(tmp_path, manifest)["complete"] is True


def test_hf_inventory_counts_folder_attachments_and_missing_sources() -> None:
    remote = [
        "Bidding_Law/24_2024_ND-CP.docx",
        "Bidding_Law/01_2024_TT-BKHDT/01_2024_TT-BKHDT.docx",
        "Bidding_Law/01_2024_TT-BKHDT/Mau so 4A.doc",
        "Bidding_Law/01_2024_TT-BKHDT/Bang.xlsx",
        "Bidding_Law/01_2024_TT-BKHDT/~$Mau tam.docx",
        "README.md",
    ]
    local = set(remote[:2])
    result = summarize_coverage(remote, local, local)

    assert result["remote_office_files"] == 4
    assert result["primary_files"] == 2
    assert result["attachment_files"] == 2
    assert result["folder_package_count"] == 1
    assert result["local_source_path_coverage_complete"] is False
    assert result["missing_local_sources"] == sorted(remote[2:4])
