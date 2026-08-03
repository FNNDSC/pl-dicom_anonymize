import pydicom
import pytest
import json
from argparse import Namespace
from dicom_anonymize import main
from conftest import make_dicom_with_nested_sequence, default_options


def test_patient_information_removed(
        dicom_tree,
        outdir,
        default_options):
    input_dir = dicom_tree
    output_dir = outdir
    options = Namespace(
        dictionary=json.dumps({
            "(16,16)": "replace",
            "(16,32)": "replace"
        }),
        pattern="**/*.dcm",
        keepPrivateTags=True,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags="",
        dictionaryFile=""

    )
    with pytest.raises(SystemExit):
        main(
            options,
            input_dir,
            output_dir
        )

    ds = pydicom.dcmread(
        output_dir /
        "patientA" /
        "series1" /
        "img1.dcm"
    )

    assert ds.PatientName != "John^Doe"
    assert ds.PatientID != "12345"

    # Kitware default behavior anonymizes this
    assert ds.PatientBirthDate == '00010101'

def test_phi_nested_in_standard_sequence_is_scrubbed(tmp_path, default_options):
    """Positive control: a profile-listed sequence (Referenced Image
    Sequence) gets its nested PHI removed just like top-level PHI."""
    indir = tmp_path / "in"
    outdir = tmp_path / "out"
    outdir.mkdir()
    make_dicom_with_nested_sequence(indir / "study/img.dcm", private_sequence=False)

    main(default_options, indir, outdir,)

    out = pydicom.dcmread(str(outdir / "study/img.dcm"))
    nested = out[(0x0008, 0x1140)].value[0]
    assert str(getattr(nested, "PatientName", "")) == ""
    assert str(getattr(nested, "PatientID", "")) == ""

def test_phi_nested_in_private_sequence_is_removed_by_default(tmp_path, default_options):
    """Default behavior (private tags deleted): the whole private group,
    nested sequence and all, is stripped -- no PHI survives."""
    indir = tmp_path / "in"
    outdir = tmp_path / "out"
    outdir.mkdir()
    make_dicom_with_nested_sequence(indir / "study/img.dcm", private_sequence=True)

    main(default_options, indir, outdir)

    out = pydicom.dcmread(str(outdir / "study/img.dcm"))
    assert 0x00411010 not in out
    assert 0x00410010 not in out
    raw = str(out)
    assert "Doe" not in raw
    assert "leaked-secret-note" not in raw