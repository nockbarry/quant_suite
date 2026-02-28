"""Reports routes — report file browser and renderer.

Logic is implemented directly in the route since this operates on the
filesystem (report files in ~/quant_results/reports/).
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException

router = APIRouter()


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def _reports_dir() -> Path:
    return _results_dir() / "reports"


def _get_report_tree() -> list[dict]:
    """Build a flat list of report files with metadata."""
    reports_root = _reports_dir()
    if not reports_root.exists():
        return []

    reports = []
    for file_path in sorted(reports_root.rglob("*"), reverse=True):
        if file_path.is_dir():
            continue
        if file_path.name.startswith("."):
            continue

        suffix = file_path.suffix.lower()
        if suffix not in (".md", ".json", ".yaml", ".yml", ".txt", ".html", ".csv"):
            continue

        rel = file_path.relative_to(reports_root)
        stat = file_path.stat()

        reports.append({
            "name": file_path.name,
            "path": str(rel),
            "directory": str(rel.parent) if str(rel.parent) != "." else "",
            "size_bytes": stat.st_size,
            "size_human": _human_size(stat.st_size),
            "modified": stat.st_mtime,
            "type": suffix.lstrip("."),
        })

    return reports


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@router.get("/")
async def report_browser(request: Request):
    """Report file browser."""
    templates = request.app.state.templates

    reports = _get_report_tree()

    # Group by directory
    by_dir: dict[str, list[dict]] = {}
    for r in reports:
        d = r["directory"] or "root"
        by_dir.setdefault(d, []).append(r)

    return templates.TemplateResponse(
        request,
        "reports/index.html",
        {
            "active_page": "reports",
            "reports": reports,
            "by_directory": by_dir,
            "total_count": len(reports),
        },
    )


@router.get("/view/{path:path}")
async def view_report(request: Request, path: str):
    """Render a report file (markdown, JSON, YAML, text)."""
    templates = request.app.state.templates

    reports_root = _reports_dir()
    file_path = (reports_root / path).resolve()

    # Security: ensure we stay within reports directory
    if not str(file_path).startswith(str(reports_root.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Report '{path}' not found")

    raw_content = file_path.read_text(errors="replace")
    suffix = file_path.suffix.lower()

    # Determine content type for rendering
    if suffix == ".json":
        content_type = "json"
        try:
            parsed = json.loads(raw_content)
            rendered = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            rendered = raw_content
    elif suffix in (".md", ".markdown"):
        content_type = "markdown"
        rendered = raw_content
    elif suffix in (".yaml", ".yml"):
        content_type = "yaml"
        rendered = raw_content
    elif suffix == ".csv":
        content_type = "csv"
        rendered = raw_content
    elif suffix == ".html":
        content_type = "html"
        rendered = raw_content
    else:
        content_type = "text"
        rendered = raw_content

    return templates.TemplateResponse(
        request,
        "reports/view.html",
        {
            "active_page": "reports",
            "file_name": file_path.name,
            "file_path": path,
            "content_type": content_type,
            "content": rendered,
            "size_human": _human_size(file_path.stat().st_size),
        },
    )
