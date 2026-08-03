import pytest
import pydicom
from pathlib import Path
from pydicom.dataset import FileMetaDataset, FileDataset
from pydicom.uid import generate_uid, ExplicitVRLittleEndian
from argparse import Namespace

def _make_dcm(path: Path, patient_name, patient_id, study_uid, series_uid, sop_uid):
    path.parent.mkdir(parents=True, exist_ok=True)
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientName = patient_name
    ds.PatientID = patient_id
    ds.PatientBirthDate = "19800101"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.InstitutionName = "General Hospital"
    ds.ReferringPhysicianName = "Dr Smith"
    ds.AccessionNumber = "ACC123"
    ds.StudyDescription = "Original clinical study description"
    ds.Modality = "MR"
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(str(path), write_like_original=False)

@pytest.fixture
def default_options():
    return Namespace(
        dictionary='{}',
        pattern="**/*",
        keepPrivateTags=False,
        copyNonDicom=False,
        skipOutputVerification=False,
        continueOnError=False,
        acknowledgeRetainedTags="",
        dictionaryFile=""
    )

@pytest.fixture
def dicom_tree(tmp_path):
    """
    A synthetic input tree exercising: recursion (nested dirs), a single
    patient/study spanning two series (for cross-file UID-consistency
    checks), a non-DICOM file, and a corrupt/malformed DICOM-looking file.
    """
    root = tmp_path / "input"
    study = generate_uid()
    series1 = generate_uid()
    series2 = generate_uid()

    _make_dcm(root / "patientA/series1/img1.dcm", "Doe^Jane", "MRN001", study, series1, generate_uid())
    _make_dcm(root / "patientA/series1/img2.dcm", "Doe^Jane", "MRN001", study, series1, generate_uid())
    _make_dcm(root / "patientA/series2/img1.dcm", "Doe^Jane", "MRN001", study, series2, generate_uid())

    (root / "notes").mkdir(parents=True, exist_ok=True)
    (root / "notes" / "readme.txt").write_text("not a dicom file")

    broken = root / "patientA/series1/broken.dcm"
    broken.write_bytes(b"\0" * 128 + b"DICM" + b"garbagegarbagegarbage")

    return root


@pytest.fixture
def outdir(tmp_path):
    d = tmp_path / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d

def make_dicom_with_nested_sequence(
    path: Path,
    *,
    private_sequence: bool,
    study_date: str = "20200615",
):
    """
    Build a single DICOM file with PHI duplicated inside a nested Sequence
    item, to exercise dicom-anonymizer's sequence-recursion behavior.

    private_sequence=False -> nests the PHI inside a *standard* sequence
        tag (Referenced Image Sequence, (0008,1140)) that IS itself a
        target in the PS3.15 2023e profile table -- upstream recurses into
        it and scrubs the nested PHI too (positive control).

    private_sequence=True -> nests the PHI inside a *private* group
        (with its own private creator block), which upstream only touches
        by deleting the entire private group wholesale
        (delete_private_tags=True, the plugin default) or leaves
        completely untouched, PHI and all, when private tags are kept
        (--keepPrivateTags).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientName = "Doe^Jane"
    ds.PatientID = "MRN001"
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.Modality = "MR"
    ds.StudyDate = study_date
    ds.SeriesDate = study_date

    item = pydicom.Dataset()
    item.PatientName = "Doe^Jane"
    item.PatientID = "MRN001"

    if private_sequence:
        ds.add_new(0x00410010, "LO", "ACME CORP PRIVATE CREATOR")
        item.add_new(0x00411001, "LO", "leaked-secret-note-about-patient")
        ds.add_new(0x00411010, "SQ", [item])
    else:
        ds.add_new((0x0008, 0x1140), "SQ", [item])  # Referenced Image Sequence

    ds.is_little_endian = True
    ds.is_implicit_VR = False
    ds.save_as(str(path), write_like_original=False)
    return ds