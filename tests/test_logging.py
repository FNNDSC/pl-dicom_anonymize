from dicom_anonymize import main


def test_logs_do_not_contain_phi(
        dicom_tree,
        default_options,
        caplog):

    input_dir, output_dir = dicom_tree

    main(
        default_options,
        input_dir,
        output_dir
    )

    logs = caplog.text

    assert "John" not in logs
    assert "Doe" not in logs
    assert "12345" not in logs