# A ChRIS plugin to anonymize DICOM files

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
| `--dictionary PATH` | `--dictionaryFile PATH` | Same semantics; must be a container-reachable path |
| `-t TAG ACTION [ARGS...]` (repeatable) | `--dictionary ` (JSON) | See note below |
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

## Inline JSON

Simple actions use the same syntax as the upstream
`dicom-anonymizer` project.

```json
{
  "(0010,0010)": "replace",
  "(0010,0020)": "empty"
}
```

Example:

```bash
docker run --rm \
    -v $PWD/in:/incoming:ro \
    -v $PWD/out:/outgoing \
    ghcr.io/fnndsc/pl-dicom_anonymize:latest \
    --dictionary '{"(0010,0010)":"replace"}' \
    /incoming /outgoing
```

---

## JSON dictionary file

Rules can also be stored in a JSON file.

```json
{
  "(0010,0010)": {
    "action": "replace_with_value",
    "value": "Anonymous"
  },
  "(0008,1030)": {
    "action": "regexp",
    "pattern": ".*",
    "replace": "REDACTED"
  }
}
```

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

When both `--dictionary` and `--dictionaryFile` are provided, rules from
`--dictionaryFile` override any matching rules supplied inline.

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
* selected runtime options
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
   datasets.

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
    --dictionary '{"(0010,0010)":"replace"}' \
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

Build a development image:

```bash
docker build \
    --build-arg extras_require=dev \
    -t pl-dicom_anonymize:dev .
```

Run the test suite:

```bash
docker run --rm \
    pl-dicom_anonymize:dev \
    pytest -v
```
