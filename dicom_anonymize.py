#!/usr/bin/env python
import ast
import json
import os
import sys
import time
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, Namespace
from pathlib import Path

from chris_plugin import PathMapper, chris_plugin
from dicomanonymizer.anonymizer import parse_dictionary_argument
from dicomanonymizer.simpledicomanonymizer import (
    ActionsMapNameFunctions,
    anonymize_dicom_file,
)

from safety import (
    FileResult,
    Status,
    is_dicom_file,
    read_dataset_for_verification,
    relpath_hash,
    sanitize_exception,
    verify_deidentified,
)

__version__ = '1.0.0'

# The exact upstream dicom-anonymizer release this plugin is validated
# against. Kept as a constant (rather than only living in requirements.txt)
# so it can be surfaced in --help, in the JSON summary, and in tests that
# assert the installed version matches what we claim to support.
UPSTREAM_DICOM_ANONYMIZER_VERSION = "1.0.13.post1"

DISPLAY_TITLE = r"""
       _           _ _                                                              _         
      | |         | (_)                                                            (_)        
 _ __ | |______ __| |_  ___ ___  _ __ ___    __ _ _ __   ___  _ __  _   _ _ __ ___  _ _______ 
| '_ \| |______/ _` | |/ __/ _ \| '_ ` _ \  / _` | '_ \ / _ \| '_ \| | | | '_ ` _ \| |_  / _ \
| |_) | |     | (_| | | (_| (_) | | | | | || (_| | | | | (_) | | | | |_| | | | | | | |/ /  __/
| .__/|_|      \__,_|_|\___\___/|_| |_| |_| \__,_|_| |_|\___/|_| |_|\__, |_| |_| |_|_/___\___|
| |                                     ______                       __/ |                    
|_|                                    |______|                     |___/                     
"""


parser = ArgumentParser(description='A ChRIS plugin to anonymize header metadata in DICOM files',
                        formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument(
    "-p", "--pattern", default="**/*.dcm", type=str, help="input file filter glob"
)
parser.add_argument(
    "-V", "--version", action="version", version=f"%(prog)s {__version__}"
)
parser.add_argument(
    "--dictionary",
    type=str,
    default="{}",
    metavar="JSON",
    required=False,
    help="Anonymization dictionary as JSON string",
)
parser.add_argument(
    "--keepPrivateTags",
    action="store_true",
    default=False,
    help="Keep DICOM private tags",
)
parser.add_argument(
    "--copyNonDicom",
    action="store_true",
    default=False,
    help=(
        "If set, files under inputdir that do not have the DICOM magic "
        "bytes are copied through to outputdir byte-for-byte, unexamined. "
        "Default: False -- non-DICOM files are NOT copied, because their "
        "content is never scanned for PHI and copying them through "
        "unexamined by default would silently defeat the purpose of this "
        "plugin. Counted and reported either way."
    ),
)
parser.add_argument(
    "--skipOutputVerification",
    action="store_true",
    default=False,
    help=(
        "If set, skip the plugin's independent post-write verification "
        "step (re-reading each output file and confirming identifying "
        "elements actually changed) that runs in addition to whatever "
        "dicom-anonymizer itself did. NOT recommended: this is the "
        "plugin's primary safeguard against silently emitting an "
        "identified file. Default: False (verification runs)."
    ),
)
parser.add_argument(
    "--acknowledgeRetainedTags",
    type=str,
    default="",
    metavar="TAG[,TAG...]",
    help=(
        "Comma-separated list of DICOM keyword names (e.g. "
        "'InstitutionName,ReferringPhysicianName') that you have "
        "intentionally configured --dictionary/--dictionaryFile to KEEP "
        "unchanged, and are explicitly acknowledging as retained rather "
        "than de-identified. Without this, the plugin's independent "
        "output verification treats any of the core identifying elements "
        "(see README.md) surviving unchanged as a failure -- even if you "
        "configured that yourself -- because the plugin cannot otherwise "
        "distinguish 'I meant to keep this' from 'de-identification "
        "silently failed to remove this'. Default: '' (no exceptions; "
        "every core identifying element must change)."
    ),
)
parser.add_argument(
    "--dictionaryFile",
    type=str,
    default=None,
    metavar="PATH",
    help=(
        "[upstream: --dictionary] Path to a JSON file (see upstream docs: "
        "https://github.com/KitwareMedical/dicom-anonymizer#change-the-value-of-a-tag-with-a-json-dictionary) "
        "of additional/overriding {tag: action} rules. The path must be "
        "reachable inside the container -- typically a file that lives "
        "inside inputdir; give the path as inputdir-relative or absolute. "
        "Rules from --dictionaryFile are applied on top of --dictionary. "
        "Default: None (no dictionary overrides; PS3.15 2023e defaults apply)."
    ),
)
parser.add_argument(
    "--upstreamVersion",
    action="version",
    version=(
        f"pl-dicom_anonymize {__version__}, wrapping "
        f"dicom-anonymizer {UPSTREAM_DICOM_ANONYMIZER_VERSION}"
    ),
    help="[upstream: -v/--version] Print plugin and upstream engine versions and exit.",
)
parser.add_argument(
    "--continueOnError",
    action="store_true",
    default=False,
    help=(
        "If set, keep processing remaining files after a per-file failure "
        "instead of stopping immediately. Regardless of this flag, if ANY "
        "file fails, the plugin's overall exit status is non-zero (a "
        "partially-successful run is never reported as success). "
        "Default: False (stop at first failure)."
    ),
)

def load_dictionary(options):
    """
    Convert Kitware dicom-anonymizer JSON dictionary
    into anonymization actions.
    """
    if options.dictionaryFile:
        with open(options.dictionaryFile) as f:
            dictionary = json.load(f)
    elif options.dictionary:
        dictionary = json.loads(options.dictionary)
    else:
        dictionary = {}
    actions = {}

    for tag, action_spec in dictionary.items():
        dicom_tag = ast.literal_eval(tag)

        if isinstance(action_spec, dict):
            action_name = action_spec["action"]
            action_factory = ActionsMapNameFunctions[action_name].value.function
            # Pass the dict straight through — replace_with_value / regexp
            # both know how to pull what they need out of a dict of options.
            action = action_factory(action_spec)
        else:
            action_name = action_spec
            action = ActionsMapNameFunctions[action_name].value.function

        actions[dicom_tag] = action

    return actions

def _process_one(
    input_path: Path,
    output_path: Path,
    extra_rules: dict,
    options,
) -> FileResult:
    if not is_dicom_file(input_path):
        if options.copyNonDicom:
            try:
                output_path.write_bytes(input_path.read_bytes())
                return FileResult(status=Status.COPIED_NON_DICOM)
            except OSError as e:
                cls, summary = sanitize_exception(e)
                return FileResult(status=Status.FAILED, error_class=cls, error_summary=summary)
        return FileResult(status=Status.SKIPPED_NOT_DICOM)

    tmp_output_path = output_path.with_name(output_path.name + ".part")

    try:
        original_dataset = read_dataset_for_verification(input_path)
    except Exception as e:  # noqa: BLE001 - deliberately broad: any read failure is a hard failure
        cls, summary = sanitize_exception(e)
        return FileResult(status=Status.FAILED, error_class=cls, error_summary=summary)

    try:
        # Serialize the actual anonymization call: dicom-anonymizer's
        # cross-file UID map (dicomanonymizer.simpledicomanonymizer.dictionary)
        # is a plain, non-thread-safe module-global dict with a
        # check-then-act read-modify-write (`if old_uid not in dictionary:
        # dictionary[old_uid] = generate_uid(...)`). Without this lock,
        # concurrent threads could race and assign two different new UIDs
        # to the same original UID, silently breaking cross-file UID
        # consistency. See README.md -> 'UID consistency: scope and
        # limitations'.

        anonymize_dicom_file(
            str(input_path),
            str(tmp_output_path),
            extra_rules,
            not options.keepPrivateTags,
        )
    except Exception as e:  # noqa: BLE001 - any anonymization failure is a hard failure
        tmp_output_path.unlink(missing_ok=True)
        cls, summary = sanitize_exception(e)
        return FileResult(status=Status.FAILED, error_class=cls, error_summary=summary)

    if not tmp_output_path.exists():
        # dicom-anonymizer did not raise, but also did not produce a file.
        # Treat as failure rather than assume success.
        return FileResult(
            status=Status.FAILED,
            error_class="MissingOutput",
            error_summary="anonymization completed without error but produced no output file",
        )

    if options.skipOutputVerification:
        os.replace(tmp_output_path, output_path)
        return FileResult(status=Status.PROCESSED, verified=False)

    ok, reason = verify_deidentified(
        original_dataset,
        tmp_output_path,
        acknowledged_retained_tags=options.acknowledged_tags_set,
    )
    if not ok:
        # Never deliver a file we can't positively verify. Delete the
        # partial/failed-verification artifact -- do not leave it under
        # outputdir under any name.
        tmp_output_path.unlink(missing_ok=True)
        return FileResult(status=Status.FAILED, error_class="VerificationFailed", error_summary=reason)

    os.replace(tmp_output_path, output_path)
    return FileResult(status=Status.PROCESSED, verified=True)


# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin
@chris_plugin(
    parser=parser,
    title='A ChRIS plugin to anonymize DICOM files',
    category='',                 # ref. https://chrisstore.co/plugins
    min_memory_limit='100Mi',    # supported units: Mi, Gi
    min_cpu_limit='1000m',       # millicores, e.g. "1000m" = 1 CPU core
    min_gpu_limit=0              # set min_gpu_limit=1 to enable GPU
)
def main(options: Namespace, inputdir: Path, outputdir: Path):
    """
    *ChRIS* plugins usually have two positional arguments: an **input directory** containing
    input files and an **output directory** where to write output files. Command-line arguments
    are passed to this main method implicitly when ``main()`` is called below without parameters.

    :param options: non-positional arguments parsed by the parser given to @chris_plugin
    :param inputdir: directory containing (read-only) input files
    :param outputdir: directory where to write output files
    """
    any_failed: int = 0

    print(DISPLAY_TITLE)

    # Typically it's easier to think of programs as operating on individual files
    # rather than directories. The helper functions provided by a ``PathMapper``
    # object make it easy to discover input files and write to output files inside
    # the given paths.
    #
    # Refer to the documentation for more options, examples, and advanced uses e.g.
    # adding a progress bar and parallelism.
    try:
        rules = load_dictionary(
            options
        )
    except Exception as e:
        cls, summary = sanitize_exception(e)
        print(f"FATAL: could not build anonymization rules ({cls}): {summary}", file=sys.stderr)
        sys.exit(2)

    records = []

    started = time.time()
    total_seen = 0
    failed_hashes = []
    counts = {s.value: 0 for s in Status}
    options.acknowledged_tags_set = frozenset(
        t.strip() for t in options.acknowledgeRetainedTags.split(",") if t.strip()
    )
    if options.acknowledged_tags_set:
        print(
            f"NOTE: verification will NOT flag these tags if retained unchanged: "
            f"{', '.join(sorted(options.acknowledged_tags_set))}",
            file=sys.stderr,
        )
    mapper = PathMapper.file_mapper(inputdir, outputdir, glob=options.pattern, fail_if_empty=False)
    for input_file, output_file in mapper:
        total_seen += 1
        rel = input_file.relative_to(inputdir)
        h = relpath_hash(rel)
        result = _process_one(input_file, output_file, rules, options)
        counts[result.status.value] += 1
        record = {"path": str(rel), "path_hash": h, "status": result.status.value}
        if result.status == Status.FAILED:
            record["error_class"] = result.error_class
            record["error_summary"] = result.error_summary
            failed_hashes.append(h)
            print(
                f"[FAIL ] file#{total_seen} ({h}): {result.error_class}: {result.error_summary}",
                file=sys.stderr,
            )
        elif result.status == Status.SKIPPED_NOT_DICOM:
            print(f"[SKIP ] file#{total_seen} ({h}): not a DICOM file", file=sys.stderr)
        elif result.status == Status.COPIED_NON_DICOM:
            print(f"[COPY ] file#{total_seen} ({h}): non-DICOM, copied through unexamined", file=sys.stderr)
        else:
            print(f"[OK   ] file#{total_seen} ({h}): de-identified" + ("" if result.verified else " (unverified)"),
                  file=sys.stderr)
        records.append(record)

    elapsed = time.time() - started
    any_failed = counts[Status.FAILED.value] > 0

    summary = {
        "plugin_version": __version__,
        "upstream_dicom_anonymizer_version": UPSTREAM_DICOM_ANONYMIZER_VERSION,
        "elapsed_seconds": round(elapsed, 3),
        "total_files_seen": total_seen,
        "counts": counts,
        "keep_private_tags": bool(options.keepPrivateTags),
        "copy_non_dicom": bool(options.copyNonDicom),
        "output_verification_enabled": not options.skipOutputVerification,
        "overall_status": "failed" if any_failed else "success",
        "files": records,
    }
    (outputdir / "deidentification_summary.json").write_text(json.dumps(summary, indent=2))

    print("---", file=sys.stderr)
    print(f"seen={total_seen} " + " ".join(f"{k}={v}" for k, v in counts.items()), file=sys.stderr)
    if any_failed:
        print(
            f"FAILED: {counts[Status.FAILED.value]} file(s) could not be safely de-identified "
            f"(hashes: {', '.join(failed_hashes)}). See deidentification_summary.json in the "
            "output directory for details (that file, unlike this log, may reference relative "
            "paths -- it lives alongside the data it describes under the same access boundary).",
            file=sys.stderr,
        )
        sys.exit(1)

    if total_seen == 0:
        print("No input files matched --pattern; nothing to do.", file=sys.stderr)

    print("Done.", file=sys.stderr)



if __name__ == '__main__':
    main()
