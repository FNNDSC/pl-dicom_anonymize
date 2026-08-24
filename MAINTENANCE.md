# Maintenance & Upgrade Procedure

## Why everything is pinned

`requirements.txt` pins exact versions (`==`) for every direct runtime
dependency, and the `Dockerfile`'s base image is pinned to a specific patch
tag. This plugin ships in clinical/research DICOM pipelines where a silent
upstream behavior change (e.g. which tags `dicom-anonymizer`'s default
profile scrubs) is a PHI-safety regression, not just a compatibility bug.
Nothing here should float on `latest`, a caret range, or an unpinned base
image.

## Upgrading `dicom-anonymizer`

This is the dependency most likely to need a deliberate upgrade (new PS3.15
confidentiality profile editions, upstream bug fixes).

1. **Read the upstream changelog** for the target version, specifically for:
   - changes to the default (`dicomfields_2023`) rule table -- this plugin
     does not override `base_rules_gen`, so any change to the default table
     changes what gets redacted (see `README.md` → *Confidentiality profile
     edition*);
   - changes to the `-t` / dictionary tag-argument parsing or the
     `replace_with_value` / `regexp` action option names -- this plugin's
     `_build_actions()` in `dicom_anonymize.py` mirrors that surface by hand
     and will silently drift if upstream renames an option key (this is
     exactly the `"pattern"` vs `"find"` class of bug -- see git history).
2. Bump the pin in `requirements.txt`.
3. Rebuild the dev image and re-run the full test suite (`pytest -v`,
   see `README.md` → *Testing*) -- do not upgrade and skip this step, even
   for a patch release. `tests/test_dictionary.py` and
   `tests/test_phi_removal.py` in particular assert on exact upstream output
   values (e.g. the literal string `"ANONYMIZED"` that
   `replace` produces) that only upstream's source defines; if upstream
   changes that string, the test failure is the signal to update
   `README.md`'s documented examples too, not just the assertion.
4. Re-check every dictionary/tag example in `README.md` still parses and
   runs -- `ast.literal_eval` accepting a given tag string, and the action
   option names it expects, are both upstream contract, and both have
   drifted silently in the past (this is why `tests/test_dictionary.py`
   exists at all; if you add a new documented example, add a test that
   exercises it verbatim).
5. Regenerate the SBOM and re-copy license files (below) -- `pydicom` and
   `tqdm` are pulled in transitively by `dicom-anonymizer`, so their pinned
   versions can change even though they're not listed directly in
   `requirements.txt`.
6. Bump `__version__` in `dicom_anonymize.py` (this is what `setup.py`,
   `--version`, and the ChRIS plugin metadata all read from) -- see
   *Versioning* below.

## Upgrading `pydicom` or `chris_plugin`

Same procedure, steps 2-3 and 5-6 above. `pydicom` major-version bumps
occasionally change default VR/encoding handling; re-run
`tests/test_dates.py`, `tests/test_uid_consistency.py`, and
`tests/test_private_tags.py` with particular attention, since they assert on
specific element values pydicom produces.

## Upgrading the base image

`Dockerfile`'s `FROM docker.io/python:3.12.1-slim-bookworm` is pinned to an
exact patch tag rather than a minor-version floor. Bump it deliberately,
rebuild, and re-run the full suite -- Debian point releases can change
system OpenSSL/libc behavior that pydicom's C extensions depend on.

## Versioning

`__version__` in `dicom_anonymize.py` is the single source of truth (see
`setup.py`'s `get_version()`); it's what `-V`/`--version` and
`--upstreamVersion` print, and what CI tags the published image and
uploaded ChRIS plugin descriptor with. Bump it for **any** change that
alters runtime behavior, including a dependency upgrade that changes what
gets redacted -- an unchanged version string on a behavior change makes a
ChRIS run un-reproducible, since the version string is the only thing a
downstream pipeline records.

## Regenerating the SBOM

The SBOM (`sbom.cdx.json`, CycloneDX JSON) must reflect the actual installed
runtime closure, not just the three lines in `requirements.txt` -- `pydicom`
and `tqdm` are transitive and won't show up if you generate it by parsing
`requirements.txt` as text.

```bash
python3 -m venv /tmp/clean-venv
/tmp/clean-venv/bin/pip install -r requirements.txt
pip install cyclonedx-bom  # into your own environment, not the clean one
cyclonedx-py environment /tmp/clean-venv \
    --output-format json --output-file sbom.cdx.json
```

Then manually strip the `pip` component itself (it's a build tool, not a
runtime dependency of the shipped image) and confirm every component's
`licenses` field is populated -- `cyclonedx-py` occasionally can't resolve a
package's license from its metadata (this happened for `tqdm`; its license
had to be filled in by hand from its `dist-info/licenses/LICENCE` file, not
left blank). Update `NOTICES.md`'s table and `third_party_licenses/` to
match afterwards.

## Re-checking CI after any of the above

`.github/workflows/ci.yml`'s `test` job builds the image with
`extras_require=dev` and runs `pytest` **inside** that image, against the
exact pinned dependencies that ship -- not against whatever happens to be on
the runner. A green run there is the actual gate; running `pytest` locally
against a different environment is a useful sanity check but not a
substitute. 
