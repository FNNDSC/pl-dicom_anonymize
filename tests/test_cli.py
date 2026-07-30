import json

import pydicom
import pytest
from argparse import Namespace
from dicom_anonymize import main, parser

def test_recursion_and_relative_path_preservation(dicom_tree, outdir, default_options):
    with pytest.raises(SystemExit) as exc:
        main(default_options, dicom_tree, outdir)
    assert exc.value.code == 1  # the corrupt file still fails the whole run

    # every valid DICOM file, at every depth, was found and mirrored at the
    # identical relative path
    assert (outdir / "patientA/series1/img1.dcm").exists()
    assert (outdir / "patientA/series1/img2.dcm").exists()
    assert (outdir / "patientA/series2/img1.dcm").exists()
    # non-DICOM file was NOT copied through by default
    assert not (outdir / "notes/readme.txt").exists()
    # the malformed file was NOT delivered as output under any name
    assert not (outdir / "patientA/series1/broken.dcm").exists()
    assert not list(outdir.glob("**/*.part"))  # no leftover partial files


def test_no_filename_collisions_across_identically_named_files(dicom_tree, outdir, default_options):
    # img1.dcm exists in both series1 and series2 -- same filename, different
    # subdirectories. Both must be preserved distinctly rather than one
    # clobbering the other.
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir)
    s1 = pydicom.dcmread(str(outdir / "patientA/series1/img1.dcm"))
    s2 = pydicom.dcmread(str(outdir / "patientA/series2/img1.dcm"))
    assert s1.SOPInstanceUID != s2.SOPInstanceUID


def test_phi_removed_from_output(dicom_tree, outdir, default_options):
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir)
    out = pydicom.dcmread(str(outdir / "patientA/series1/img1.dcm"))
    assert getattr(out, "PatientName", "") in ("", None)
    assert getattr(out, "PatientID", "") in ("", None)


def test_uid_consistency_across_entire_dataset(dicom_tree, outdir, default_options):
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir)
    out1 = pydicom.dcmread(str(outdir / "patientA/series1/img1.dcm"))
    out2 = pydicom.dcmread(str(outdir / "patientA/series1/img2.dcm"))
    out3 = pydicom.dcmread(str(outdir / "patientA/series2/img1.dcm"))

    # same original StudyInstanceUID -> same new StudyInstanceUID everywhere
    assert out1.StudyInstanceUID == out2.StudyInstanceUID == out3.StudyInstanceUID
    # same original SeriesInstanceUID (series1) -> same new SeriesInstanceUID
    assert out1.SeriesInstanceUID == out2.SeriesInstanceUID
    # different original SeriesInstanceUID (series2) -> different new one
    assert out1.SeriesInstanceUID != out3.SeriesInstanceUID
    # distinct original SOPInstanceUIDs -> distinct new ones
    assert out1.SOPInstanceUID != out2.SOPInstanceUID


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


def test_summary_json_has_no_phi_values(dicom_tree, outdir, default_options):
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir)
    raw = (outdir / "deidentification_summary.json").read_text()
    assert "Doe" not in raw
    assert "Jane" not in raw
    assert "MRN001" not in raw
    assert "General Hospital" not in raw


def test_non_dicom_not_copied_by_default_but_copied_when_requested(dicom_tree, outdir, default_options):
    default_options = Namespace(
        dictionary="",
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags="",
        continueOnError=True,
    )
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir)
    assert not (outdir / "notes/readme.txt").exists()

    outdir2 = outdir.parent / "outdir2"
    outdir2.mkdir()
    default_options = Namespace(
        dictionary="",
        pattern="**/*",
        keepPrivateTags=False,
        copyNonDicom=True,
        skipOutputVerification=False,
        acknowledgeRetainedTags="",
        continueOnError=True,
    )
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir2)
    assert (outdir2 / "notes/readme.txt").exists()
    assert (outdir2 / "notes/readme.txt").read_text() == "not a dicom file"


def test_custom_tag_action_via_json(dicom_tree, outdir, default_options):
    default_options = Namespace(
        dictionary='{"(0x0008, 0x1030)": {"action": "replace_with_value", "value": "SCRUBBED"}}',
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags="",
        continueOnError=True,
    )
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir)
    out = pydicom.dcmread(str(outdir / "patientA/series1/img1.dcm"))
    assert getattr(out, "StudyDescription", None) == "SCRUBBED"


def test_intentional_retain_requires_explicit_acknowledgement(dicom_tree, outdir, tmp_path, default_options):
    dictionary_file = tmp_path / "dict.json"
    dictionary_file.write_text(json.dumps({"(0x0008, 0x0080)": "keep"}))  # InstitutionName
    default_options = Namespace(
        dictionary=json.dumps({"(0x0008, 0x0080)": "keep"}),
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags="",
        continueOnError=True,
    )

    # Without acknowledging, verification must reject files where the
    # custom dictionary intentionally retained an identifying tag.
    with pytest.raises(SystemExit) as exc:
        main(default_options, dicom_tree, outdir)
    assert exc.value.code == 1
    summary = json.loads((outdir / "deidentification_summary.json").read_text())
    reasons = [f.get("error_summary", "") for f in summary["files"] if f["status"] == "failed"]
    assert any("InstitutionName" in r for r in reasons)

    # With explicit acknowledgement, those same files succeed (only the
    # genuinely malformed file still fails).
    outdir2 = outdir.parent / "outdir_ack"
    outdir2.mkdir()
    default_options = Namespace(
        dictionary=json.dumps({"(0x0008, 0x0080)": "keep"}),
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags="InstitutionName",
        continueOnError=True,
    )
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir2)
    summary2 = json.loads((outdir2 / "deidentification_summary.json").read_text())
    failed2 = [f for f in summary2["files"] if f["status"] == "failed"]
    assert len(failed2) == 1
    assert failed2[0]["path"] == "patientA/series1/broken.dcm"


def test_keep_private_tags_flag(dicom_tree, outdir, tmp_path, default_options):
    # add a private tag to one input file
    default_options = Namespace(
        dictionary='',
        pattern="**/*.dcm",
        keepPrivateTags=True,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags="",
        continueOnError=True,
    )
    target = dicom_tree / "patientA/series1/img1.dcm"
    ds = pydicom.dcmread(str(target))
    ds.add_new(0x00410010, "LO", "PRIVATE CREATOR")
    ds.add_new(0x00411001, "LO", "some private value")
    ds.save_as(str(target), write_like_original=False)

    outdir_keep = outdir.parent / "outdir_keep"
    outdir_keep.mkdir()
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir_keep)
    kept = pydicom.dcmread(str(outdir_keep / "patientA/series1/img1.dcm"))
    assert 0x00411001 in kept

    outdir_strip = outdir.parent / "outdir_strip"
    outdir_strip.mkdir()
    default_options = Namespace(
        dictionary='',
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags="",
        continueOnError=True,
    )
    with pytest.raises(SystemExit):
        main(default_options, dicom_tree, outdir_strip)
    stripped = pydicom.dcmread(str(outdir_strip / "patientA/series1/img1.dcm"))
    assert 0x00411001 not in stripped

def test_help_output_documents_every_option(capsys):
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for flag in (
        "--keepPrivateTags",
        "--dictionaryFile",
        "--dictionary",
        "--copyNonDicom",
        "--continueOnError",
        "--skipOutputVerification",
        "--acknowledgeRetainedTags",
        "--upstreamVersion",
        "--pattern",
    ):
        assert flag in out