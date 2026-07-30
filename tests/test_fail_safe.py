import pytest
import json
import pydicom
from dicom_anonymize import main
from pathlib import Path

from safety import (
    MalformedDicomError,
    is_dicom_file,
    read_dataset_for_verification,
    relpath_hash,
    sanitize_exception,
    verify_deidentified,
)


def test_invalid_dicom_fails(
        tmp_path,
        default_options):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"

    input_dir.mkdir()
    output_dir.mkdir()

    bad_file = input_dir / "bad.dcm"

    bad_file.write_text(
        "this is not a dicom file"
    )

    main(
        default_options,
        input_dir,
        output_dir
    )

    # no identified data should leak
    assert len(list(output_dir.iterdir())) == 1

def test_malformed_input_fails_safely_and_is_never_emitted(dicom_tree, outdir, default_options):
    with pytest.raises(SystemExit) as exc:
        main(default_options, dicom_tree, outdir)
    assert exc.value.code == 1
    summary = json.loads((outdir / "deidentification_summary.json").read_text())
    assert summary["overall_status"] == "failed"
    failed = [f for f in summary["files"] if f["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["path"] == "patientA/series1/broken.dcm"
    assert not (outdir / "patientA/series1/broken.dcm").exists()

def test_is_dicom_file_detects_by_magic_bytes_not_extension(tmp_path):
    real = tmp_path / "IM0001"  # no extension at all, like real scanner output
    real.write_bytes(b"\0" * 128 + b"DICM" + b"restofthefile")
    assert is_dicom_file(real) is True

    fake = tmp_path / "notes.dcm"  # .dcm extension but not actually DICOM
    fake.write_bytes(b"not really dicom")
    assert is_dicom_file(fake) is False


def test_malformed_dicom_with_valid_magic_bytes_is_rejected(tmp_path):
    broken = tmp_path / "broken.dcm"
    broken.write_bytes(b"\0" * 128 + b"DICM" + b"garbagegarbagegarbage")
    assert is_dicom_file(broken) is True  # magic bytes are present
    with pytest.raises(MalformedDicomError):
        read_dataset_for_verification(broken)  # but it's not conformant DICOM


def test_sanitize_exception_never_includes_original_message():
    exc = ValueError("Patient name 'Doe^Jane' could not be converted")
    cls, summary = sanitize_exception(exc)
    assert cls == "ValueError"
    assert "Doe^Jane" not in summary
    assert "Doe" not in summary


def test_relpath_hash_is_stable_and_does_not_contain_path_text():
    p = Path("patientA/series1/img1.dcm")
    h1 = relpath_hash(p)
    h2 = relpath_hash(p)
    assert h1 == h2
    assert "patientA" not in h1
    assert len(h1) == 12


def test_relpath_hash_differs_for_different_paths():
    a = relpath_hash(Path("a/1.dcm"))
    b = relpath_hash(Path("b/1.dcm"))
    assert a != b


def test_verify_deidentified_rejects_unchanged_patient_name(tmp_path, dicom_tree):
    original = pydicom.dcmread(str(dicom_tree / "patientA/series1/img1.dcm"))
    # Simulate a "de-identification" that failed to touch PatientName.
    output_path = tmp_path / "output_unchanged.dcm"
    original.save_as(str(output_path), write_like_original=False)
    ok, reason = verify_deidentified(original, output_path)
    assert ok is False
    assert "PatientName" in reason


def test_verify_deidentified_accepts_when_identifiers_are_removed(tmp_path, dicom_tree):
    original = pydicom.dcmread(str(dicom_tree / "patientA/series1/img1.dcm"))
    modified = pydicom.dcmread(str(dicom_tree / "patientA/series1/img1.dcm"))
    del modified.PatientName
    del modified.PatientID
    del modified.PatientBirthDate
    del modified.InstitutionName
    del modified.ReferringPhysicianName
    del modified.AccessionNumber
    modified.StudyInstanceUID = pydicom.uid.generate_uid()
    modified.SeriesInstanceUID = pydicom.uid.generate_uid()
    modified.SOPInstanceUID = pydicom.uid.generate_uid()
    output_path = tmp_path / "output_changed.dcm"
    modified.save_as(str(output_path), write_like_original=False)
    ok, reason = verify_deidentified(original, output_path)
    assert ok is True
    assert reason is None


def test_verify_deidentified_honors_acknowledged_retained_tags(tmp_path, dicom_tree):
    original = pydicom.dcmread(str(dicom_tree / "patientA/series1/img1.dcm"))
    modified = pydicom.dcmread(str(dicom_tree / "patientA/series1/img1.dcm"))
    del modified.PatientName
    del modified.PatientID
    del modified.PatientBirthDate
    del modified.ReferringPhysicianName
    del modified.AccessionNumber
    modified.StudyInstanceUID = pydicom.uid.generate_uid()
    modified.SeriesInstanceUID = pydicom.uid.generate_uid()
    modified.SOPInstanceUID = pydicom.uid.generate_uid()
    # InstitutionName intentionally left unchanged.
    output_path = tmp_path / "output_partial.dcm"
    modified.save_as(str(output_path), write_like_original=False)

    ok, reason = verify_deidentified(original, output_path)
    assert ok is False  # not acknowledged -> must fail

    ok2, reason2 = verify_deidentified(
        original, output_path, acknowledged_retained_tags=frozenset({"InstitutionName"})
    )
    assert ok2 is True
    assert reason2 is None