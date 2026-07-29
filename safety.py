"""
Safety helpers for pl-dicom_anonymize.

Everything in this module exists to serve two hard invariants of the plugin:

1.  An original, identified DICOM file must NEVER be silently emitted as if
    it were de-identified output. If we cannot positively verify that a file
    was de-identified, we do not deliver it -- we fail the file instead.

2.  Logs, stderr, exit messages, and the machine-readable run summary must
    never disclose PHI -- including PHI that leaks in indirectly, such as
    through directory/file names or exception text that happens to quote a
    tag value.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import pydicom
from pydicom.errors import InvalidDicomError

# Tags that, if the *value survives byte-for-byte* between the input and
# output dataset, indicate de-identification did not do its job for that
# tag. This list is intentionally broader than the upstream tool's own
# U_TAGS/D_TAGS groups: it is our independent, defense-in-depth check, not
# a re-statement of the anonymizer's own rule table. Keeping this list
# separate from dicom-anonymizer's internals means a future upstream
# refactor of *how* it anonymizes can't silently disable *our* check.
CORE_IDENTIFYING_TAGS = (
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientAddress",
    "PatientTelephoneNumbers",
    "OtherPatientIDs",
    "OtherPatientNames",
    "InstitutionName",
    "InstitutionAddress",
    "ReferringPhysicianName",
    "PerformingPhysicianName",
    "AccessionNumber",
    "StudyID",
)

# UID-bearing tags dicom-anonymizer's U_TAGS/X_Z_U_STAR_TAGS groups replace
# with newly-generated, mapped UIDs. We independently confirm at least the
# top-level identity chain actually changed.
CORE_UID_TAGS = (
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
)


class Status(str, Enum):
    PROCESSED = "processed"
    SKIPPED_NOT_DICOM = "skipped_not_dicom"
    COPIED_NON_DICOM = "copied_non_dicom"
    FAILED = "failed"


@dataclass
class FileResult:
    """
    Outcome for a single input path.

    Deliberately does NOT store the relative path or any dataset content --
    callers decide, in exactly one place (the CLI's PHI-safe logging layer),
    how much path information is appropriate for a given sink (stdout/stderr
    job logs vs. the on-disk summary that lives alongside the data itself).
    """

    status: Status
    error_class: Optional[str] = None
    error_summary: Optional[str] = None
    verified: bool = False


def relpath_hash(relative_path: Path) -> str:
    """
    A short, non-reversible correlation id for a relative path.

    Used anywhere output might be more widely visible than the data itself
    (namely: stdout/stderr, which ChRIS exposes as job logs through its API
    and UI to a potentially broader audience than those authorized to view
    the underlying PHI). Directory/file names in a real-world DICOM tree
    are *not* guaranteed to be PHI-free (e.g. `Smith_John/study1/img1.dcm`),
    so even the relative path string itself is treated as sensitive here.
    """
    digest = hashlib.sha256(str(relative_path).encode("utf-8")).hexdigest()
    return digest[:12]


def sanitize_exception(exc: BaseException) -> tuple[str, str]:
    """
    Turn an exception into a (class_name, generic_summary) pair that is
    safe to log or persist.

    We deliberately do NOT use str(exc) verbatim: pydicom and
    dicom-anonymizer exceptions can and do interpolate tag *values* into
    their messages (e.g. a malformed-value ValueError quoting the offending
    string), which could itself be PHI. Instead we map known exception
    types to fixed, generic descriptions and fall back to a type-only
    description for anything unrecognized.
    """
    name = type(exc).__name__
    known = {
        "InvalidDicomError": "input file is not a valid DICOM file (missing/bad preamble or meta header)",
        "MalformedDicomError": "input file has DICOM magic bytes but is missing mandatory File Meta Information and was rejected rather than leniently parsed",
        "FileNotFoundError": "input file disappeared or was unreadable before processing completed",
        "PermissionError": "insufficient filesystem permissions to read input or write output",
        "IsADirectoryError": "expected a file but found a directory at that path",
        "KeyError": "a required DICOM data element or dictionary key was missing",
        "ValueError": "a data element could not be parsed, converted, or written under the requested rules",
        "AttributeError": "an unexpected dataset structure was encountered",
        "OSError": "an I/O error occurred while reading or writing",
    }
    return name, known.get(name, "processing failed with an unexpected internal error")


def is_dicom_file(path: Path) -> bool:
    """
    Content-based DICOM detection (DICM magic bytes at offset 128).

    We do *not* rely on file extensions: real-world DICOM datasets, and in
    particular ChRIS input trees, routinely contain extension-less files or
    files named e.g. `IM0001` rather than `*.dcm`. Relying on extensions
    would silently exclude such files from de-identification, which is
    exactly the "silently pass through" failure mode this plugin must not
    have -- so we always sniff content instead.
    """
    try:
        with open(path, "rb") as fh:
            fh.seek(128)
            return fh.read(4) == b"DICM"
    except OSError:
        return False


class MalformedDicomError(InvalidDicomError):
    """
    Raised when a file has the DICOM magic bytes but pydicom's own lenient
    fallback parsing (it will read on and guess a transfer syntax even when
    the mandatory File Meta Information group is missing or empty) produces
    a dataset that is not conformant DICOM.

    This exists because content-sniffing on the magic bytes alone is not
    sufficient: a file can have a valid preamble + "DICM" marker yet contain
    garbage afterward, and pydicom (with force=False) can still return
    *without raising*, having misinterpreted the garbage as a small number
    of data elements. Silently emitting "de-identified" output for such a
    file would violate the never-pass-through-unverified guarantee just as
    much as mishandling a genuinely identified file would -- so we treat
    it as invalid input and fail the file instead.
    """


# The File Meta Information group (0002,xxxx) is mandatory in the DICOM
# Part 10 file format (PS3.10 section 7.1). A conformant file must have all
# of these. If any are missing, we do not consider the file a valid DICOM
# object regardless of whether the magic bytes were present.
_REQUIRED_FILE_META_ELEMENTS = (
    "MediaStorageSOPClassUID",
    "MediaStorageSOPInstanceUID",
    "TransferSyntaxUID",
)


def read_dataset_for_verification(path: Path) -> pydicom.dataset.FileDataset:
    """
    Read a DICOM file, raising InvalidDicomError (or the stricter
    MalformedDicomError) for anything that is not a fully conformant DICOM
    Part 10 file -- rather than trusting pydicom's lenient fallback parsing.
    """
    dataset = pydicom.dcmread(str(path), force=False)
    file_meta = getattr(dataset, "file_meta", None)
    missing = [
        name
        for name in _REQUIRED_FILE_META_ELEMENTS
        if file_meta is None or not hasattr(file_meta, name)
    ]
    if missing:
        raise MalformedDicomError(
            "missing mandatory File Meta Information element(s): " + ", ".join(missing)
        )
    return dataset


def verify_deidentified(
    original: pydicom.dataset.FileDataset,
    output_path: Path,
    acknowledged_retained_tags: frozenset[str] = frozenset(),
) -> tuple[bool, Optional[str]]:
    """
    Independently confirm that the file written to ``output_path`` no longer
    carries the original dataset's identifying values.

    This is a *second*, independent safety net on top of whatever
    dicom-anonymizer itself did -- it re-opens the file we actually wrote to
    disk (catching truncated/partial writes too) and checks it, rather than
    trusting that "the library call returned without raising" implies
    correctness.

    Returns (ok, reason_if_not_ok). ``reason_if_not_ok`` is a fixed,
    generic string (never a tag value) suitable for logging.
    """
    try:
        output_ds = pydicom.dcmread(str(output_path), force=False)
    except InvalidDicomError:
        return False, "output file failed to re-parse as valid DICOM after writing"
    except OSError:
        return False, "output file could not be read back after writing"

    for tag_name in CORE_IDENTIFYING_TAGS:
        if tag_name in acknowledged_retained_tags:
            continue
        orig_val = getattr(original, tag_name, None)
        if orig_val in (None, ""):
            continue
        out_val = getattr(output_ds, tag_name, None)
        if out_val is not None and str(out_val) == str(orig_val):
            return False, f"identifying element '{tag_name}' unchanged after processing"

    for tag_name in CORE_UID_TAGS:
        orig_val = getattr(original, tag_name, None)
        out_val = getattr(output_ds, tag_name, None)
        if orig_val and out_val and str(orig_val) == str(out_val):
            return False, f"UID element '{tag_name}' unchanged after processing"

    # Defense-in-depth deep scan: make sure literal original identifying
    # values do not appear verbatim *anywhere else* in the output dataset --
    # including nested inside a Sequence item that the top-level attribute
    # checks above can't see. This matters concretely: testing showed that
    # when --keepPrivateTags is used, PHI nested inside a *private* Sequence
    # is left completely untouched by upstream (private tags are swept as a
    # whole *group*, not walked into recursively the way certain
    # standard/public sequences are), so `str(output_ds)` (which pydicom
    # renders recursively, including sequence item contents) is the only
    # thing that catches it here.
    needles = []
    for tag_name in (
        "PatientName",
        "PatientID",
        "AccessionNumber",
        "InstitutionName",
        "ReferringPhysicianName",
    ):
        if tag_name in acknowledged_retained_tags:
            continue
        val = getattr(original, tag_name, None)
        if val not in (None, ""):
            needles.append(str(val))

    if needles:
        haystack = str(output_ds)
        for needle in needles:
            if len(needle) >= 4 and needle in haystack:
                return False, "an original identifying value was found elsewhere in the output dataset"

    return True, None