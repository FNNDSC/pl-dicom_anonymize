from dicom_anonymize import main
import pytest

def test_logs_do_not_contain_phi(
        dicom_tree,
        outdir,
        default_options,
        caplog):

    input_dir = dicom_tree
    output_dir = outdir
    with pytest.raises(SystemExit) as exc:

        main(
            default_options,
            input_dir,
            output_dir
        )

    logs = caplog.text

    assert "John" not in logs
    assert "Doe" not in logs
    assert "12345" not in logs