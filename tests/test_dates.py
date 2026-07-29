from dicom_anonymize import main
from conftest import make_dicom_with_nested_sequence
import pydicom
import pytest
import json
from argparse import Namespace

def test_dates_are_replaced_with_fixed_dummy_not_shifted(tmp_path, default_options):
    """
    dicom-anonymizer does NOT date-shift: DA/DT/TM elements are all
    replaced with the same fixed dummy value regardless of their
    original value, so relative time intervals between studies are NOT
    preserved. Two files with different original StudyDate values must
    both end up with the identical dummy date, not two different
    shifted-but-distinguishable dates.
    """
    indir = tmp_path / "in"
    outdir = tmp_path / "out"
    outdir.mkdir()
    make_dicom_with_nested_sequence(indir / "a/img.dcm", private_sequence=False, study_date="20180101")
    make_dicom_with_nested_sequence(indir / "b/img.dcm", private_sequence=False, study_date="20230630")
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

    main(options, indir, outdir)

    out_a = pydicom.dcmread(str(outdir / "a/img.dcm"))
    out_b = pydicom.dcmread(str(outdir / "b/img.dcm"))

    assert out_a.StudyDate == out_b.StudyDate == "00010101"
    assert out_a.StudyDate != "20180101"
    assert out_b.StudyDate != "20230630"