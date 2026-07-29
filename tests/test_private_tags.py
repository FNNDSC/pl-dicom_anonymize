import pydicom
import pytest
import json
from argparse import Namespace
from dicom_anonymize import main
from conftest import make_dicom_with_nested_sequence


def test_private_tags_removed(
        dicom_tree,
        outdir,
        default_options):
    input_dir = dicom_tree
    output_dir = outdir
    with pytest.raises(SystemExit):
        main(
            default_options,
            input_dir,
            output_dir
        )

    ds = pydicom.dcmread(
        output_dir /
        "patientA" /
        "series1" /
        "img2.dcm"
    )

    assert not any(
        elem.tag.is_private
        for elem in ds
    )

def test_phi_nested_in_private_sequence_survives_with_keepPrivateTags_but_is_caught(tmp_path, default_options):
    """
    Documents a real upstream gap (verified by direct experimentation
    against dicomanonymizer.simpledicomanonymizer.anonymize_dataset):
    with --keepPrivateTags, PHI nested inside a private Sequence is left
    completely untouched by dicom-anonymizer itself. This plugin's
    independent post-write verification must detect the leaked
    PatientName and refuse to deliver the file, rather than silently
    shipping an identified private sequence as "de-identified" output.
    """
    indir = tmp_path / "in"
    outdir = tmp_path / "out"
    outdir.mkdir()
    make_dicom_with_nested_sequence(indir / "study/img.dcm", private_sequence=True)
    options = Namespace(
        dictionary=json.dumps({
            "(16,16)": "replace",
            "(16,32)": "replace"
        }),
        pattern="**/*.dcm",
        keepPrivateTags=True,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags=""

    )

    with pytest.raises(SystemExit) as exc:
        main(options, indir, outdir)

    assert exc.value.code == 1  # run correctly reports failure
    assert not (outdir / "study/img.dcm").exists()  # never delivered