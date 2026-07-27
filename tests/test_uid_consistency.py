import pydicom

from dicom_anonymize import main


def test_uid_replacement_and_consistency(
        dicom_tree,
        default_options):

    input_dir, output_dir = dicom_tree

    main(
        default_options,
        input_dir,
        output_dir
    )

    ds1 = pydicom.dcmread(
        output_dir /
        "patientA" /
        "image.dcm"
    )

    ds2 = pydicom.dcmread(
        output_dir /
        "patientB" /
        "image.dcm"
    )

    # UID should not remain original
    assert ds1.StudyInstanceUID != "1.2.3.4"

    # Same original UID -> same anonymized UID
    assert (
        ds1.StudyInstanceUID
        ==
        ds2.StudyInstanceUID
    )