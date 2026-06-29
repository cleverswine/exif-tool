#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import namedtuple
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SUPPORTED_EXTENSIONS = {
    ".3fr", ".3g2", ".3gp", ".3gpp", ".aax", ".ai", ".ait", ".arq", ".arw", ".avi",
    ".avif", ".cr2", ".cr3", ".crm", ".crw", ".dcp", ".dng", ".erf", ".exif", ".exr",
    ".fff", ".heic", ".heif", ".hif", ".iiq", ".insp", ".j2c", ".j2k", ".jpc", ".jp2",
    ".jpe", ".jpeg", ".jpf", ".jph", ".jpg", ".jpm", ".jpx", ".jxl", ".m4a", ".m4b",
    ".m4p", ".m4v", ".mef", ".mie", ".mov", ".mp4", ".mpo", ".mqv", ".mrw", ".nef",
    ".nrw", ".orf", ".ori", ".pef", ".png", ".psb", ".psd", ".qt", ".qtif",
    ".raf", ".rw2", ".rwl", ".sr2", ".srf", ".srw", ".thm", ".tif", ".tiff", ".webp",
    ".x3f", ".xcf",
}

DATE_YEAR_MIN = 1990
DATE_YEAR_MAX = datetime.now().year

ExifMetadata = namedtuple("ExifMetadata", ["source_file", "datetime_original", "create_date", "modify_date"])

DATE_PATTERNS = [
    # Full dates with separators: YYYY-MM-DD, YYYY_MM_DD, YYYY.MM.DD, YYYY MM DD
    re.compile(r"(?P<year>19\d{2}|20\d{2}|2026)[-_\. ](?P<month>0?[1-9]|1[0-2])[-_\. ](?P<day>0?[1-9]|[12][0-9]|3[01])"),
    # Compact full dates: YYYYMMDD
    re.compile(r"(?P<year>19\d{2}|20\d{2}|2026)(?P<month>0[1-9]|1[0-2])(?P<day>0[1-9]|[12][0-9]|3[01])"),
    # MM-DD-YYYY / MM.DD.YYYY / MM_DD_YYYY
    re.compile(r"(?P<month>0?[1-9]|1[0-2])[-_\. ](?P<day>0?[1-9]|[12][0-9]|3[01])[-_\. ](?P<year>19\d{2}|20\d{2}|2026)"),
    # MM-DD-YY_
    re.compile(r"(?P<month>0?[1-9]|1[0-2])-(?P<day>0?[1-9]|[12][0-9]|3[01])-(?P<year>\d{2})_"),
    # space M-DD-YY_
    re.compile(r" (?P<month>0?[1-9]|1[0-2])-(?P<day>0?[1-9]|[12][0-9]|3[01])-(?P<year>\d{2})_"),
    # YYYY-MM / YYYY_MM / YYYY.MM / YYYY MM
    re.compile(r"(?P<year>19\d{2}|20\d{2}|2026)[-_\. ](?P<month>0?[1-9]|1[0-2])"),
]


class ExifDateOrganizer:
    def __init__(self, source: Path, dest: Path, log_path: Path, dry_run: bool, limit: int, batch_size: int, verbose: bool, copy_unsupported: bool):
        self.source = source
        self.dest = dest
        self.log_path = log_path
        self.dry_run = dry_run
        self.limit = limit
        self.batch_size = batch_size
        self.verbose = verbose
        self.copy_unsupported = copy_unsupported
        self.now = datetime.now()
        self.unsupported_files: Dict[Path, str] = {}
        self.stats = {
            "found": 0,
            "unknown": 0,
            "copied": 0,
            "skipped": 0,
            "unsupported": 0,
            "errors": 0,
        }

    def run(self) -> int:
        self._ensure_exiftool_available()
        self.dest.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        limit = self.limit if self.dry_run and self.limit > 0 else None
        files = list(self._collect_files(limit=limit))

        if self.verbose:
            print(f"Found {len(files)} supported files under {self.source}")

        exif_map = self._read_exif_metadata(files)
        planned_actions = self._plan_actions(files, exif_map)

        if self.verbose:
            print(f"Planned {len(planned_actions)} actions")

        self._execute_actions(planned_actions)
        self._print_summary()

        return 0 if self.stats["errors"] == 0 else 1

    def _ensure_exiftool_available(self) -> None:
        try:
            subprocess.run(["exiftool", "-ver"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("exiftool is required but not found in PATH")

    def _collect_files(self, limit: Optional[int] = None) -> Iterable[Path]:
        count = 0
        for root, dirs, files in os.walk(self.source):
            for filename in files:
                path = Path(root) / filename
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    self.stats["unsupported"] += 1
                    self.unsupported_files[path] = "unsupported file extension"
                    continue
                yield path
                count += 1
                if limit is not None and count >= limit:
                    return

    def _read_exif_metadata(self, files: List[Path]) -> Dict[Path, ExifMetadata]:
        metadata: Dict[Path, ExifMetadata] = {}
        for batch in self._chunks(files, self.batch_size):
            cmd = ["exiftool", "-j", "-DateTimeOriginal", "-CreateDate", "-ModifyDate"] + [str(path) for path in batch]
            try:
                result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                entries = json.loads(result.stdout.decode("utf-8", errors="replace"))
                self._load_exif_entries(entries, metadata)
            except subprocess.CalledProcessError:
                for path in batch:
                    if not self._read_exif_metadata_for_single_file(path, metadata):
                        if path not in self.unsupported_files:
                            self.unsupported_files[path] = "failed metadata read"
                            self.stats["unsupported"] += 1
            except json.JSONDecodeError:
                for path in batch:
                    if not self._read_exif_metadata_for_single_file(path, metadata):
                        if path not in self.unsupported_files:
                            self.unsupported_files[path] = "failed metadata read"
                            self.stats["unsupported"] += 1
        return metadata

    def _read_exif_metadata_for_single_file(self, source_path: Path, metadata: Dict[Path, ExifMetadata]) -> bool:
        cmd = ["exiftool", "-j", "-DateTimeOriginal", "-CreateDate", "-ModifyDate", str(source_path)]
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            entries = json.loads(result.stdout.decode("utf-8", errors="replace"))
            self._load_exif_entries(entries, metadata)
            return True
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return False

    def _load_exif_entries(self, entries: List[Dict], metadata: Dict[Path, ExifMetadata]) -> None:
        for entry in entries:
            source_file = Path(entry.get("SourceFile"))
            metadata[source_file] = ExifMetadata(
                source_file=source_file,
                datetime_original=entry.get("DateTimeOriginal"),
                create_date=entry.get("CreateDate"),
                modify_date=entry.get("ModifyDate"),
            )
        return metadata

    def _plan_actions(self, files: List[Path], exif_map: Dict[Path, ExifMetadata]) -> List[Dict]:
        actions = []
        for source_path in files:
            if source_path in self.unsupported_files:
                continue

            existing = exif_map.get(source_path, ExifMetadata(source_path, None, None, None))
            derived_timestamp, reason = self._determine_timestamp(source_path, existing)
            dest_path = self._destination_path(source_path, derived_timestamp)
            if dest_path is None:
                self.stats["unknown"] += 1
                prefixed_name = self._get_path_prefixed_filename(source_path)
                dest_path = self.dest / "unknown_date" / prefixed_name
            else:
                self.stats["found"] += 1

            actions.append(
                {
                    "source": source_path,
                    "dest": dest_path,
                    "metadata": existing,
                    "derived_timestamp": derived_timestamp,
                    "reason": reason,
                }
            )

        actions.extend(self._plan_unsupported_actions())
        return actions

    def _plan_unsupported_actions(self) -> List[Dict]:
        if not self.copy_unsupported:
            return []

        actions: List[Dict] = []
        for source_path, reason in self.unsupported_files.items():
            actions.append(
                {
                    "source": source_path,
                    "dest": self.dest / "unsupported_ext" / source_path.name,
                    "metadata": ExifMetadata(source_path, None, None, None),
                    "derived_timestamp": None,
                    "reason": reason,
                }
            )
        return actions

    def _execute_actions(self, actions: List[Dict]) -> None:
        self._write_log_header_if_missing()

        write_updates: List[Tuple[Dict, Path, str]] = []
        for action in actions:
            source: Path = action["source"]
            dest: Path = action["dest"]
            derived_timestamp: Optional[str] = action["derived_timestamp"]
            metadata: ExifMetadata = action["metadata"]
            reason: str = action["reason"]

            dest.parent.mkdir(parents=True, exist_ok=True)
            if self.dry_run:
                self._log_action(action, "dry-run")
                if self.verbose:
                    self._print_action(action)
                continue

            if dest.exists():
                if self._files_are_identical(source, dest):
                    self.stats["skipped"] += 1
                    self._log_action(action, "skipped")
                    if self.verbose:
                        print(f"{source} (identical to existing {dest}, skipped)")
                    continue
                dest = self._resolve_collision(dest)

            try:
                shutil.copy2(source, dest)
                self.stats["copied"] += 1
                if self._needs_exif_update(metadata, derived_timestamp):
                    write_updates.append((action, dest, derived_timestamp))
                else:
                    status = "unsupported" if reason in {"unsupported file extension", "failed metadata read"} else "copied"
                    self._log_action(action, status)
                    if self.verbose:
                        self._print_action(action)
            except Exception as exc:
                self.stats["errors"] += 1
                # For supported files with errors, copy to unknown_date with prefixed name
                if source.suffix.lower() in SUPPORTED_EXTENSIONS:
                    error_prefix = "ERROR_"
                    prefixed_name = error_prefix + self._get_path_prefixed_filename(source)
                    error_dest = self.dest / "unknown_date" / prefixed_name
                    error_dest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(source, error_dest)
                        error_action = dict(action)
                        error_action["dest"] = error_dest
                        self._log_action(error_action, f"error (copied to fallback): {exc}")
                    except Exception as move_exc:
                        self._log_action(action, f"error: {exc} (also failed to copy to fallback: {move_exc})")
                else:
                    self._log_action(action, f"error: {exc}")

        if not self.dry_run and write_updates:
            self._update_exif_batch(write_updates)

    def _needs_exif_update(self, metadata: ExifMetadata, derived_timestamp: Optional[str]) -> bool:
        if derived_timestamp is None:
            return False
        existing = metadata.datetime_original
        if existing is None:
            return True
        formatted_existing = self._normalize_exif_date(existing)
        if formatted_existing != derived_timestamp:
            return True
        if metadata.create_date is None or metadata.modify_date is None:
            return True
        return False

    def _update_exif_batch(self, updates: List[Tuple[Dict, Path, str]]) -> None:
        for batch in self._chunks(updates, self.batch_size):
            # Try a batch write first
            cmd = ["exiftool", "-overwrite_original"]
            for _, dest_path, timestamp in batch:
                cmd.extend([
                    f"-DateTimeOriginal={timestamp}",
                    f"-CreateDate={timestamp}",
                    f"-ModifyDate={timestamp}",
                    str(dest_path),
                ])
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                # Batch succeeded — log all actions as copied
                for action, _, _ in batch:
                    self._log_action(action, "copied")
                    if self.verbose:
                        self._print_action(action)
            except subprocess.CalledProcessError:
                # Batch failed — try each file individually to isolate failures
                for action, dest_path, timestamp in batch:
                    try:
                        single_cmd = [
                            "exiftool",
                            "-overwrite_original",
                            f"-DateTimeOriginal={timestamp}",
                            f"-CreateDate={timestamp}",
                            f"-ModifyDate={timestamp}",
                            str(dest_path),
                        ]
                        subprocess.run(single_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        # per-file write succeeded
                        self._log_action(action, "copied")
                        if self.verbose:
                            self._print_action(action)
                    except subprocess.CalledProcessError as exc:
                        # per-file write failed — move the destination file to unsupported_ext and log
                        stderr_text = exc.stderr.decode("utf-8", errors="replace") if getattr(exc, "stderr", None) is not None else ""
                        reason_text = f"metadata write failed: {stderr_text.splitlines()[0] if stderr_text else 'unknown error'}"
                        try:
                            unsupported_parent = self.dest / "unsupported_ext"
                            unsupported_parent.mkdir(parents=True, exist_ok=True)
                            new_dest = unsupported_parent / dest_path.name
                            if new_dest.exists():
                                new_dest = self._resolve_collision(new_dest)
                            shutil.move(str(dest_path), str(new_dest))
                            # adjust stats: this file was already counted as copied during copy step
                            self.stats["unsupported"] += 1
                            self.stats["copied"] = max(0, self.stats["copied"] - 1)
                            # log the moved file with the failure reason
                            action_copy = dict(action)
                            action_copy["dest"] = new_dest
                            action_copy["reason"] = reason_text
                            self._log_action(action_copy, "unsupported")
                            if self.verbose:
                                self._print_action(action_copy)
                        except Exception as move_exc:
                            self.stats["errors"] += 1
                            self._log_action(action, f"error: {move_exc}")

    def _log_action(self, action: Dict, status: str) -> None:
        line = self._format_log_line(action, status)
        with open(self.log_path, "a", encoding="utf-8") as log_file:
            log_file.write(line + "\n")

    def _write_log_header_if_missing(self) -> None:
        if not self.log_path.exists():
            with open(self.log_path, "w", encoding="utf-8") as log_file:
                log_file.write("source\texif_datetime\tderived_timestamp\tdestination\tstatus\treason\n")

    def _format_log_line(self, action: Dict, status: str) -> str:
        metadata: ExifMetadata = action["metadata"]
        exif_values = [
            f"DateTimeOriginal={metadata.datetime_original}" if metadata.datetime_original else None,
            f"CreateDate={metadata.create_date}" if metadata.create_date else None,
            f"ModifyDate={metadata.modify_date}" if metadata.modify_date else None,
        ]
        exif_str = ",".join([value for value in exif_values if value]) or "none"
        derived_timestamp = action["derived_timestamp"] or "unknown"
        reason = action["reason"] or ""
        return "\t".join(
            [
                str(action["source"]),
                exif_str,
                derived_timestamp,
                str(action["dest"]),
                status,
                reason,
            ]
        )

    def _print_action(self, action: Dict) -> None:
        src = action["source"]
        dest = action["dest"]
        derived = action["derived_timestamp"] or "unknown"
        reason = action["reason"] or ""
        print(f"{src} -> {dest} | derived={derived} {reason}")

    def _print_summary(self) -> None:
        print("\nSummary:")
        print(f"  files found: {self.stats['found']}")
        print(f"  unknown dates: {self.stats['unknown']}")
        print(f"  copied: {self.stats['copied']}")
        print(f"  unsupported files: {self.stats['unsupported']}")
        print(f"  errors: {self.stats['errors']}")
        print(f"  log: {self.log_path}")

    def _resolve_collision(self, dest: Path) -> Path:
        count = 1
        candidate = dest
        while candidate.exists():
            candidate = dest.with_name(f"{dest.stem}_{count}{dest.suffix}")
            count += 1
        return candidate

    def _files_are_identical(self, source: Path, dest: Path) -> bool:
        """Compare two files using MD5 hash to determine if they are identical."""
        if not dest.exists():
            return False
        try:
            source_hash = self._compute_file_hash(source)
            dest_hash = self._compute_file_hash(dest)
            return source_hash == dest_hash
        except Exception:
            return False

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute MD5 hash of file contents."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _get_path_prefixed_filename(self, source_path: Path) -> str:
        """Generate a filename with the relative source path prepended, replacing '/' with '_'."""
        try:
            relative_path = source_path.relative_to(self.source)
            path_parts = list(relative_path.parts[:-1])  # All parts except the filename
            if path_parts:
                path_prefix = "_".join(path_parts) + "_"
                return path_prefix + source_path.name
            return source_path.name
        except ValueError:
            # If relative_to fails, just return the filename
            return source_path.name

    def _is_valid_month(self, text: str) -> bool:
        """Check if text is a valid month (01-12 or 1-12)."""
        try:
            month = int(text)
            return 1 <= month <= 12
        except ValueError:
            return False

    def _is_valid_day(self, text: str) -> bool:
        """Check if text is a valid day (01-31 or 1-31)."""
        try:
            day = int(text)
            return 1 <= day <= 31
        except ValueError:
            return False

    def _destination_path(self, source_path: Path, derived_timestamp: Optional[str]) -> Optional[Path]:
        if derived_timestamp is None:
            return None
        try:
            dt = datetime.strptime(derived_timestamp, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            return None
        year = f"{dt.year:04d}"
        month = f"{dt.month:02d}"
        return self.dest / year / month / source_path.name

    def _determine_timestamp(self, source_path: Path, metadata: ExifMetadata) -> Tuple[Optional[str], Optional[str]]:
        stem = source_path.stem
        if stem.isdigit() and len(stem) > 14:
            filename_timestamp = None
        else:
            filename_timestamp = self._extract_timestamp_from_text(stem)

        directory_timestamp = self._extract_timestamp_from_path(source_path.parent)

        derived_timestamp = filename_timestamp or directory_timestamp
        derived_reason = None
        if filename_timestamp:
            derived_reason = "derived from filename"
        elif directory_timestamp:
            derived_reason = "derived from directory path"

        if derived_timestamp:
            if metadata.datetime_original:
                normalized_embedded = self._normalize_exif_date(metadata.datetime_original)
                if normalized_embedded:
                    if self._year_month_match(normalized_embedded, derived_timestamp):
                        return normalized_embedded, "embedded DateTimeOriginal matches derived year/month"
                    return derived_timestamp, derived_reason
            return derived_timestamp, derived_reason

        if metadata.datetime_original:
            normalized = self._normalize_exif_date(metadata.datetime_original)
            if normalized:
                return normalized, "embedded DateTimeOriginal"

        return None, "unable to determine timestamp"

    def _year_month_match(self, embedded_timestamp: str, derived_timestamp: str) -> bool:
        try:
            embedded_dt = datetime.strptime(embedded_timestamp, "%Y:%m:%d %H:%M:%S")
            derived_dt = datetime.strptime(derived_timestamp, "%Y:%m:%d %H:%M:%S")
            return embedded_dt.year == derived_dt.year and embedded_dt.month == derived_dt.month
        except ValueError:
            return False

    def _extract_timestamp_from_text(self, text: str) -> Optional[str]:
        candidate = self._find_date_in_text(text)
        if candidate is None:
            return None
        full_date = self._build_date_string(candidate)
        if full_date and not self._is_future(full_date):
            return full_date
        return None

    def _extract_timestamp_from_path(self, path: Path) -> Optional[str]:
        # First, try to find patterns that span multiple consecutive path segments (YYYY/MM/DD or YYYY/MM)
        parts = list(path.parts)
        for i in range(len(parts) - 1, 0, -1):  # Start from the end, go backwards
            current_part = parts[i]
            prev_part = parts[i - 1]
            
            # Check if current part is a year
            year_match = self._find_date_in_text(current_part)
            if year_match and year_match.get("year") and not year_match.get("month"):
                year = year_match["year"]
                
                # Check if previous part is a month
                if self._is_valid_month(prev_part):
                    month = int(prev_part)
                    day = 1
                    
                    # Check if there's a day part (two segments back)
                    if i >= 2 and self._is_valid_day(parts[i - 2]):
                        day = int(parts[i - 2])
                    
                    full_date = self._build_date_string({"year": year, "month": month, "day": day})
                    if full_date and not self._is_future(full_date):
                        return full_date
        
        # Fall back to single-part extraction
        partial: Dict[str, int] = {}
        for part in reversed(path.parts):
            candidate = self._find_date_in_text(part)
            if candidate is None:
                continue
            if candidate.get("year") and candidate.get("month") and candidate.get("day"):
                full_date = self._build_date_string(candidate)
                if full_date and not self._is_future(full_date):
                    return full_date
            if candidate.get("year") and candidate.get("month") and not candidate.get("day"):
                partial = candidate
                if not self._is_future(self._build_date_string({"year": candidate["year"], "month": candidate["month"], "day": 1})):
                    return self._build_date_string({"year": candidate["year"], "month": candidate["month"], "day": 1})
            if candidate.get("year") and not candidate.get("month"):
                partial = candidate
                full_date = self._build_date_string({"year": candidate["year"], "month": 1, "day": 1})
                if full_date and not self._is_future(full_date):
                    return full_date
            if candidate.get("month") and not candidate.get("year"):
                if partial.get("year"):
                    year = partial["year"]
                    month = candidate["month"]
                    full_date = self._build_date_string({"year": year, "month": month, "day": 1})
                    if full_date and not self._is_future(full_date):
                        return full_date
        return None

    def _find_date_in_text(self, text: str) -> Optional[Dict[str, int]]:
        for pattern in DATE_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            parts = match.groupdict()
            year = int(parts["year"]) if parts.get("year") else None
            month = int(parts["month"]) if parts.get("month") else None
            day = int(parts["day"]) if parts.get("day") else None
            if year and not (DATE_YEAR_MIN <= year <= DATE_YEAR_MAX):
                continue
            if month and not (1 <= month <= 12):
                continue
            if day and not (1 <= day <= 31):
                continue
            return {k: v for k, v in {"year": year, "month": month, "day": day}.items() if v is not None}
        return None

    def _build_date_string(self, date_parts: Dict[str, int]) -> Optional[str]:
        year = date_parts.get("year")
        month = date_parts.get("month", 1)
        day = date_parts.get("day", 1)
        if year is None:
            return None
        try:
            dt = datetime(year=year, month=month, day=day, hour=0, minute=0, second=0)
        except ValueError:
            return None
        return dt.strftime("%Y:%m:%d %H:%M:%S")

    def _normalize_exif_date(self, value: str) -> Optional[str]:
        if not isinstance(value, str):
            value = str(value)
        for fmt in ["%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(value, fmt)
                return dt.strftime("%Y:%m:%d %H:%M:%S")
            except ValueError:
                continue
        return None

    def _is_future(self, date_string: str) -> bool:
        try:
            dt = datetime.strptime(date_string, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            return True
        return dt > self.now

    @staticmethod
    def _chunks(items: Iterable, size: int):
        items = list(items)
        for i in range(0, len(items), size):
            yield items[i : i + size]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize photos and videos using ExifTool and derived dates.")
    parser.add_argument(
        "--source",
        default="~/Pictures/",
        help="Source root folder. Default: ~/Pictures/",
    )
    parser.add_argument(
        "--dest",
        default="~/Pictures_Organized/",
        help="Destination root folder. Default: ~/Pictures_Organized/",
    )
    parser.add_argument(
        "--log",
        default=None,
        help="Log file path. Default: exif_date_organizer.log inside destination folder.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without copying or modifying files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Limit number of files processed when dry-run is enabled. Default: 500 (no limit).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=300,
        help="Number of files per ExifTool batch. Default: 300.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print summary and planned actions to console.",
    )
    parser.add_argument(
        "--copy-unsupported",
        action="store_true",
        help="Copy unsupported files into the unsupported_ext folder instead of skipping them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    dest = Path(args.dest).expanduser().resolve()
    log_path = Path(args.log).expanduser().resolve() if args.log else dest / "exif_date_organizer.log"

    organizer = ExifDateOrganizer(
        source=source,
        dest=dest,
        log_path=log_path,
        dry_run=args.dry_run,
        limit=args.limit,
        batch_size=args.batch_size,
        verbose=args.verbose,
        copy_unsupported=args.copy_unsupported,
    )
    return organizer.run()


if __name__ == "__main__":
    sys.exit(main())
