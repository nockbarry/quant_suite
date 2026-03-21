"""Bug Detection Monitor.

Scans system logs for errors, categorizes them, tracks frequency,
and proposes fixes for known patterns.

Detection sources:
1. Python tracebacks in log files (~/quant_results/logs/*.log)
2. Non-zero exit codes in session completions
3. Missing expected output files (sessions that produce no artifacts)
4. Error patterns in process_events.jsonl

Known auto-fixable patterns:
- AttributeError on NoneType -> add null check
- KeyError -> add .get() with default
- FileNotFoundError -> add existence check
- TypeError on int/float conversion -> add type coercion
"""
import re
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from pathlib import Path
from collections import Counter
from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class BugReport:
    """A detected bug or error."""
    bug_id: str
    timestamp: str
    severity: str  # "crash", "error", "warning", "silent_failure"
    category: str  # "traceback", "exit_code", "missing_output", "data_error"
    source_file: str  # Which log file
    error_type: str  # e.g., "AttributeError", "KeyError", "FileNotFoundError"
    error_message: str
    traceback: str  # Full traceback if available
    affected_module: str  # e.g., "src/swarm/situation_board.py"
    affected_line: int
    occurrence_count: int  # How many times this exact error appeared
    first_seen: str
    last_seen: str
    auto_fixable: bool
    fix_description: str  # What the fix would be
    fix_applied: bool = False
    fix_proposal_id: str = ""  # Links to UpgradeProposal if fix attempted


class BugMonitor:
    """Scans logs for bugs and categorizes them."""

    REPORT_FILE = paths.base / "logs" / "bug_reports.json"

    # Log directories to scan
    LOG_DIRS: list[Path] = []

    # Known error patterns and their fixes
    KNOWN_PATTERNS = {
        "NoneType_attr": {
            "pattern": r"AttributeError: 'NoneType' object has no attribute '(\w+)'",
            "fix": "Add null check before accessing attribute",
            "auto_fixable": True,
            "severity": "error",
        },
        "KeyError": {
            "pattern": r"KeyError: '([^']*)'",
            "fix": "Replace dict[key] with dict.get(key, default)",
            "auto_fixable": True,
            "severity": "error",
        },
        "FileNotFound": {
            "pattern": r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']*)'",
            "fix": "Add Path.exists() check before reading",
            "auto_fixable": True,
            "severity": "error",
        },
        "TypeError_int": {
            "pattern": r"TypeError: int\(\) argument must be a string.*not '(\w+)'",
            "fix": "Add type coercion with float() then int()",
            "auto_fixable": True,
            "severity": "error",
        },
        "ValueError_int": {
            "pattern": r"ValueError: invalid literal for int\(\) with base 10: '([^']*)'",
            "fix": "Use float() before int() for decimal strings",
            "auto_fixable": True,
            "severity": "error",
        },
        "ImportError": {
            "pattern": r"ImportError: cannot import name '(\w+)' from '([^']*)'",
            "fix": "Check module exports or fix import path",
            "auto_fixable": False,
            "severity": "crash",
        },
        "ModuleNotFound": {
            "pattern": r"ModuleNotFoundError: No module named '([^']*)'",
            "fix": "Install missing package or fix import path",
            "auto_fixable": False,
            "severity": "crash",
        },
        "ConnectionError": {
            "pattern": r"(ConnectionError|ConnectionRefusedError|TimeoutError|ConnectionResetError)",
            "fix": "Transient network issue -- retry or skip gracefully",
            "auto_fixable": False,
            "severity": "warning",
        },
        "async_not_awaited": {
            "pattern": r"RuntimeWarning: coroutine '(\w+)' was never awaited",
            "fix": "Wrap async call with asyncio.run() or await",
            "auto_fixable": True,
            "severity": "error",
        },
        "TypeError_None_subscript": {
            "pattern": r"TypeError: 'NoneType' object is not subscriptable",
            "fix": "Add null check before indexing/subscripting",
            "auto_fixable": True,
            "severity": "error",
        },
        "TypeError_None_iterable": {
            "pattern": r"TypeError: 'NoneType' object is not iterable",
            "fix": "Add null check or default to empty list before iterating",
            "auto_fixable": True,
            "severity": "error",
        },
        "JSONDecodeError": {
            "pattern": r"(?:json\.decoder\.)?JSONDecodeError: (.+)",
            "fix": "Add try/except around JSON parsing with fallback",
            "auto_fixable": True,
            "severity": "warning",
        },
        "PermissionError": {
            "pattern": r"PermissionError: \[Errno 13\]",
            "fix": "Check file permissions or use a different path",
            "auto_fixable": False,
            "severity": "error",
        },
        "IndexError": {
            "pattern": r"IndexError: (list|tuple) index out of range",
            "fix": "Add bounds check before indexing",
            "auto_fixable": True,
            "severity": "error",
        },
        "AttributeError_general": {
            "pattern": r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
            "fix": "Check object type or use hasattr() before accessing",
            "auto_fixable": False,
            "severity": "error",
        },
        "ZeroDivisionError": {
            "pattern": r"ZeroDivisionError: (division by zero|float division by zero)",
            "fix": "Add zero check before division",
            "auto_fixable": True,
            "severity": "error",
        },
        "OSError_disk": {
            "pattern": r"OSError: \[Errno 28\] No space left on device",
            "fix": "Disk full -- clean up old logs or expand storage",
            "auto_fixable": False,
            "severity": "crash",
        },
        "RecursionError": {
            "pattern": r"RecursionError: maximum recursion depth exceeded",
            "fix": "Break circular reference or increase recursion limit",
            "auto_fixable": False,
            "severity": "crash",
        },
    }

    # Maximum log file size to scan (50 MB)
    MAX_LOG_SIZE = 50 * 1024 * 1024

    # Maximum number of tracebacks to extract per file
    MAX_TRACEBACKS_PER_FILE = 100

    def __init__(self):
        self.bugs: list[BugReport] = []
        self.LOG_DIRS = [paths.base / "logs"]
        # Also scan instance logs
        for d in Path.home().glob("quant_results*/logs"):
            if d.is_dir() and d not in self.LOG_DIRS:
                self.LOG_DIRS.append(d)

    def scan_all(self, hours: int = 24) -> list[BugReport]:
        """Scan all log sources for bugs.

        Args:
            hours: Only scan files modified within this many hours.
        """
        self.bugs = []
        self.bugs.extend(self._scan_log_files(hours))
        self.bugs.extend(self._scan_completions(hours))
        self.bugs.extend(self._scan_process_events(hours))

        # Deduplicate by error signature
        self.bugs = self._deduplicate(self.bugs)

        # Save report
        self._save_report()
        return self.bugs

    def _scan_log_files(self, hours: int = 24) -> list[BugReport]:
        """Scan *.log files for Python tracebacks."""
        bugs = []
        cutoff = datetime.now().timestamp() - (hours * 3600)
        for log_dir in self.LOG_DIRS:
            if not log_dir.exists():
                continue
            for log_file in log_dir.glob("*.log"):
                try:
                    stat = log_file.stat()
                except OSError:
                    continue
                # Only scan files modified within window
                if stat.st_mtime < cutoff:
                    continue
                # Skip huge files
                if stat.st_size > self.MAX_LOG_SIZE:
                    logger.warning(f"Skipping oversized log: {log_file} ({stat.st_size / 1024 / 1024:.0f} MB)")
                    continue
                try:
                    content = log_file.read_text(errors='ignore')
                    bugs.extend(self._extract_tracebacks(content, str(log_file)))
                except Exception as e:
                    logger.debug(f"Error reading {log_file}: {e}")
                    continue
        return bugs

    # Common Python exception class names for validation
    _KNOWN_EXCEPTIONS = {
        'AttributeError', 'KeyError', 'FileNotFoundError', 'TypeError',
        'ValueError', 'ImportError', 'ModuleNotFoundError', 'IndexError',
        'NameError', 'RuntimeError', 'RuntimeWarning', 'OSError', 'IOError',
        'ConnectionError', 'ConnectionRefusedError', 'TimeoutError',
        'ConnectionResetError', 'JSONDecodeError', 'PermissionError',
        'ZeroDivisionError', 'RecursionError', 'StopIteration',
        'UnicodeDecodeError', 'UnicodeEncodeError', 'OverflowError',
        'AssertionError', 'NotImplementedError', 'SystemExit',
        'json.decoder.JSONDecodeError', 'sqlite3.OperationalError',
        'sqlite3.IntegrityError', 'asyncio.TimeoutError',
        'requests.exceptions.ConnectionError', 'requests.exceptions.Timeout',
        'urllib.error.URLError', 'decimal.InvalidOperation',
    }

    def _extract_tracebacks(self, content: str, source_file: str) -> list[BugReport]:
        """Extract Python tracebacks from log content."""
        bugs = []

        # Find traceback blocks: starts with "Traceback (most recent call last):"
        # and ends at the error line (first line that doesn't start with whitespace or "File")
        tb_pattern = r'Traceback \(most recent call last\):.*?(?=\n(?!\s|File|Traceback)|\Z)'
        matches = list(re.finditer(tb_pattern, content, re.DOTALL))

        # Limit to avoid memory issues on huge log files
        if len(matches) > self.MAX_TRACEBACKS_PER_FILE:
            matches = matches[-self.MAX_TRACEBACKS_PER_FILE:]

        for match in matches:
            tb_text = match.group(0)

            # Also try to grab the error line that follows the traceback
            # (the regex stops before it, so we look at the content after the match)
            end_pos = match.end()
            next_line = ""
            if end_pos < len(content):
                next_newline = content.find('\n', end_pos)
                if next_newline == -1:
                    next_line = content[end_pos:].strip()
                else:
                    next_line = content[end_pos:next_newline].strip()
            if next_line:
                tb_text = tb_text.rstrip() + '\n' + next_line

            # Extract error type and message from the error line
            # The error line is the final non-indented line that matches ErrorType: message
            lines = tb_text.strip().split('\n')
            if not lines:
                continue

            error_line = ""
            error_type = ""
            error_message = ""

            # Scan from the bottom to find the actual error line
            for line in reversed(lines):
                stripped = line.strip()
                if not stripped:
                    continue
                # Check if this looks like "ErrorType: message" or "module.ErrorType: message"
                colon_match = re.match(r'^([\w.]+(?:Error|Exception|Warning|Exit))\s*:\s*(.*)', stripped)
                if colon_match:
                    error_type = colon_match.group(1)
                    error_message = colon_match.group(2)
                    error_line = stripped
                    break
                # Also handle bare exception names without message
                if stripped in self._KNOWN_EXCEPTIONS or re.match(r'^[\w.]+(?:Error|Exception|Warning)$', stripped):
                    error_type = stripped
                    error_message = ""
                    error_line = stripped
                    break
                # Handle "raise ExceptionType(...)" lines
                raise_match = re.match(r'^raise\s+([\w.]+(?:Error|Exception|Warning))\s*\(', stripped)
                if raise_match:
                    error_type = raise_match.group(1)
                    # Extract message from raise arguments if possible
                    msg_match = re.search(r'raise\s+\w+\("([^"]*)"', stripped)
                    error_message = msg_match.group(1) if msg_match else stripped
                    error_line = stripped
                    break

            # If no proper error line found, this is a truncated traceback
            if not error_type:
                # Use the last non-File line as a hint
                error_type = "TruncatedTraceback"
                error_message = lines[-1].strip()[:100] if lines else "Unknown"
                error_line = error_message

            # Extract affected file and line from traceback
            file_matches = re.findall(r'File "([^"]+)", line (\d+)', tb_text)
            affected_module = ""
            affected_line = 0
            if file_matches:
                # Get the last file reference (most specific to our code)
                # Prefer files in our project over stdlib/packages
                for fpath, fline in reversed(file_matches):
                    if 'quant_suite' in fpath or 'quant_results' in fpath:
                        affected_module = fpath
                        affected_line = int(fline)
                        break
                if not affected_module:
                    affected_module = file_matches[-1][0]
                    affected_line = int(file_matches[-1][1])

            # Build canonical error string for pattern matching: "ErrorType: message"
            canonical_error = f"{error_type}: {error_message}" if error_message else error_type

            # Check against known patterns for fix suggestions
            auto_fixable = False
            fix_description = "Unknown error -- requires manual investigation"
            severity = "error"

            for pattern_name, pattern_info in self.KNOWN_PATTERNS.items():
                if re.search(pattern_info["pattern"], canonical_error) or re.search(pattern_info["pattern"], error_line):
                    auto_fixable = pattern_info["auto_fixable"]
                    fix_description = pattern_info["fix"]
                    severity = pattern_info["severity"]
                    break

            # Generate stable bug ID from error signature
            sig = (error_type, error_message[:100], affected_module)
            bug_id = f"bug_{abs(hash(sig)):010x}"

            bugs.append(BugReport(
                bug_id=bug_id,
                timestamp=datetime.now().isoformat(),
                severity=severity,
                category="traceback",
                source_file=source_file,
                error_type=error_type,
                error_message=error_message[:200],
                traceback=tb_text[:2000],  # Cap traceback length
                affected_module=affected_module,
                affected_line=affected_line,
                occurrence_count=1,
                first_seen=datetime.now().isoformat(),
                last_seen=datetime.now().isoformat(),
                auto_fixable=auto_fixable,
                fix_description=fix_description,
            ))

        return bugs

    def _scan_completions(self, hours: int = 24) -> list[BugReport]:
        """Scan session completions for failures."""
        bugs = []
        cutoff = datetime.now().timestamp() - (hours * 3600)
        comp_dirs = [paths.base / "scheduler" / "completions"]
        for d in Path.home().glob("quant_results*/scheduler/completions"):
            if d.is_dir() and d not in comp_dirs:
                comp_dirs.append(d)

        for comp_dir in comp_dirs:
            if not comp_dir.exists():
                continue
            for f in comp_dir.glob("*.json"):
                try:
                    if f.stat().st_mtime < cutoff:
                        continue
                except OSError:
                    continue
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                    continue

                # Failed sessions
                if not data.get("success", True):
                    bugs.append(BugReport(
                        bug_id=f"bug_session_{f.stem}",
                        timestamp=data.get("completed_at", datetime.now().isoformat()),
                        severity="error",
                        category="exit_code",
                        source_file=str(f),
                        error_type="SessionFailure",
                        error_message=str(data.get("summary", "Session failed"))[:200],
                        traceback="",
                        affected_module=str(data.get("session_type", "unknown")),
                        affected_line=0,
                        occurrence_count=1,
                        first_seen=data.get("completed_at", datetime.now().isoformat()),
                        last_seen=data.get("completed_at", datetime.now().isoformat()),
                        auto_fixable=False,
                        fix_description="Session failed -- check log file",
                    ))

                # Empty sessions (smart_completion with no findings)
                if data.get("source") == "smart_completion" and not data.get("key_findings"):
                    bugs.append(BugReport(
                        bug_id=f"bug_empty_{f.stem}",
                        timestamp=data.get("completed_at", datetime.now().isoformat()),
                        severity="warning",
                        category="silent_failure",
                        source_file=str(f),
                        error_type="EmptySession",
                        error_message=f"Session {data.get('session_type', '?')} produced no findings",
                        traceback="",
                        affected_module=str(data.get("session_type", "unknown")),
                        affected_line=0,
                        occurrence_count=1,
                        first_seen=data.get("completed_at", datetime.now().isoformat()),
                        last_seen=data.get("completed_at", datetime.now().isoformat()),
                        auto_fixable=False,
                        fix_description="Session ran but produced no output -- may need prompt improvement",
                    ))

        return bugs

    def _scan_process_events(self, hours: int = 24) -> list[BugReport]:
        """Scan process_events.jsonl for error events."""
        bugs = []
        events_files = [paths.base / "logs" / "process_events.jsonl"]
        for d in Path.home().glob("quant_results*/logs"):
            pf = d / "process_events.jsonl"
            if pf.exists() and pf not in events_files:
                events_files.append(pf)

        cutoff = datetime.now() - timedelta(hours=hours)

        for events_file in events_files:
            if not events_file.exists():
                continue
            try:
                # Only read the tail of large files (last 500KB)
                file_size = events_file.stat().st_size
                read_offset = max(0, file_size - 500_000)

                with open(events_file, 'r', errors='ignore') as fh:
                    if read_offset > 0:
                        fh.seek(read_offset)
                        fh.readline()  # Skip partial line
                    lines = fh.readlines()

                # Limit to last 2000 lines
                lines = lines[-2000:]

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue

                    # Check if within time window
                    ts_str = event.get("timestamp", "")
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                            # Compare naive datetimes
                            if ts.replace(tzinfo=None) < cutoff:
                                continue
                        except (ValueError, TypeError):
                            pass

                    if event.get("status") == "error" or event.get("level") == "error":
                        sig = (
                            event.get("event_type", "ProcessError"),
                            str(event.get("message", event.get("error", "")))[:100],
                            str(event.get("source", "unknown")),
                        )
                        bug_id = f"bug_event_{abs(hash(sig)):010x}"
                        bugs.append(BugReport(
                            bug_id=bug_id,
                            timestamp=ts_str or datetime.now().isoformat(),
                            severity="error",
                            category="data_error",
                            source_file=str(events_file),
                            error_type=str(event.get("event_type", "ProcessError")),
                            error_message=str(event.get("message", event.get("error", "")))[:200],
                            traceback="",
                            affected_module=str(event.get("source", "unknown")),
                            affected_line=0,
                            occurrence_count=1,
                            first_seen=ts_str or datetime.now().isoformat(),
                            last_seen=ts_str or datetime.now().isoformat(),
                            auto_fixable=False,
                            fix_description="Process event error",
                        ))
            except Exception as e:
                logger.debug(f"Error scanning {events_file}: {e}")
                continue

        return bugs

    def _deduplicate(self, bugs: list[BugReport]) -> list[BugReport]:
        """Merge duplicate bugs by error signature."""
        seen: dict[tuple, BugReport] = {}
        for bug in bugs:
            key = (bug.error_type, bug.error_message[:100], bug.affected_module)
            if key in seen:
                seen[key].occurrence_count += 1
                if bug.timestamp > seen[key].last_seen:
                    seen[key].last_seen = bug.timestamp
                if bug.timestamp < seen[key].first_seen:
                    seen[key].first_seen = bug.timestamp
                # Keep the longer traceback
                if len(bug.traceback) > len(seen[key].traceback):
                    seen[key].traceback = bug.traceback
            else:
                seen[key] = bug
        return sorted(seen.values(), key=lambda b: b.occurrence_count, reverse=True)

    def get_critical_bugs(self) -> list[BugReport]:
        """Get bugs that need immediate attention."""
        return [b for b in self.bugs if b.severity in ("crash", "error") and b.occurrence_count >= 2]

    def get_auto_fixable(self) -> list[BugReport]:
        """Get bugs that can be auto-fixed."""
        return [b for b in self.bugs if b.auto_fixable and not b.fix_applied]

    def get_summary(self) -> dict:
        """Get bug summary statistics."""
        if not self.bugs:
            self.scan_all()
        return {
            "total": len(self.bugs),
            "crashes": len([b for b in self.bugs if b.severity == "crash"]),
            "errors": len([b for b in self.bugs if b.severity == "error"]),
            "warnings": len([b for b in self.bugs if b.severity == "warning"]),
            "silent_failures": len([b for b in self.bugs if b.severity == "silent_failure"]),
            "auto_fixable": len(self.get_auto_fixable()),
            "recurring": len([b for b in self.bugs if b.occurrence_count >= 3]),
            "top_errors": [(b.error_type, b.error_message[:60], b.occurrence_count)
                          for b in self.bugs[:5]],
        }

    def _save_report(self):
        """Save bug report to JSON file."""
        try:
            self.REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
            report = {
                "timestamp": datetime.now().isoformat(),
                "summary": self.get_summary(),
                "bugs": [asdict(b) for b in self.bugs],
            }
            # Atomic write
            tmp = self.REPORT_FILE.with_suffix('.tmp')
            with open(tmp, 'w') as f:
                json.dump(report, f, indent=2)
            tmp.rename(self.REPORT_FILE)
        except Exception as e:
            logger.error(f"Failed to save bug report: {e}")

    def load_latest(self) -> dict:
        """Load latest bug report from disk."""
        if self.REPORT_FILE.exists():
            try:
                with open(self.REPORT_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load bug report: {e}")
        return {"bugs": [], "summary": {}}
