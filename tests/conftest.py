import pytest
from pathlib import Path
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
from argparse import Namespace


@pytest.fixture
def default_options():
    return Namespace(
        dictionary=None,
        pattern="**/*",
        deletePrivateTags=True
    )

@pytest.fixture
def dicom_tree(tmp_path):

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"

    input_dir.mkdir()
    output_dir.mkdir()

    for patient in ["patientA", "patientB"]:

        folder = input_dir / patient
        folder.mkdir()

        file_path = folder / "image.dcm"

        file_meta = FileDataset(
            None,
            {},
        ).file_meta

        file_meta.MediaStorageSOPClassUID = generate_uid()
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.ImplementationClassUID = generate_uid()

        ds = FileDataset(
            str(file_path),
            {},
            file_meta=file_meta,
            preamble=b"\0" * 128,
        )
        ds.add_new(
            0x00190010,
            "LO",
            "PRIVATE_VALUE"
        )


        ds.PatientName = "John^Doe"
        ds.PatientID = "12345"
        ds.PatientBirthDate = "19700101"

        ds.StudyInstanceUID = "1.2.3.4"
        ds.SeriesInstanceUID = "1.2.3.4.5"
        ds.SOPInstanceUID = generate_uid()

        ds.save_as(file_path)

    return input_dir, output_dir