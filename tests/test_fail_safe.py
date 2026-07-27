import pytest

from dicom_anonymize import main


def test_invalid_dicom_fails(
        tmp_path,
        default_options):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"

    input_dir.mkdir()
    output_dir.mkdir()

    bad_file = input_dir / "bad.dcm"

    bad_file.write_text(
        "this is not a dicom file"
    )

    with pytest.raises(Exception):

        main(
            default_options,
            input_dir,
            output_dir
        )

    # no identified data should leak
    assert list(output_dir.iterdir()) == []