import pydicom
import pytest
from dicom_anonymize import main


def test_uid_replacement_and_consistency(
        dicom_tree,
        outdir,
        default_options):
    input_dir = dicom_tree
    output_dir = outdir
    with pytest.raises(SystemExit):
        main(
            default_options,
            input_dir,
            output_dir
        )

    ds1 = pydicom.dcmread(
        output_dir /
        "patientA" /
        "series1" /
        "img1.dcm"
    )

    ds2 = pydicom.dcmread(
        output_dir /
        "patientA" /
        "series1" /
        "img2.dcm"
    )

    # UID should not remain original
    assert ds1.StudyInstanceUID != "1.2.3.4"

    # Same original UID -> same anonymized UID
    assert (
        ds1.StudyInstanceUID
        ==
        ds2.StudyInstanceUID
    )

def test_output_filenames_are_never_derived_from_uids(dicom_tree, outdir, default_options):
    """
    The plugin names output files identically to their input counterpart
    (mirrored relative path), never by new SOP/Series/Study UID. This is
    *why* collisions structurally cannot occur: two distinct input files
    can never share a relative path, whereas UID-based renaming schemes
    can collide (e.g. if an upstream bug ever produced a duplicate UID).
    """
    with pytest.raises(SystemExit):
        main(default_options,dicom_tree, outdir)

    out1 = pydicom.dcmread(str(outdir / "patientA/series1/img1.dcm"))
    out2 = pydicom.dcmread(str(outdir / "patientA/series2/img1.dcm"))
    # both retained their original filename "img1.dcm" despite getting
    # entirely different new SOPInstanceUIDs
    assert out1.SOPInstanceUID != out2.SOPInstanceUID
    assert (outdir / "patientA/series1/img1.dcm").name == "img1.dcm"
    assert (outdir / "patientA/series2/img1.dcm").name == "img1.dcm"