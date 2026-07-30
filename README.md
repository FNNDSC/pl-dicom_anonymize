# A ChRIS plugin to anonymize DICOM files

[![Version](https://img.shields.io/docker/v/fnndsc/pl-dicom_anonymize?sort=semver)](https://hub.docker.com/r/fnndsc/pl-dicom_anonymize)
[![MIT License](https://img.shields.io/github/license/fnndsc/pl-dicom_anonymize)](https://github.com/FNNDSC/pl-dicom_anonymize/blob/main/LICENSE)
[![ci](https://github.com/FNNDSC/pl-dicom_anonymize/actions/workflows/ci.yml/badge.svg)](https://github.com/FNNDSC/pl-dicom_anonymize/actions/workflows/ci.yml)

`pl-dicom_anonymize` is a [_ChRIS_](https://chrisproject.org/)
``ds`` plugin that recursively de-identifies a DICOM dataset, using
[KitwareMedical/dicom-anonymizer](https://github.com/KitwareMedical/dicom-anonymizer)
(pinned to **1.0.13.post1**) as the underlying anonymization engine.

## Abstract

...

## Installation

`pl-dicom_anonymize` is a _[ChRIS](https://chrisproject.org/) plugin_, meaning it can
run from either within _ChRIS_ or the command-line.

## Usage: local CLI, container, and ChRIS

### Local CLI (no container)

```bash
git clone https://github.com/fnndsc/pl-dicom_anonymize.git
cd pl-dicom_anonymize
pip install -r requirements.txt
pip install -e .

dicom_anonymize --help
dicom_anonymize /path/to/input /path/to/output
```

`dicom_anonymize` is the installed console-script entry point
(`python3 -m dicom_anonymize ...`) works identically.

### Container

```bash
docker build -t pl-dicom_anonymize:local .

docker run --rm \
  -v /path/to/input:/incoming:ro \
  -v /path/to/output:/outgoing \
  pl-dicom_anonymize:local \
  dicom_anonymize /incoming /outgoing
```

Mount `inputdir` read-only (`:ro`) if your Docker setup supports it — the
plugin never writes there, and `:ro` gives you an extra, enforced guarantee
of that on top of the plugin's own behavior. Pre-built images (once
published — see [Publishing to a ChRIS store](#publishing-to-a-chris-store))
are available at `ghcr.io/fnndsc/pl-dicom_anonymize:<version>`.
## What this plugin guarantees

1. Every file under `inputdir`, at every depth, is either de-identified into
   the identical relative path under `outputdir`, explicitly skipped, or
   causes the run to fail — never silently ignored.
2. Nothing is ever written outside `outputdir`.
3. UID references (Study/Series/SOP Instance UID, etc.) are replaced
   consistently across the *entire* run, so relationships between studies,
   series, and instances in the original dataset are preserved in the
   de-identified output.
4. A file is only delivered as output after the plugin **independently
   re-reads it from disk and confirms** identifying elements actually
   changed — not merely because the upstream library call returned without
   raising.
5. Nothing written to stdout/stderr (ChRIS job logs) contains PHI, dataset
   content, or even the relative file paths from the input dataset (which,
   in real-world data, are not guaranteed to be PHI-free themselves).

## Recursive processing, path preservation, and collision avoidance

The plugin uses `chris_plugin.PathMapper.file_mapper(inputdir, outputdir,
glob="**/*")`, which:

- walks `inputdir` recursively (`**/*` matches every file at every depth,
  not just the top level — this matters because **upstream
  `dicom-anonymizer`'s own directory-mode CLI only processes the top level
  of a folder** via `os.listdir`, not a recursive walk; this plugin does not
  rely on upstream's own directory traversal for exactly this reason, and
  instead calls its file-level function, `anonymize_dicom_file`, once per
  discovered file under our own recursive walk),
- computes each output path as `outputdir / <path of input file relative to
  inputdir>`, i.e. the directory structure is mirrored exactly, never
  flattened,
- creates any needed parent directories under `outputdir` automatically.

Because the relative path (including all intermediate directory names) is
preserved verbatim and directories are never flattened, two input files can
only collide in the output if they already occupied the exact same path
under `inputdir` — which is impossible on a real filesystem. This plugin
deliberately does **not** rename files by UID or content hash (a strategy
some anonymizers use, which can produce collisions when flattening a tree
that contains legitimately repeated instance numbers/filenames across
series) — collision-freedom here is a structural property of the mapping,
not a runtime check.

Content, not extension, decides what counts as DICOM: every candidate file
is sniffed for the `DICM` magic bytes at offset 128 (`dicom_deid/safety.py
::is_dicom_file`), because real acquisition trees routinely contain
extension-less files (e.g. `IM0001`). `--pattern` (default `**/*`) only
narrows which files are even considered candidates; it never causes a match
to bypass the content sniff.

## Pinning policy & maintenance procedure

**Every runtime dependency in `requirements.txt` is pinned with `==`, never
a range.** This is deliberate: this plugin's only job is deterministic,
auditable de-identification, and a silent transitive upgrade of
`dicom-anonymizer` (or `pydicom`, which it uses to parse/write files) could
silently change *which* tags get scrubbed and *how* — a compliance and
patient-safety issue, not merely a version bump.

| Package | Pinned version | Why |
|---|---|---|
| `dicom-anonymizer` | `1.0.13.post1` | The validated anonymization engine (GitHub release `v1.0.13-1`) |
| `pydicom` | `2.4.5` | Newest 2.x release; `dicom-anonymizer` 1.0.13.post1 requires `pydicom<3` |
| `tqdm` | `4.69.1` | Transitive dependency of `dicom-anonymizer`; pinned for reproducibility |
| `chris_plugin` | `0.4.0` | ChRIS plugin SDK (`PathMapper`, `@chris_plugin`) |

The Dockerfile independently asserts, at build time, that the installed
`dicom-anonymizer` version matches `dicom_deid.UPSTREAM_DICOM_ANONYMIZER_VERSION`
— a bump to `requirements.txt` that isn't matched by a bump to that constant
(or vice versa) fails the image build rather than shipping silently
inconsistent metadata.

### Upgrade procedure

Follow this checklist for **every** dependency bump, most importantly
`dicom-anonymizer` itself:

1. **Read the upstream changelog/diff** for the target version against the
   currently-pinned version — specifically for changes to: the default tag
   action tables (`dicomanonymizer/dicom_fields/*`), the CLI argument list
   (`dicomanonymizer/anonymizer.py::main`), and the public function
   signatures this plugin calls directly
   (`anonymize_dicom_file`, `parse_tag_actions_arguments`,
   `parse_dictionary_argument`, and the module-global UID map in
   `dicomanonymizer.simpledicomanonymizer`).
2. **Update the version pin** in `requirements.txt`, `pyproject.toml`
   (`dependencies`), and `dicom_deid.UPSTREAM_DICOM_ANONYMIZER_VERSION`, all
   in the same commit/PR.
3. **Re-run the full test suite** (`pytest tests/ -v`) unchanged — if
   upstream changed which tags get scrubbed by default, some assertions in
   `tests/test_integration.py` (which check specific tags were removed) may
   now need updating; treat any such change as a signal to re-review, not
   just re-baseline the test.
4. **Re-verify the exposed CLI mapping**: diff upstream's `main()`
   argparse setup against the "Note on -t"/CLI-mapping section below. If
   upstream added a new CLI flag, add the equivalent plugin flag in the same
   PR (see [CLI reference](#cli-reference) for the mapping convention) —
   do not let the plugin's surface silently fall behind upstream's.
5. **Rebuild and smoke-test the Docker image** (`docker build .` — the
   build-time version-assertion step will fail loudly if the pins are
   inconsistent), and run it against a small real (de-identified/synthetic)
   dataset before tagging a release.
6. **Update `CHANGELOG.md`** with old → new version numbers for every
   changed pin, plus anything user-visible that changed as a result (new
   default rule for a tag, a fixed bug in a specific action function, etc).
7. **Tag and release** (`git tag vX.Y.Z`) — this triggers
   `.github/workflows/ci.yml`'s build-and-publish job.

Never bump `dicom-anonymizer` as a side effect of an unrelated dependency
update (e.g. a `pip-compile`/`dependabot` bulk upgrade) — it should always be
its own, deliberate, changelog-reviewed step.

## CLI reference

Run `dicom_deid --help` for the authoritative, in-tool listing (also
reproduced in full via `chris_plugin_info`, which the ChRIS store uses to
render this plugin's parameter UI). Every option upstream's own CLI exposes
is available here:

| Upstream `dicom-anonymizer` CLI | This plugin | Notes |
|---|---|---|
| `input` (positional) | *(implicit: `inputdir`)* | Supplied by ChRIS |
| `output` (positional) | *(implicit: `outputdir`)* | Supplied by ChRIS |
| `--keepPrivateTags` | `--keepPrivateTags` | Same semantics; default `False` |
| `--dictionary PATH` | `--dictionaryFile PATH` | Same semantics; must be a container-reachable path |
| `-t TAG ACTION [ARGS...]` (repeatable) | `--tagActions '[[TAG, ACTION, ...ARGS], ...]'` (JSON) | See note below |
| `-v` / `--version` | `--upstreamVersion` | Prints plugin + pinned upstream version |

**Note on `-t`:** the ChRIS plugin parameter schema (what `chris_plugin_info`
emits and what the ChRIS store/UI renders as a form field) only supports
single-valued scalar parameter types (`str`/`int`/`float`/`bool`) — there is
no equivalent of argparse's repeatable `action="append", nargs="*"`. (This
isn't a hypothetical concern: an earlier draft of this plugin tried a custom
argparse `type=` callable for this flag, and `chris_plugin_info` crashed
trying to validate its default value against a non-type callable.) So
`--tagActions` instead takes a single JSON array of the same `[tag, action,
...args]` tuples upstream's `-t` accepts, fed through upstream's own
`parse_tag_actions_arguments()` unmodified — this is a lossless, mechanical
adaptation to the plugin schema, not a reduction in functionality.
## Examples

`dicom_anonymize` requires two positional arguments: a directory containing
input data, and a directory where to create output data.
First, create the input directory and move input data into it.

```shell
mkdir incoming/ outgoing/
mv some.dat other.dat incoming/
apptainer exec docker://fnndsc/pl-dicom_anonymize:latest dicom_anonymize [--args] incoming/ outgoing/
```

## Development

Instructions for developers.

### Building

Build a local container image:

```shell
docker build -t localhost/fnndsc/pl-dicom_anonymize .
```

### Running

Mount the source code `dicom_anonymize.py` into a container to try out changes without rebuild.

```shell
docker run --rm -it --userns=host -u $(id -u):$(id -g) \
    -v $PWD/dicom_anonymize.py:/usr/local/lib/python3.12/site-packages/dicom_anonymize.py:ro \
    -v $PWD/in:/incoming:ro -v $PWD/out:/outgoing:rw -w /outgoing \
    localhost/fnndsc/pl-dicom_anonymize dicom_anonymize /incoming /outgoing
```

### Testing

Run unit tests using `pytest`.
It's recommended to rebuild the image to ensure that sources are up-to-date.
Use the option `--build-arg extras_require=dev` to install extra dependencies for testing.

```shell
docker build -t localhost/fnndsc/pl-dicom_anonymize:dev --build-arg extras_require=dev .
docker run --rm -it localhost/fnndsc/pl-dicom_anonymize:dev pytest
```

Alternatively,

```
pip install -r requirements.txt pytest
pip install -e .
pytest -v
```

## Release

Steps for release can be automated by [Github Actions](.github/workflows/ci.yml).
This section is about how to do those steps manually.

### Increase Version Number

Increase the version number in `setup.py` and commit this file.

### Push Container Image

Build and push an image tagged by the version. For example, for version `1.2.3`:

```
docker build -t docker.io/fnndsc/pl-dicom_anonymize:1.2.3 .
docker push docker.io/fnndsc/pl-dicom_anonymize:1.2.3
```

### Get JSON Representation

Run [`chris_plugin_info`](https://github.com/FNNDSC/chris_plugin#usage)
to produce a JSON description of this plugin, which can be uploaded to _ChRIS_.

```shell
docker run --rm docker.io/fnndsc/pl-dicom_anonymize:1.2.3 chris_plugin_info -d docker.io/fnndsc/pl-dicom_anonymize:1.2.3 > chris_plugin_info.json
```

Intructions on how to upload the plugin to _ChRIS_ can be found here:
https://chrisproject.org/docs/tutorials/upload_plugin

