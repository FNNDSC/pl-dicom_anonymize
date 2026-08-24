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
        continueOnError=True,
        acknowledgeRetainedTags="",
        dictionaryFile=""

    )
    with pytest.raises(SystemExit) as exc:

        main(
        options,
        input_dir,
        output_dir
        )
    # dicom_tree includes one deliberately-corrupt file (broken.dcm), so
    # the overall run still exits 1 even though the custom dictionary
    # itself is applied fine to every valid file.
    assert exc.value.code == 1

    ds = pydicom.dcmread(
        output_dir /
        "patientA" /
        "series1" /
        "img1.dcm"
    )

    # The fixture sets PatientName/PatientID to "Doe^Jane" / "MRN001"
    # (tests/conftest.py); the custom "replace" rule for both tags
    # overrides the plugin's normal default de-identification, which
    # would otherwise blank these instead.
    assert ds.PatientName == "ANONYMIZED"
    assert ds.PatientID == "ANONYMIZED"

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


def test_inline_wins_even_against_a_differently_spelled_file_duplicate(
        dicom_tree, outdir, tmp_path):
    """Regression test: precedence must hold on the *parsed* DICOM tag,
    not on raw JSON-key string identity / insertion order. If the file
    dictionary spells the same tag two different ways and inline matches
    only the earlier spelling, inline must still win."""
    input_dir = dicom_tree
    output_dir = outdir

    dictionary_file = tmp_path / "dictionary.json"
    dictionary_file.write_text(json.dumps({
        "(16,16)": {"action": "replace_with_value", "value": "FILE_B"},
        "(16, 16)": {"action": "replace_with_value", "value": "FILE_A"},
    }))

    options = Namespace(
        dictionary=json.dumps({
            "(16,16)": {"action": "replace_with_value", "value": "INLINE"}
        }),
        pattern="patientA/series1/img1.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        continueOnError=False,
        acknowledgeRetainedTags="",
        dictionaryFile=str(dictionary_file),
    )

    main(options, input_dir, output_dir)

    ds = pydicom.dcmread(
        output_dir /
        "patientA" /
        "series1" /
        "img1.dcm"
    )
    assert ds.PatientName == "INLINE"


def test_dictionary_file_only(dicom_tree, outdir, tmp_path):
    """--dictionaryFile with no --dictionary at all -- the most common real
    usage, and previously the only path in the whole suite left untested.
    Also covers a plain string-form action (not a dict) loaded from a
    file, which the inline-vs-file precedence test above doesn't exercise.
    """
    input_dir = dicom_tree
    output_dir = outdir

    dictionary_file = tmp_path / "dictionary.json"
    dictionary_file.write_text(json.dumps({
        "(16, 16)": "replace",
        "(16, 32)": {
            "action": "replace_with_value",
            "value": "FILE_ONLY_ID",
        },
    }))

    options = Namespace(
        dictionary="{}",
        pattern="patientA/series1/img1.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        continueOnError=False,
        acknowledgeRetainedTags="",
        dictionaryFile=str(dictionary_file),
    )

    main(options, input_dir, output_dir)

    ds = pydicom.dcmread(
        output_dir /
        "patientA" /
        "series1" /
        "img1.dcm"
    )

    assert ds.PatientName == "ANONYMIZED"
    assert ds.PatientID == "FILE_ONLY_ID"


def test_missing_dictionary_file_exits_fatal(dicom_tree, outdir, tmp_path):
    """A --dictionaryFile that doesn't exist should abort the whole run
    with a fatal, non-per-file error before any processing starts."""
    options = Namespace(
        dictionary="{}",
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        continueOnError=False,
        acknowledgeRetainedTags="",
        dictionaryFile=str(tmp_path / "does_not_exist.json"),
    )
    with pytest.raises(SystemExit) as exc:
        main(options, dicom_tree, outdir)
    assert exc.value.code == 2
    # Nothing should have been processed.
    assert not list(outdir.glob("**/*.dcm"))


def test_malformed_dictionary_file_exits_fatal(dicom_tree, outdir, tmp_path):
    """A --dictionaryFile containing invalid JSON should abort the whole
    run with a fatal error, not fail per-file part way through."""
    dictionary_file = tmp_path / "bad.json"
    dictionary_file.write_text('{"(16,16)": "replace",}')  # trailing comma

    options = Namespace(
        dictionary="{}",
        pattern="**/*.dcm",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        continueOnError=False,
        acknowledgeRetainedTags="",
        dictionaryFile=str(dictionary_file),
    )
    with pytest.raises(SystemExit) as exc:
        main(options, dicom_tree, outdir)
    assert exc.value.code == 2
    assert not list(outdir.glob("**/*.dcm"))
