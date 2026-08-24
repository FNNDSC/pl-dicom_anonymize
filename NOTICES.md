# Third-Party Notices

This plugin (`dicom_anonymize`, MIT-licensed, see `LICENSE`) is built on the
following third-party packages, redistributed inside the built container
image under their respective licenses. Full license texts are in
[`third_party_licenses/`](./third_party_licenses).

| Package            | Version        | License        | Upstream                                              | Full text                                                             |
|---------------------|----------------|-----------------|--------------------------------------------------------|-------------------------------------------------------------------------|
| `dicom-anonymizer`  | `1.0.13.post1` | BSD-3-Clause    | https://github.com/KitwareMedical/dicom-anonymizer      | [`third_party_licenses/dicom_anonymizer.LICENSE`](./third_party_licenses/dicom_anonymizer.LICENSE) |
| `pydicom`           | `2.4.5`        | MIT             | https://github.com/pydicom/pydicom                       | [`third_party_licenses/pydicom.LICENSE`](./third_party_licenses/pydicom.LICENSE)                     |
| `chris_plugin`      | `0.4.0`        | MIT             | https://github.com/FNNDSC/chris_plugin                   | [`third_party_licenses/chris_plugin.LICENSE`](./third_party_licenses/chris_plugin.LICENSE)           |
| `tqdm`              | `4.70.0`       | MPL-2.0 AND MIT | https://github.com/tqdm/tqdm                             | [`third_party_licenses/tqdm.LICENSE`](./third_party_licenses/tqdm.LICENSE)                           |

`tqdm` and `pydicom` are pulled in transitively by `dicom-anonymizer` and are
not listed directly in `requirements.txt`; their exact pinned versions are
recorded in the SBOM (`sbom.cdx.json`), not just this table, since a
transitive version can change between releases of `dicom-anonymizer` even
when this table isn't touched. Regenerate both together — see
[`MAINTENANCE.md`](./MAINTENANCE.md).

This list covers the plugin's own Python runtime dependencies only. It does
not cover the base container image (`python:3.12.1-slim-bookworm` and its
Debian package set); consult that image's own notices for OS-level
components.
