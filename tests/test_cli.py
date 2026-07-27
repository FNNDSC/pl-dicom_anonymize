import subprocess


def test_cli_help():

    result = subprocess.run(
        [
            "dicom_anonymize",
            "--help"
        ],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0

    assert "--dictionary" in result.stdout
    assert "--deletePrivateTags" in result.stdout