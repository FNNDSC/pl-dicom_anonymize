import json
import pydicom
from argparse import Namespace

from dicom_anonymize import main


def test_custom_dictionary(
        dicom_tree):

    input_dir, output_dir = dicom_tree

    options = Namespace(
        dictionary=json.dumps({
            "(16,16)": "replace",
            "(16,32)": "replace"
        }),
        pattern="**/*",
        deletePrivateTags=False,
    )

    main(
        options,
        input_dir,
        output_dir
    )

    ds = pydicom.dcmread(
        output_dir /
        "patientA" /
        "image.dcm"
    )

    assert ds.PatientName != "John^Doe"