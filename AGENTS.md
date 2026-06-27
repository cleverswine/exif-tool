# AGENTS.md

## Project summary
This repository contains a Python command-line tool that scans a source tree of photos and videos, derives a date from embedded EXIF metadata or from filenames/directories, and copies files into a destination tree organized by year and month.

The repository already contains reference material in README.md and exif_date_organizer.py, but this file is intended to guide a coding agent creating the application from scratch.

## Goal
Create a small, maintainable Python CLI that:
- scans a source directory recursively
- recognizes supported media files
- reads EXIF timestamps with exiftool
- derives fallback dates from filename or path patterns when EXIF metadata is missing
- copies files into a destination structure like DEST/YYYY/MM/filename
- logs actions to a tab-separated log file
- supports dry-run mode, batch processing, and unsupported-file handling

## Expected behavior
The implementation should preserve the behavior described in README.md and the existing script:
- use Python 3
- require exiftool to be installed and available on PATH
- support these CLI options:
  - --source
  - --dest
  - --log
  - --dry-run
  - --limit
  - --batch-size
  - --verbose
  - --copy-unsupported
- create destination folders as needed
- avoid modifying the source tree
- write logs with source, EXIF values, derived timestamp, destination, status, and reason
- place files with unknown dates into an unknown_date folder
- copy unsupported files into unsupported_ext when requested
- handle destination collisions safely by renaming copies when needed

## Recommended architecture
Implement the tool as a single Python script with a small object-oriented structure:
- ExifDateOrganizer: top-level orchestration
- file discovery and filtering
- EXIF metadata collection using exiftool
- timestamp derivation logic
- destination path generation
- execution and logging

Suggested module layout:
- exif_date_organizer.py: all implementation in one file for simplicity

## Implementation plan
1. Create the CLI entrypoint
   - parse arguments with argparse
   - expand user paths and resolve them
   - set defaults that match the current README behavior

2. Implement file discovery
   - recursively walk the source folder
   - filter to supported extensions
   - record unsupported extensions separately

3. Implement EXIF metadata reading
   - call exiftool in batches for performance
   - fall back to single-file reads if batch reading fails
   - normalize EXIF date values into a consistent format

4. Implement timestamp derivation
   - prefer embedded EXIF date values when present
   - otherwise derive from filename stem and parent directory names
   - use the first valid date found, with future dates rejected
   - support year/month/day patterns and compact date formats

5. Implement destination planning
   - build destination paths as DEST/YYYY/MM/filename
   - use unknown_date for files with no usable timestamp
   - use unsupported_ext for unsupported files when requested

6. Implement copy and metadata update logic
   - copy files to their planned destinations
   - skip identical files if a destination already exists
   - resolve collisions by appending numeric suffixes
   - update embedded timestamps for copied files when a derived timestamp is available

7. Implement logging and reporting
   - write a header row to the log file if it does not exist
   - append one line per action with tab-separated fields
   - print verbose summaries and per-file actions when requested

## Important implementation details
- Use exiftool for all EXIF reads and writes.
- Keep the source tree read-only; only copies should be modified.
- When timestamp derivation fails, the tool should place the file in unknown_date and explain why.
- Avoid hard-coding private paths; use command-line arguments and defaults.
- Preserve a clear distinction between supported files, unsupported extensions, and files with metadata errors.
- Prefer simple, readable code over clever abstractions.

## Validation checklist
A completed implementation should be able to:
- run with --help successfully
- process a small dry-run sample with --dry-run --verbose --limit 10
- create a destination tree and log file in a test directory
- preserve the expected folder structure and unknown-date fallback behavior

## Suggested verification commands
Run these after implementation:
```bash
python3 exif_date_organizer.py --help
python3 exif_date_organizer.py --source /tmp/sample-source --dest /tmp/sample-dest --dry-run --verbose --limit 10
```

## Notes for the agent
- The existing script in exif_date_organizer.py is a reference implementation; use it as a behavior guide, but feel free to simplify or refactor if the result is clearer.
- If a requirement is ambiguous, prefer the behavior described in README.md and the existing script over inventing new semantics.
- Keep the implementation robust to missing EXIF metadata and file-system edge cases.
