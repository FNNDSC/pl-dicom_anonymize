import pydicom

from dicom_anonymize import main


def test_patient_information_removed(
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

    assert ds.PatientName != "John^Doe"
    assert ds.PatientID != "12345"

    # Kitware default behavior anonymizes this
    assert ds.PatientBirthDate == '00010101'