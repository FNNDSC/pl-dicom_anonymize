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

def test_inline_dictionary_overrides_dictionary_file(
        dicom_tree, outdir, tmp_path):

    input_dir = dicom_tree
    output_dir = outdir

    dictionary_file = tmp_path / "dictionary.json"
    dictionary_file.write_text(json.dumps({
        "(16, 16)": {
            "action": "replace_with_value",
            "value": "FILE"
        },
        "(16, 32)": {
            "action": "replace_with_value",
            "value": "FILE_ID"
        },
    }))

    options = Namespace(
        dictionary=json.dumps({
            "(16, 16)": {
                "action": "replace_with_value",
                "value": "INLINE"
            }
        }),
        pattern="patientA/series1/img1.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        continueOnError=False,
        acknowledgeRetainedTags="",
        dictionaryFile=str(dictionary_file),
    )

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

    # Inline dictionary overrides the file dictionary.
    assert ds.PatientName == "INLINE"

    # File-only rule is still retained.
    assert ds.PatientID == "FILE_ID"