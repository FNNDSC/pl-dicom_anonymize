from pathlib import Path
from dicom_anonymize import parser, main

def test_output_preserves_relative_paths(
        dicom_tree,
        default_options):

    input_dir, output_dir = dicom_tree

    main(
        default_options,
        input_dir,
        output_dir
    )