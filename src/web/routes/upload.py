"""Upload routes — file upload page and handler.

Logic is implemented directly in the route since this is pure file I/O.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


# Allowed extensions and their target directories
UPLOAD_TARGETS = {
    "knowledge": "knowledge",
    "thesis": "theses",
    "learning": "learnings",
    "signal": "live/research",
    "report": "reports",
    "config": "config_uploads",
}

ALLOWED_EXTENSIONS = {".csv", ".json", ".yaml", ".yml"}

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("/")
async def upload_page(request: Request):
    """Upload page with form."""
    templates = request.app.state.templates

    # Recent uploads
    upload_log = _get_upload_log()

    return templates.TemplateResponse(
        request,
        "upload/index.html",
        {
            "active_page": "upload",
            "targets": list(UPLOAD_TARGETS.keys()),
            "recent_uploads": upload_log[-20:],
        },
    )


@router.post("/")
async def handle_upload(
    request: Request,
    file: UploadFile = File(...),
    target: str = Form("report"),
    description: str = Form(""),
):
    """Handle file upload (CSV, JSON, YAML)."""
    templates = request.app.state.templates

    # Validate target
    if target not in UPLOAD_TARGETS:
        raise HTTPException(status_code=400, detail=f"Invalid target: {target}")

    # Validate extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read content
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content)} bytes). Max: {MAX_UPLOAD_SIZE} bytes",
        )

    # Validate content format
    content_str = content.decode("utf-8", errors="replace")
    validation_error = _validate_content(content_str, suffix)
    if validation_error:
        raise HTTPException(status_code=400, detail=f"Invalid file content: {validation_error}")

    # Save file
    target_dir = _results_dir() / UPLOAD_TARGETS[target]
    target_dir.mkdir(parents=True, exist_ok=True)

    # Unique filename to avoid overwrites
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{timestamp}_{file.filename}"
    dest = target_dir / safe_name
    dest.write_text(content_str)

    # Log the upload
    _log_upload({
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.utcnow().isoformat(),
        "filename": file.filename,
        "saved_as": safe_name,
        "target": target,
        "target_dir": str(target_dir),
        "size_bytes": len(content),
        "description": description,
    })

    # Redirect back to upload page with success
    return templates.TemplateResponse(
        request,
        "upload/index.html",
        {
            "active_page": "upload",
            "targets": list(UPLOAD_TARGETS.keys()),
            "recent_uploads": _get_upload_log()[-20:],
            "success": {
                "filename": file.filename,
                "target": target,
                "path": str(dest),
            },
        },
    )


def _validate_content(content: str, suffix: str) -> str | None:
    """Validate file content. Returns error message or None."""
    if suffix == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
    elif suffix in (".yaml", ".yml"):
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            return f"Invalid YAML: {e}"
    elif suffix == ".csv":
        lines = content.strip().split("\n")
        if not lines:
            return "Empty CSV file"
    return None


def _get_upload_log() -> list[dict]:
    """Read upload log."""
    log_path = _results_dir() / "logs" / "upload_log.jsonl"
    if not log_path.exists():
        return []
    entries = []
    for line in log_path.read_text().strip().split("\n"):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _log_upload(entry: dict) -> None:
    """Append to upload log."""
    log_dir = _results_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "upload_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
