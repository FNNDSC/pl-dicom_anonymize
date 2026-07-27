import pydicom

from dicom_anonymize import main


def test_private_tags_removed(
        dicom_tree,
        default_options):

    input_dir, output_dir = dicom_tree

    main(
        default_options,
        input_dir,
        output_dir
    )

    ds = pydicom.dcmread(
        output_dir /
        "patientA" /
        "image.dcm"
    )

    assert not any(
        elem.tag.is_private
        for elem in ds
    )