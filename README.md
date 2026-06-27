# Exif Date Organizer

`exif_date_organizer.py` is a Python utility for organizing photo and video files by date using embedded EXIF metadata and derived timestamps from filenames or directory paths.

run notes:

python3 exif_date_organizer.py --source /mnt/smb/cloud_backup/Archive/Larry/ --dest ~/Pictures_Organized --verbose

python3 exif_date_organizer.py --source /mnt/smb/cloud_backup/Pictures/ --dest ~/Pictures_Organized --copy-unsupported --verbose

python3 exif_date_organizer.py --source /mnt/smb/cloud_backup/Videos/ --dest ~/Pictures_Organized --copy-unsupported --verbose


## Features

- Recursively scans a source folder for supported media files
- Uses `exiftool` to read EXIF date fields:
  - `DateTimeOriginal`
  - `CreateDate`
  - `ModifyDate`
- Derives dates from filenames or folder names when EXIF metadata is missing
- Copies files into `DEST/YYYY/MM/` folders
- Supports dry-run mode and verbose logging
- Writes a tab-separated log file describing each action
- Tracks unsupported files and unknown dates

## Requirements

- Python 3
- `exiftool` installed and available on `PATH`

## Supported file extensions

The script currently targets common image, RAW, and video formats that ExifTool can read with EXIF metadata, including:

- `.jpg`, `.jpeg`, `.jpe`, `.jpx`, `.png`, `.heic`, `.heif`, `.hif`, `.webp`, `.tif`, `.tiff`
- `.cr2`, `.cr3`, `.crw`, `.nef`, `.nrw`, `.arw`, `.rw2`, `.orf`, `.ori`, `.dng`, `.raf`, `.sr2`, `.srf`, `.srw`, `.pef`, `.x3f`, `.iiq`, `.fff`, `.mef`, `.3fr`
- `.mov`, `.mp4`, `.m4v`, `.avi`, `.mkv`, `.3gp`, `.3g2`, `.3gpp`, `.qt`, `.qtif`
- `.psd`, `.psb`, `.pdf`, `.xmp`, `.exif`, `.thm`

## Usage

```bash
python3 exif_date_organizer.py --source /path/to/source --dest /path/to/dest --log /path/to/logfile.log
```

### Common options

- `--source`: Source root folder to scan (default: `~/Pictures/`)
- `--dest`: Destination root folder for organized files (default: `~/Pictures_Organized/`)
- `--log`: Log file path (default: `exif_date_organizer.log` inside destination folder)
- `--dry-run`: Simulate actions without copying or modifying files
- `--limit`: Limit number of files processed in dry-run mode (default: `500`)
- `--batch-size`: Number of files per ExifTool batch (default: `300`)
- `--verbose`: Print summary and planned actions to console
- `--copy-unsupported`: Copy unsupported files into `unsupported_ext/` under the destination. If you omit this flag, unsupported files are skipped and only logged.

## Examples

Dry run with verbose output:

```bash
python3 exif_date_organizer.py --source ~/Pictures --dest ~/Pictures_Organized --dry-run --verbose
```

Run for real and save logs:

```bash
python3 exif_date_organizer.py --source ~/Pictures --dest ~/Pictures_Organized --log ~/Pictures_Organized/exif_date_organizer.log
```

Process a smaller test set:

```bash
python3 exif_date_organizer.py --source ~/Pictures/Test --dest ~/Pictures_Organized/Test --dry-run --limit 100
```

Copy unsupported files into the fallback folder:

```bash
python3 exif_date_organizer.py --source ~/Pictures --dest ~/Pictures_Organized --copy-unsupported
```

## Log format

The log is tab-separated and includes:

- `source`: original file path
- `exif_datetime`: embedded EXIF fields
- `derived_timestamp`: final timestamp used for destination path
- `destination`: copied file path or target location
- `status`: `copied`, `dry-run`, `unsupported`, or `error`
- `reason`: explanation for derived dates or unsupported files

## Notes

- Unsupported files and files that fail EXIF metadata reads are recorded in the log.
- By default, they are skipped; use `--copy-unsupported` to copy them into `unsupported_ext/` under the destination folder.
- **Supported files with unknown timestamps or errors** are placed in `unknown_date/` with their relative source path prepended to the filename (with `/` replaced by `_`). For example:
  - File: `source/Archive/2020/photo.jpg` → `dest/unknown_date/Archive_2020_photo.jpg`
  - Files with errors are prefixed with `ERROR_` for easy identification
- When a destination file already exists, the script compares the files using MD5 hash:
  - If identical, the file is skipped and logged as "skipped"
  - If different, a collision is resolved by renaming the destination (appending `_1`, `_2`, etc.)
- `exiftool` must be installed separately; the script will fail if it is not available.
