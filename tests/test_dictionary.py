import json
import pydicom
from argparse import Namespace
import pytest
from dicom_anonymize import main


def test_custom_dictionary(
        dicom_tree, outdir):

    input_dir = dicom_tree
    output_dir = outdir

    options = Namespace(
        dictionary=json.dumps({
            "(16,16)": "replace",
            "(16,32)": "replace"
        }),
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        acknowledgeRetainedTags="",
        dictionaryFile=""

    )
    with pytest.raises(SystemExit) as exc:

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