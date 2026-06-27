# exif tag editor

This repository now contains a working Python CLI that organizes media files by derived date using exiftool. The implementation has evolved beyond the original task list, so the guidance below reflects the current behavior of the code.

## Current implementation summary

- The tool is implemented in exif_date_organizer.py as a single-file CLI.
- It scans a source tree recursively, copies supported files into a destination tree organized as DEST/YYYY/MM/filename, and leaves the source tree unchanged.
- It uses exiftool to read DateTimeOriginal, CreateDate, and ModifyDate values and to update timestamps on copied files.
- It derives fallback timestamps from filename or directory names when EXIF metadata is missing or incomplete.

## Behavior now implemented

- CLI options:
  - --source
  - --dest
  - --log
  - --dry-run
  - --limit
  - --batch-size
  - --verbose
  - --copy-unsupported
- Defaults:
  - source: ~/Pictures/
  - dest: ~/Pictures_Organized/
  - log: exif_date_organizer.log inside the destination folder
- Dry-run mode logs planned actions and prints them without copying or modifying files.
- Unsupported extensions are skipped by default; they can be copied into unsupported_ext under the destination when --copy-unsupported is used.
- Files with no usable date are placed in unknown_date with a path-prefixed filename.
- Existing destination files are skipped if identical; otherwise collisions are resolved by appending numeric suffixes.
- Batch metadata reads and writes use exiftool; if batch operations fail, the script falls back to single-file reads and writes.
- The log file is tab-separated and includes source, EXIF values, derived timestamp, destination, status, and reason.

## Implementation notes for future work

- Keep behavior aligned with README.md and the current script.
- Prefer a simple object-oriented structure, but avoid over-engineering.
- Use argparse, pathlib, subprocess, shutil, and datetime for the core implementation.
- Keep exiftool as an explicit dependency and validate that it is available on PATH.
- Avoid changing the source tree; only copied files in the destination may be modified.

## Differences from the earlier instructions

- This implementation is copy-based rather than move-based.
- The destination layout is DEST/YYYY/MM/filename rather than a single folder under /home/knoone/Pictures/.
- Default paths are now user-home based instead of hard-coded SMB paths.
- Unknown-date handling uses unknown_date plus prefixed filenames.
- Unsupported files are explicitly handled and logged.
- Collision handling and identical-file skipping are implemented.
- --copy-unsupported is part of the CLI.
