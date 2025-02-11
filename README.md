# IMAP Data Access Package
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-6-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

This lightweight  Python package allows users to download, query, and upload data from the IMAP Science Data Center (SDC).

For more information see the [detailed instructions](https://imap-processing.readthedocs.io/en/latest/data-access/index.html).

## Command Line Utility

### To install

```bash
pip install imap-data-access
imap-data-access -h
```

### Base Command Arguments
```bash
$ imap-data-access query # or
$ imap-data-access download # or
$ imap-data-access upload
```
Add the '-h' help flag with any base command for more information

### Query / Search for data

Find all files from the SWE instrument

```bash
$ imap-data-access query --instrument swe
Found [3] matching files
|-----------------------------------------------------------------------------------------------------------------------------------|
| Instrument | Data Level | Descriptor      | Start Date | Repointing | Version | Filename                                          |
|-----------------------------------------------------------------------------------------------------------------------------------|
| swe        | l0         | raw             | 20240510   |            | v022    | imap_swe_l0_raw_20240510_v022.pkts                |
| swe        | l1a        | sci             | 20240510   |            | v022    | imap_swe_l1a_sci_20240510_v022.cdf                |
| swe        | l1b        | sci             | 20240510   |            | v022    | imap_swe_l1b_sci_20240510_v022.cdf                |
|-----------------------------------------------------------------------------------------------------------------------------------|
```

Find all files during the year 2024 and return the response as raw json

```bash
$ imap-data-access query --start-date 20240101 --end-date 20241231 --output-format json
[{'file_path': 'imap/swe/l0/2024/01/imap_swe_l0_sci_20240105_v001.pkts', 'instrument': 'swe', 'data_level': 'l0', 'descriptor': 'sci', 'start_date': '20240105', 'version': 'v001', 'extension': 'pkts'}, {'file_path': 'imap/swe/l0/2024/01/imap_swe_l0_sci_20240105_v001.pkts', 'instrument': 'swe', 'data_level': 'l0', 'descriptor': 'sci', 'start_date': '20240105', 'version': 'v001', 'extension': 'pkts'}]
```

### Download a file

Download a level 0 SWE file on 2024/01/05

> [!NOTE]
> Make sure the directory configuration is correct, see the [Data Directory section](https://github.com/IMAP-Science-Operations-Center/imap-data-access#data-directory) for more information.

```bash
$ imap-data-access download imap/swe/l0/2024/01/imap_swe_l0_sci_20240105_v001.pkts
Successfully downloaded the file to: <IMAP_DATA_DIR>/imap/swe/l0/2024/01/imap_swe_l0_sci_20240105_v001.pkts
```

### Upload a file

Upload a l1a file after decoding the l0 CCSDS ".pkts" file

```bash
$ imap-data-access upload /imap/swe/l1a/2024/01/imap_swe_l1a_sci_20240105_v001.cdf
Successfully uploaded the file to the IMAP SDC
```

## Importing as a package

```python
import imap_data_access

# Search for files
results = imap_data_access.query(instrument="mag", data_level="l0")
# results is a list of dictionaries
# [{'file_path': 'imap/swe/l0/2024/01/imap_swe_l0_sci_20240105_v001.pkts', 'instrument': 'swe', 'data_level': 'l0', 'descriptor': 'sci', 'start_date': '20240105','version': 'v001', 'extension': 'pkts'}, {'file_path': 'imap/swe/l0/2024/01/imap_swe_l0_sci_20240105_v001.pkts', 'instrument': 'swe', 'data_level': 'l0', 'descriptor': 'sci', 'start_date': '20240105', 'version': 'v001', 'extension': 'pkts'}]

# Download a file that was returned from the search
imap_data_access.download("imap/mag/l0/2024/01/imap_mag_l0_raw_202040101_v001.pkts")

# Upload a calibration file that exists locally
imap_data_access.upload("imap/swe/l1a/2024/01/imap_swe_l1a_sci_20240105_v001.cdf")
```

## Configuration

### Data directory

The folder structure for data files within the IMAP SDC is rigidly
defined, so the data access will mimic that structure to make sure
all data is stored in the same heirarchical structure as the SDC.
This will enable seamless transition between a user's local system
and the SDC. This is only used for downloads.

A user's root data location can be specified as an environment
variable ``IMAP_DATA_DIR`` or through a configuration dictionary
within the package itself ``imap_data_access.config["DATA_DIR"]``.
If the ``IMAP_DATA_DIR`` variable is not set, the program defaults
to the user's current working directory + ``data/``.

The following is the directory structure the IMAP SDC uses.

```text
<IMAP_DATA_DIR>/
  imap/
    <instrument>/
      <data_level>/
        <year>/
          <month>/
            <filename>
```

for example, with ``IMAP_DATA_DIR=/data``:

```text
/data/
  imap/
    swe/
      l0/
        2024/
          01/
            imap_swe_l0_sci_20240105_v001.pkts
```

### Data Access URL

To change the default URL that the package accesses, you can set
the environment variable ``IMAP_DATA_ACCESS_URL`` or within the
package ``imap_data_access.config["DATA_ACCESS_URL"]``. The default
is the development server ``https://api.dev.imap-mission.com``.

## Troubleshooting

### Network issues

#### SSL

If you encounter SSL errors similar to the following:

```text
urllib.error.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:997)>
```

That generally means the Python environment you're using is not finding your system's root
certificates properly. This means you need to tell Python how to find those certificates
with the following potential solutions.

1. **Upgrade the certifi package**

    ```bash
    pip install --upgrade certifi
    ```

2. **Install system certificates**
    Depending on the Python version you installed the program with the command will look something like this:

    ```bash
    /Applications/Python\ 3.10/Install\ Certificates.command
    ```

#### HTTP Error 502: Bad Gateway

This could mean that the service is temporarily down. If you
continue to encounter this, reach out to the IMAP SDC at
<imap-sdc@lasp.colorado.edu>.

#### FileNotFoundError

This could mean that the local data directory is not set
up with the same paths as the SDC. See the [data directory](#data-directory)
section for an example of how to set this up.

## File Validation

This package validates filenames and paths to check they follow our standards, as defined by the filename conventions. There is also a class available for
use by other packages to create filepaths and filenames that follow the IMAP SDC conventions.

To use this class, use `imap_data_access.ScienceFilePath`.

Usage:

```python

science_file = imap_data_access.ScienceFilePath("imap_swe_l0_sci_20240101_v001.pkts")

# Filepath = /imap/swe/l0/2024/01/imap_swe_l0_sci_20240101_v001.pkts
filepath = science_file.construct_path()
```

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="http://greglucas.github.io"><img src="https://avatars.githubusercontent.com/u/12417828?v=4?s=100" width="100px;" alt="Greg Lucas"/><br /><sub><b>Greg Lucas</b></sub></a><br /><a href="https://github.com/IMAP-Science-Operations-Center/imap-data-access/commits?author=greglucas" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/bourque"><img src="https://avatars.githubusercontent.com/u/2250769?v=4?s=100" width="100px;" alt="Matthew Bourque"/><br /><sub><b>Matthew Bourque</b></sub></a><br /><a href="https://github.com/IMAP-Science-Operations-Center/imap-data-access/commits?author=bourque" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/maxinelasp"><img src="https://avatars.githubusercontent.com/u/117409426?v=4?s=100" width="100px;" alt="Maxine Hartnett"/><br /><sub><b>Maxine Hartnett</b></sub></a><br /><a href="https://github.com/IMAP-Science-Operations-Center/imap-data-access/commits?author=maxinelasp" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/mfacchinelli"><img src="https://avatars.githubusercontent.com/u/19731497?v=4?s=100" width="100px;" alt="Michele Facchinelli"/><br /><sub><b>Michele Facchinelli</b></sub></a><br /><a href="https://github.com/IMAP-Science-Operations-Center/imap-data-access/commits?author=mfacchinelli" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/anamanica"><img src="https://avatars.githubusercontent.com/u/171708990?v=4?s=100" width="100px;" alt="anamanica"/><br /><sub><b>anamanica</b></sub></a><br /><a href="https://github.com/IMAP-Science-Operations-Center/imap-data-access/commits?author=anamanica" title="Documentation">📖</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/daralynnrhode"><img src="https://avatars.githubusercontent.com/u/143308810?v=4?s=100" width="100px;" alt="Daralynn Rhode"/><br /><sub><b>Daralynn Rhode</b></sub></a><br /><a href="https://github.com/IMAP-Science-Operations-Center/imap-data-access/commits?author=daralynnrhode" title="Documentation">📖</a> <a href="https://github.com/IMAP-Science-Operations-Center/imap-data-access/commits?author=daralynnrhode" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!
