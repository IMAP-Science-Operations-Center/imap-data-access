# Dependency YAML format

The YAML files in this folder define every processing job in the IMAP Science
Data Center (SDC): what each job reads, what it writes, and how its runs are
split up in time. There is one file per instrument. This page is the reference
for their format.

## This format is a contract

These files and the code that reads them ship together in each
`imap-data-access` release, so the package version is also the format version.
There's no separate schema version.

`sds-data-manager`, which runs the SDC processing pipeline, relies on three
things:

- **The file location:**
  `imap_data_access/dependencies/config_files/imap_<instrument>_dependencies.yaml`.
  At deploy time, `sds-data-manager` compares these files with the ones from the
  release it deployed last time, which it reads from that older release at this
  path. Moving or renaming the folder or the files breaks that comparison until
  `sds-data-manager` learns both layouts.
- **The fields and their meanings,** as described on this page.
- **The SPICE sources,** which must match the SPICE kernel types that
  `sds-data-manager` knows about. A test there checks this.

A pull request that changes the format must update this page, and needs a
matching change in `sds-data-manager`. A change to the files themselves takes
effect only once it's in an `imap-data-access` release and `sds-data-manager`
has been updated to that release.

## Checking a change

From the root of your checkout, run:

```bash
python -m imap_data_access.dependencies.validation
pytest tests/dependencies
```

The first command checks the major versions (see [Validation](#validation)).
The second loads every file with the reader and runs the unit tests. Both also
run on every pull request.

## Files

Each instrument has one file, named `imap_<instrument>_dependencies.yaml`. The
instruments are codice, glows, hi, hit, idex, lo, mag, spacecraft, swapi, swe
and ultra. The reader raises an error if any of these files is missing. It
ignores `ialirt` and `l1const`, which have no processing jobs.

The jobs in a file belong to that file's instrument.

## Structure

Each top-level key in a file is either a job or a shared group of inputs.

- **A job** has a key in parentheses, `(<data_type>, <descriptor>)`, such as
  `(l1b, sci)`. Together with the file's instrument, that names the job, for
  example `(swe, l1b, sci)`.
- **Any other top-level key** isn't a job. The reader skips it. These keys hold
  shared groups of inputs; see [Shared input groups](#shared-input-groups).

A key that's meant to be a job but doesn't start with `(`, such as `l1b, sci:`,
is skipped silently, so check the parentheses.

A job's descriptor can't contain a comma, because the reader splits the key on
commas.

```yaml
(l1b, sci):
  partition: daily
  inputs:
    - source: swe
      data_type: l1a
      descriptor: sci
    - source: swe
      data_type: ancillary
      descriptor: esa-lut
    - source: leapseconds
      data_type: spice
      descriptor: historical
      trigger_job: false
  outputs:
    - source: swe
      data_type: l1b
      descriptor: sci
      major_version: 1
```

### Job fields

| Field | Required | Meaning |
|---|---|---|
| `partition` | Yes | How the job's runs are split up in time. See [Partitions](#partitions). |
| `inputs` | Yes | The products and files the job reads. A list of entries, described below. |
| `outputs` | Yes | The products the job writes. A list of entries, described below. At least one output must have the job's own data type. |

### Entry fields

Inputs and outputs use the same fields. Some fields apply only to one of them.

| Field | Required | Default | Meaning |
|---|---|---|---|
| `source` | Yes | | Where the data comes from: an instrument, or a kind of SPICE, spin or repoint data. See [source](#source). |
| `data_type` | Yes | | The data level, or the kind of non-science data. See [data_type](#data_type). |
| `descriptor` | Yes | | Which product, as in its file names. See [descriptor](#descriptor). |
| `required` | No | `true` for inputs, `false` for outputs | Inputs only: whether the job can't run without this input. See [required](#required). |
| `trigger_job` | No | `true` | Inputs only: whether a new file of this input starts the job. See [trigger_job](#trigger_job). |
| `date_range` | No | none | Inputs only: how far before or after the job's time window to look for this input. See [date_range](#date_range). |
| `major_version` | Outputs: yes | | Outputs only: the major version of the output's files. See [major_version](#major_version). |

The reader checks `source`, `data_type`, `descriptor`, `required`,
`trigger_job` and `date_range` whenever it loads a file, and raises an error
that names the job. It doesn't check `partition` or `major_version`.

#### source

One of:

- an instrument: codice, glows, hi, hit, ialirt, idex, l1const, lo, mag,
  spacecraft, swapi, swe or ultra
- `spin`, `repoint` or `spice`
- a SPICE kernel type: leapseconds, planetary_constants, imap_frames,
  science_frames, spacecraft_clock, earth_attitude, planetary_ephemeris,
  ephemeris_reconstructed, ephemeris_predicted, ephemeris_nominal,
  ephemeris_90days, attitude_history, pointing_attitude, lo_pivot_attitude,
  spin and thruster

The instruments come from `imap_data_access.VALID_INSTRUMENTS`, and the SPICE
kernel types from `imap_data_access.dependencies.SPICE_SOURCES`, in metakernel
load order. Adding a kernel type takes a change both here and in
`sds-data-manager`.

#### data_type

One of:

- a data level from `imap_data_access.VALID_DATALEVELS`: l0, l1, l1a, l1b, l1c,
  l1ca, l1cb, l1d, l2, l2a, l2b, l2c, l3, l3a, l3b, l3c, l3d or l3e
- `ancillary`, `spice`, `spin` or `repoint`
- `collection`, which the reader accepts but no file uses

The pipeline handles each input according to its kind. The first rule that
matches decides:

1. `source: repoint` is the job's repoint input.
2. `data_type: spice` is a SPICE input. The pipeline picks its files by `source`.
3. `data_type: spin` is the job's spin input.
4. `data_type: ancillary` is an ancillary input.
5. Anything else is a science input.

A job has at most one spin input and one repoint input. If there are more, the
last one wins.

#### descriptor

A non-empty string.

- **Science and ancillary data:** the descriptor in the product's file names,
  for example `sci` or `esa-lut`. File names use underscores to separate their
  parts, so a descriptor can't contain one.
- **SPICE inputs:** the files use `historical`, or `best` for some ephemeris
  inputs.
- **Spin and repoint inputs:** the files use `historical`.

#### required

For inputs, `true` (the default) means the job doesn't run until this input's
files are found for its time window. `false` means the job runs without them.

In `sds-data-manager` today, `required: false` has no effect on SPICE inputs: a
missing SPICE kernel type always holds the job back. Outputs default to `false`,
and the pipeline doesn't use the value.

#### trigger_job

For inputs, `true` (the default) means a new file of this input starts the job.
`false` means the job uses the input's files but doesn't start because one
arrives. That suits inputs that change rarely or are only needed alongside
others, such as leapseconds and spacecraft clock kernels.

`trigger_job` also affects reprocessing after a major version change; see
[major_version](#major_version).

#### date_range

A list of one or two strings, `[past]` or `[past, future]`. Each string is a
whole number followed by a unit:

| Unit | Meaning |
|---|---|
| `d` | days |
| `h` | hours |
| `p` | pointings |
| `l` | last processed |
| `nd` | nearest days, counted from the job's window |
| `np` | nearest pointings, counted from the job's window |

The reader enforces these rules:

- `past` must be zero or negative, and `future` zero or positive. For example
  `["-3d", "5d"]`, `["-2h", "2h"]`, `["-3p", "3p"]` or `["-1l"]`.
- `nd` and `np` count files rather than measure time, so they come alone, with
  no future: `["6np"]` or `["6nd"]`.
- A list with more than two strings, or a string with any other unit, is an
  error.

Without `date_range`, the pipeline looks for files of the input that overlap
the job's own time window, as set by its partition.

Support for `date_range` in `sds-data-manager` is limited today. The only value
in use is `["8np"]`, on the Hi goodtimes jobs, and a Hi-specific rule in
`sds-data-manager` implements it. Check with the SDC before using any other
value.

#### major_version

Outputs only. A whole number from 0 to 999, which becomes the major part of
the output files' version, `v<major>.<minor>`, such as `v002.0001`. The
pipeline chooses the minor part. Inputs don't have a major version.

Increase it when a change in processing should replace a product's existing
files across the whole mission. When `sds-data-manager` deploys, it compares
these files with the ones from its last deploy. If a job is new, has a new
output, or has an output whose major version went up, it reprocesses the whole
mission from 2025-09-24 to the deploy date.

Reprocessing starts at the furthest-upstream job that changed in that
instrument's pipeline, and the reprocessed files then trigger everything
downstream. Only science inputs from the same instrument with
`trigger_job: true` lead upstream.

A major version that goes down isn't detected and doesn't reprocess anything,
so don't lower one.

##### Validation

`python -m imap_data_access.dependencies.validation` walks each instrument's
pipeline from its first jobs, the ones that read the instrument's `l0` `raw`
data. It reports an error for these problems, and the pull request check fails:

- Two outputs of a job share a descriptor but have different major versions.
- None of a job's outputs has the job's own data type.

It logs a warning, but doesn't fail, when an output has a lower major version
than the same instrument's output that it's made from.

From each first job, it follows every output to the jobs of the same instrument
that read it, and checks only the jobs it reaches. Jobs that aren't downstream
of a first job aren't checked: for example, jobs that read no science data, and
the jobs that read their outputs.

### Partitions

`partition` sets the time window that each run of the job covers, and so the
time span of the files it writes. For any file,
`imap_data_access.dependencies.nominal_coverage()` returns that window. The
reader doesn't check the value, but `sds-data-manager` only knows these:

| Value | Each run covers |
|---|---|
| `daily` | one day |
| `repoint` | one pointing |
| `10d` | one IDEX 10-day window, from `idex_10_day_CDF_names.csv` in this folder |
| `3mo`, `6mo`, `1yr` | one ENA map window. 3-month windows start on December 25, March 25, June 25 and September 25, 6-month windows on December 25 and June 25, and 1-year windows on December 25. See `imap_data_access/dependencies/map_windows.py`. |
| `pointing_attitude` | the whole pointings covered by one attitude history kernel. Only the spacecraft job that makes pointing-attitude kernels uses it. |

## Shared input groups

Most jobs share inputs such as the basic SPICE kernels. A file can define a
group of inputs once, under a top-level key that isn't a job, and reuse it with
YAML anchors. `&name` names the group, and `*name` inserts it. A group can
include another group.

```yaml
spice_basic: &spice_basic
  - source: leapseconds
    data_type: spice
    descriptor: historical
    trigger_job: false
  - source: spacecraft_clock
    data_type: spice
    descriptor: historical
    trigger_job: false

spice_l1b: &spice_l1b
  - *spice_basic
  - source: imap_frames
    data_type: spice
    descriptor: historical
    trigger_job: false

(l1b, 45sensor-de):
  partition: repoint
  inputs:
    - *spice_l1b
    - source: hi
      data_type: l1a
      descriptor: 45sensor-de
  outputs:
    - source: hi
      data_type: l1b
      descriptor: 45sensor-de
      major_version: 1
```

The reader flattens nested groups in order. This job's inputs are leapseconds,
spacecraft_clock, imap_frames, and then hi l1a 45sensor-de.

## The IDEX 10-day window file

`idex_10_day_CDF_names.csv` defines the IDEX 10-day windows used by the `10d`
partition, one row per window. Its columns are `start_date` and `end_date`, as
`YYYYMMDD`, and `doy`, the window's day of year. Each window's start date must
be unique. `sds-data-manager` reads it through
`imap_data_access.dependencies.IDEX_10_DAY_RANGES_PATH`.

## Format history

| imap-data-access version | Change |
|---|---|
| 1.4.0.dev0 | The files moved here from `sds-data-manager`, unchanged. |

If an incompatible format change is ever needed, a top-level `schema_version`
key could mark it. Readers in earlier releases skip top-level keys that aren't
in parentheses, so adding one doesn't break them.
