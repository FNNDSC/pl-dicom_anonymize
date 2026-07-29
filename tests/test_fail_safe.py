import pytest
import json
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

    main(
        default_options,
        input_dir,
        output_dir
    )

    # no identified data should leak
    assert len(list(output_dir.iterdir())) == 1

def test_malformed_input_fails_safely_and_is_never_emitted(dicom_tree, outdir, default_options):
    with pytest.raises(SystemExit) as exc:
        main(default_options, dicom_tree, outdir)
    assert exc.value.code == 1
    summary = json.loads((outdir / "deidentification_summary.json").read_text())
    assert summary["overall_status"] == "failed"
    failed = [f for f in summary["files"] if f["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["path"] == "patientA/series1/broken.dcm"
    assert not (outdir / "patientA/series1/broken.dcm").exists()