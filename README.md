# A ChRIS plugin to anonymize DICOM files

[![Version](https://img.shields.io/docker/v/fnndsc/pl-dicom_anonymize?sort=semver)](https://hub.docker.com/r/fnndsc/pl-dicom_anonymize)
[![MIT License](https://img.shields.io/github/license/fnndsc/pl-dicom_anonymize)](https://github.com/FNNDSC/pl-dicom_anonymize/blob/main/LICENSE)
[![ci](https://github.com/FNNDSC/pl-dicom_anonymize/actions/workflows/ci.yml/badge.svg)](https://github.com/FNNDSC/pl-dicom_anonymize/actions/workflows/ci.yml)


`pl-dicom_anonymize` is a **ChRIS ds plugin** that recursively de-identifies
DICOM datasets using
[KitwareMedical/dicom-anonymizer](https://github.com/KitwareMedical/dicom-anonymizer)
as the underlying anonymization engine.

The plugin wraps the upstream library with additional safeguards for production
workflows, including recursive directory traversal, independent output
verification, machine-readable reporting, safe output handling, and support for
parameterized anonymization dictionaries.

### Confidentiality profile edition

The pinned release (`dicom-anonymizer==1.0.13.post1`) ships two built-in
rule tables — `dicomfields_2023` (PS3.15 **2023e** Table E.1-1) and
`dicomfields_2024b` — but **only `dicomfields_2023` is reachable from
upstream's own CLI**; selecting `2024b` requires calling the Python API
directly with `base_rules_gen=initialize_actions_2024b`, which upstream's
`main()` does not expose as a flag. This plugin calls `anonymize_dicom_file`
without overriding `base_rules_gen`, so **it uses the 2023e profile**,
consistent with this project's policy of exposing exactly upstream's actual
CLI surface

---

| Upstream `dicom-anonymizer` CLI | This plugin | Notes |
|---|---|---|
| `input` (positional) | *(implicit: `inputdir`)* | Supplied by ChRIS |
| `output` (positional) | *(implicit: `outputdir`)* | Supplied by ChRIS |
| `--keepPrivateTags` | `--keepPrivateTags` | Same semantics; default `False` |
| `--dictionary PATH` | `--dictionaryFile PATH` | JSON dictionary file; path must be reachable inside the container |
| `-t TAG ACTION [ARGS...]` (repeatable) | `--dictionary` (JSON) | See note below |
| `-v` / `--version` | `--upstreamVersion` | Prints plugin + pinned upstream version |

**Note on `-t`:** Upstream `dicom-anonymizer` supports multiple `-t TAG ACTION
[ARGS...]` arguments using argparse's repeatable argument mechanism. ChRIS
plugins cannot expose such parameters because the plugin schema supports only
single-valued scalar arguments. To preserve the same functionality in a
ChRIS-compatible way, this plugin accepts a JSON dictionary via
`--dictionary`, which can express an arbitrary number of anonymization rules in
a single parameter.

# Custom anonymization dictionaries

Additional or overriding anonymization rules can be supplied either inline with
`--dictionary` or from a JSON file using `--dictionaryFile`.

When both are provided, rules from `--dictionary` are applied on top of rules
from `--dictionaryFile`. If the same DICOM tag is specified in both,
the inline `--dictionary` rule takes precedence.

## Tag keys: keyword or (group, element)

Every tag key below can be given two ways:

- **A standard DICOM keyword**, e.g. `"PatientName"` or `"AccessionNumber"`
  -- this is almost always the one to use. It's resolved against pydicom's
  data dictionary, the same lookup pydicom itself uses, so it's exactly as
  authoritative as the hex form and far easier to get right without
  looking anything up.
- **A literal `(group, element)` tuple**, e.g. `"(0x0010, 0x0010)"` -- still
  needed for private tags and anything else with no standard keyword,
  since those can't be resolved by name at all.

Both forms resolve to the same underlying tag, so a keyword in
`--dictionary` and a tuple for the same tag in `--dictionaryFile` still
collide correctly for precedence purposes (see below). An unrecognized
keyword (a typo, or a tag that genuinely has no standard name) is a fatal
error at startup, before any file is touched -- not a silent no-op.

> **Tag tuple syntax**, if you do need the `(group, element)` form: keys are
> parsed with Python's `ast.literal_eval`, so they must be a literal
> 2-tuple such as `"(0x0010, 0x0010)"` (hex) or `"(16, 16)"` (decimal) --
> **not** the zero-padded `"(0010,0010)"` form often used in DICOM
> documentation, which Python rejects as an invalid decimal literal.

## Inline JSON

Simple actions use the same syntax as the upstream
`dicom-anonymizer` project.

```json
{
  "PatientName": "replace",
  "PatientID": "empty"
}
```

Example:

```bash
docker run --rm \
    -v $PWD/in:/incoming:ro \
    -v $PWD/out:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --dictionary '{"PatientName":"replace"}' \
    /incoming /outgoing
```

---

## JSON dictionary file

Rules can also be stored in a JSON file.

```json
{
  "PatientName": {
    "action": "replace_with_value",
    "value": "Anonymous"
  },
  "StudyDescription": {
    "action": "regexp",
    "find": ".*",
    "replace": "REDACTED"
  },
  "(0x0009, 0x0010)": "empty"
}
```

The last entry above is a private tag -- no standard keyword exists for it,
so it has to be given as a literal tuple.

Example:

```bash
docker run --rm \
    -v $PWD/in:/incoming:ro \
    -v $PWD/out:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --dictionaryFile /incoming/custom_dictionary.json \
    /incoming /outgoing
```

The plugin forwards these objects directly to the corresponding upstream action
implementations, allowing full support for parameterized actions such as
`replace_with_value` and `regexp`.

When both `--dictionaryFile` and `--dictionary` are provided, the file is
loaded first and the inline dictionary is applied on top of it.

---

# Independent output verification

Successful completion of the upstream anonymization routine is **not**
considered sufficient evidence that a file has been safely de-identified.

After every DICOM is written, the plugin independently re-opens the output file
and verifies that identifying elements expected to change have actually changed.

Only after verification succeeds is the temporary output atomically moved into
its final location.

If verification fails:

* the temporary output file is deleted,
* the file is marked as failed,
* no output file is produced.

Verification can be disabled if desired:

```bash
docker run --rm \
    -v $PWD/in:/incoming:ro \
    -v $PWD/out:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --skipOutputVerification \
    /incoming /outgoing
```

This option is intended only for specialized workflows where the additional
verification pass is not required.

---

# Intentionally retained identifying tags

Verification assumes that core identifying DICOM elements should not survive
unchanged.

If a custom anonymization policy intentionally preserves one or more
identifying tags, those tags must be explicitly acknowledged.

Example:

```bash
docker run --rm \
    -v $PWD/in:/incoming:ro \
    -v $PWD/out:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --dictionaryFile /incoming/custom_dictionary.json \
    --acknowledgeRetainedTags InstitutionName,ReferringPhysicianName \
    /incoming /outgoing
```

Only the listed DICOM keywords are exempted from verification. Any other
identifying elements remaining unchanged will still cause verification to fail.

---

# Non-DICOM files

Files matching `--pattern` are inspected for the DICOM file signature before
processing.

By default:

* DICOM files are anonymized.
* Non-DICOM files are skipped.

To instead copy non-DICOM files unchanged into the output directory:

```bash
docker run --rm \
    -v $PWD/in:/incoming:ro \
    -v $PWD/out:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --copyNonDicom \
    /incoming /outgoing
```

Copied files are transferred byte-for-byte and **are not inspected for PHI**.

---

# Continue processing after failures

By default, processing stops immediately after the first failed file.

To continue processing the remaining dataset while still reporting a failed
overall run:

```bash
docker run --rm \
    -v $PWD/in:/incoming:ro \
    -v $PWD/out:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --continueOnError \
    /incoming /outgoing
```

Even when this option is used, the plugin exits with a non-zero status if any
file fails.

---

# Processing summary

Every execution produces a machine-readable summary:

```
outputdir/
└── deidentification_summary.json
```

The summary contains:

* plugin version
* upstream `dicom-anonymizer` version
* elapsed runtime
* total files examined
* per-file processing status
* verification status
* processing counts
* selected runtime options, including whether `--continueOnError` was set
  and whether the run in fact stopped early because of it (`stopped_early`)
* overall success or failure

This file is intended for automated workflows, auditing, and troubleshooting.

---

# What this plugin guarantees

1. Every file under `inputdir`, at every depth, is either de-identified,
   explicitly skipped, copied (if requested), or causes the run to fail—never
   silently ignored.

2. The directory hierarchy under `inputdir` is preserved exactly in
   `outputdir`.

3. Nothing is ever written outside `outputdir`.

4. UID references (Study, Series, SOP Instance UID, etc.) are replaced
   consistently across the entire run, preserving relationships between
   datasets. **Scope of this consistency:** the old-UID → new-UID mapping is
   held in an in-memory table for the lifetime of one `dicom_anonymize`
   process invocation (this is upstream `dicom-anonymizer`'s own mechanism —
   a module-level dictionary, not something this plugin persists to disk).
   Concretely:
   - Consistent: every file under `inputdir` in a **single** run, however
     deeply nested, gets the same replacement UID for the same original UID
     -- so Series-to-Study and Instance-to-Series relationships inside that
     one dataset survive de-identification.
   - **Not** consistent: two **separate** invocations of the plugin (e.g.
     the same physical study submitted to two different ChRIS pipeline
     instances, or the same input directory run through the plugin twice)
     will assign different replacement UIDs to the same original UID, since
     each process starts with an empty mapping. Do not rely on UID matching
     to correlate output across separate runs.
   - `--continueOnError`: does not affect this. Stopping early on a failure
     doesn't reset or partially apply the mapping — every UID replacement
     already written to a delivered output file remains internally
     consistent with every other delivered file from that same run.

5. A file is only delivered after the plugin independently re-reads the output
   and verifies that identifying elements actually changed (unless verification
   has been explicitly disabled).

6. Output files are written atomically using temporary `.part` files before
   being moved into their final location.

7. Every execution produces a machine-readable
   `deidentification_summary.json` describing the outcome of the run.

8. Custom anonymization dictionaries support both standard upstream actions and
   parameterized actions such as `replace_with_value` and `regexp`.

9. Nothing written to stdout or stderr contains PHI, dataset contents, or the
   original relative file paths.

---

# Limitations

* **Confidentiality profile:** only PS3.15's `dicomfields_2023` (2023e)
  table is used; `dicomfields_2024b` is not reachable through this plugin's
  CLI (see *Confidentiality profile edition* above).
* **UID consistency scope:** the old→new UID mapping lives only for the
  duration of one plugin process invocation. It is not shared or
  reconciled across separate runs -- see item 4 above.
* **Non-DICOM files are not inspected for PHI.** With `--copyNonDicom`,
  matching non-DICOM files are copied byte-for-byte; the plugin has no way
  to know whether such a file (e.g. an accompanying report or screenshot)
  contains identifying information.
* **`-t TAG ACTION [ARGS...]` is not available.** Upstream's repeatable
  `-t` flag has no single-valued ChRIS-schema equivalent; use `--dictionary`
  / `--dictionaryFile` instead (see the CLI comparison table above).
* **Private tags nested inside a private Sequence, with `--keepPrivateTags`
  set:** upstream `dicom-anonymizer` leaves PHI nested this way untouched
  even though `--keepPrivateTags` is meant only to preserve *non-identifying*
  private tags. This plugin's independent output verification step (on by
  default) catches this and fails the file rather than delivering it -- do
  not disable `--skipOutputVerification` if you use `--keepPrivateTags` on
  data that may contain such sequences.
* **`--continueOnError` still means a non-zero exit on any failure.** It
  changes whether the run stops early, not whether the run is reported as
  successful.
* **CI test gating:** the `test` job must pass before an image is pushed
  (`.github/workflows/ci.yml`, `build` job's `needs: [test]`); this depends
  on the workflow file itself not being edited to remove that dependency.

---

# CLI options

| Option                                   | Description                                                             |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `--dictionary JSON`                      | Inline JSON dictionary of additional or overriding anonymization rules. |
| `--dictionaryFile PATH`                  | Read anonymization rules from a JSON file.                              |
| `--keepPrivateTags`                      | Preserve DICOM private tags.                                            |
| `--copyNonDicom`                         | Copy non-DICOM files unchanged instead of skipping them.                |
| `--skipOutputVerification`               | Disable the independent verification step.                              |
| `--acknowledgeRetainedTags TAG[,TAG...]` | Allow specified identifying tags to remain unchanged.                   |
| `--continueOnError`                      | Continue processing remaining files after individual failures.          |
| `--upstreamVersion`                      | Print both the plugin version and the pinned upstream library version.  |

## Running via ChRIS (CUBE)

This is a standard ChRIS `ds` plugin -- it reads from one plugin instance's
output and writes to its own, and takes no positional arguments beyond
those ChRIS supplies automatically (`inputdir`/`outputdir`).

* **Via `chrisui` / the ChRIS web UI:** search the plugin catalog for
  `pl-dicom_anonymize`, add it as a child of any node producing DICOM
  output, and set the options above as plugin parameters in the run form.
* **Via the `chrs` CLI or the CUBE API directly:** register the image with
  a CUBE instance (an admin step, done once per CUBE deployment) using the
  plugin representation that `docker run --rm ghcr.io/fnndsc/pl-dicom_anonymize:latest --json`
  prints (standard `chris_plugin` behavior), then create a plugin instance
  with the desired parameters against a prior instance's output.
* CI (`.github/workflows/ci.yml`) automatically uploads the plugin
  descriptor to a configured CUBE instance on every semver tag push, via
  `FNNDSC/upload-chris-plugin`.
* Once registered, the plugin behaves identically to the Docker examples
  above -- CUBE mounts the previous plugin instance's output as `inputdir`
  and a fresh directory as `outputdir`, and passes through whatever
  parameters were set in the run form as the equivalent CLI flags.

## Installation

### Clone the repository

```bash
git clone https://github.com/FNNDSC/pl-dicom_anonymize.git
cd pl-dicom_anonymize
```

### Install locally

Create and activate a Python environment (recommended), then install the
dependencies and the plugin.

```bash
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

The editable installation makes local source changes immediately available
without reinstalling the package.

---

## Building the Docker image

Build the plugin container locally:

```bash
docker build -t pl-dicom_anonymize:local .
```

You can verify the installation by printing the plugin version:

```bash
docker run --rm pl-dicom_anonymize:local --version
```

or

```bash
docker run --rm pl-dicom_anonymize:local --upstreamVersion
```

---

## Running from the command line

After installing locally, the plugin can be executed directly:

```bash
dicom_anonymize [OPTIONS] INPUTDIR OUTPUTDIR
```

Example:

```bash
dicom_anonymize \
    ./incoming \
    ./outgoing
```

Preserve private tags:

```bash
dicom_anonymize \
    --keepPrivateTags \
    ./incoming \
    ./outgoing
```

Use a custom anonymization dictionary:

```bash
dicom_anonymize \
    --dictionaryFile custom_dictionary.json \
    ./incoming \
    ./outgoing
```

Copy non-DICOM files as well:

```bash
dicom_anonymize \
    --copyNonDicom \
    ./incoming \
    ./outgoing
```

Skip independent output verification:

```bash
dicom_anonymize \
    --skipOutputVerification \
    ./incoming \
    ./outgoing
```

Continue processing after individual file failures:

```bash
dicom_anonymize \
    --continueOnError \
    ./incoming \
    ./outgoing
```

---

## Running with Docker

The recommended container invocation is:

```bash
docker run --rm \
    -v $PWD/incoming:/incoming:ro \
    -v $PWD/outgoing:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    /incoming /outgoing
```

Using a custom dictionary:

```bash
docker run --rm \
    -v $PWD/incoming:/incoming:ro \
    -v $PWD/outgoing:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --dictionaryFile /incoming/custom_dictionary.json \
    /incoming /outgoing
```

Using an inline dictionary:

```bash
docker run --rm \
    -v $PWD/incoming:/incoming:ro \
    -v $PWD/outgoing:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --dictionary '{"PatientName":"replace"}' \
    /incoming /outgoing
```


## Testing

### Install development dependencies

```bash
pip install -r requirements.txt
pip install -e .
pip install pytest
```

### Run the test suite

```bash
pytest -v
```

or run a specific test:

```bash
pytest tests/test_private_tags.py -v
```

### Test inside Docker

```bash
docker build --build-arg extras_require=dev -t pl-dicom_anonymize:dev .
docker run --rm \
    -v "$PWD:/app:ro" \
    -w /app \
    pl-dicom_anonymize:dev \
    pytest -v -o cache_dir=/tmp/pytest
```

Two things about this command are load-bearing, not optional style:

* **The volume mount is required.** The `Dockerfile`'s final build step
  installs the plugin non-editably (`pip install .`) and then deletes the
  entire source tree it was built from (`rm -rf ${SRCDIR}`), leaving
  `WORKDIR /`. A built image contains no `tests/` directory at all -- run
  `pytest` against it with nothing mounted and it collects zero tests and
  exits `5` (`no tests ran`), not a passing empty run.
* **`-o cache_dir=/tmp/pytest` is required given the `:ro` mount.** Without
  it, pytest tries to create its own `.pytest_cache/` inside the read-only
  `/app` and fails outright. (Test *collection* itself is fine read-only --
  Python and pytest's assertion-rewriting importer both silently skip
  writing `__pycache__` bytecode when they hit a permission error rather
  than raising.)

Because the installed package is whatever was baked in at the last
`docker build`, not the live contents of the mount, this two-step sequence
(build, then test) always tests what you just built. If you edit
`dicom_anonymize.py` and only re-run the second command, you're testing the
previous build, not your edit -- rebuild first.

## Dependencies, licensing, and maintenance

* All runtime dependencies are pinned exactly in `requirements.txt`, and the
  base container image is pinned to a specific patch tag in `Dockerfile`.
* [`sbom.cdx.json`](./sbom.cdx.json) is a CycloneDX software bill of
  materials for the plugin's full runtime dependency closure (including
  transitive dependencies like `pydicom` and `tqdm`, which
  `dicom-anonymizer` pulls in but which aren't listed directly in
  `requirements.txt`).
* [`NOTICES.md`](./NOTICES.md) and [`third_party_licenses/`](./third_party_licenses)
  contain the license notices required by each pinned dependency.
* [`MAINTENANCE.md`](./MAINTENANCE.md) documents the upgrade procedure for
  `dicom-anonymizer`, `pydicom`, `chris_plugin`, and the base image,
  including which tests and README examples to re-verify after each
  upgrade, and how to regenerate the SBOM.

