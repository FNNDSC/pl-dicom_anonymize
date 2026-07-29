from pathlib import Path
from dicom_anonymize import parser, main
import pytest

def test_output_preserves_relative_paths(
        dicom_tree,
        outdir,
        default_options):
    input_dir = dicom_tree
    output_dir = outdir
    with pytest.raises(SystemExit) as exc:
        main(
            default_options,
            input_dir,
            output_dir
        )