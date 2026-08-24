import json
from argparse import Namespace

import pytest

from dicom_anonymize import main


def _make_broken_dcm(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same "has the DICM magic bytes but no valid File Meta Information"
    # shape as tests/conftest.py's broken.dcm fixture file.
    path.write_bytes(b"\0" * 128 + b"DICM" + b"garbagegarbagegarbage")


def _options(continue_on_error: bool) -> Namespace:
    return Namespace(
        dictionary="{}",
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        continueOnError=continue_on_error,
        acknowledgeRetainedTags="",
        dictionaryFile="",
    )


@pytest.fixture
def all_broken_tree(tmp_path):
    """Three malformed DICOM files. Since every file fails regardless of
    which one is visited first, this makes stop-vs-continue behavior
    deterministic without depending on filesystem directory-iteration
    order (which PathMapper does not guarantee is sorted)."""
    root = tmp_path / "in"
    _make_broken_dcm(root / "a/broken1.dcm")
    _make_broken_dcm(root / "b/broken2.dcm")
    _make_broken_dcm(root / "c/broken3.dcm")
    return root


def test_default_stops_after_first_failure(all_broken_tree, tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()

    with pytest.raises(SystemExit) as exc:
        main(_options(continue_on_error=False), all_broken_tree, outdir)
    assert exc.value.code == 1

    summary = json.loads((outdir / "deidentification_summary.json").read_text())
    # Every file in the tree fails, so regardless of iteration order the
    # very first file visited must trigger an immediate stop.
    assert summary["total_files_seen"] == 1
    assert summary["counts"]["failed"] == 1
    assert summary["stopped_early"] is True
    assert summary["continue_on_error"] is False
    assert len(summary["files"]) == 1


def test_continue_on_error_processes_the_whole_tree(all_broken_tree, tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()

    with pytest.raises(SystemExit) as exc:
        main(_options(continue_on_error=True), all_broken_tree, outdir)
    assert exc.value.code == 1  # still an overall failure

    summary = json.loads((outdir / "deidentification_summary.json").read_text())
    assert summary["total_files_seen"] == 3
    assert summary["counts"]["failed"] == 3
    assert summary["stopped_early"] is False
    assert summary["continue_on_error"] is True
    assert len(summary["files"]) == 3


def test_default_stops_even_with_valid_files_present(dicom_tree, tmp_path):
    """Sanity check against the richer dicom_tree fixture (which mixes
    valid, non-DICOM, and one broken file): with the default
    continueOnError=False, the run must still stop the moment it hits
    the broken file, so strictly fewer files are ever examined than
    exist under inputdir."""
    outdir = tmp_path / "out"
    outdir.mkdir()

    total_under_inputdir = sum(1 for _ in dicom_tree.rglob("*.dcm") if _.is_file())

    with pytest.raises(SystemExit) as exc:
        main(_options(continue_on_error=False), dicom_tree, outdir)
    assert exc.value.code == 1

    summary = json.loads((outdir / "deidentification_summary.json").read_text())
    assert summary["stopped_early"] is True
    assert summary["total_files_seen"] < total_under_inputdir
    # Whatever was seen, the run must have stopped exactly at the failure.
    assert summary["files"][-1]["status"] == "failed"
