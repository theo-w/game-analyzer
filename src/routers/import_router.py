"""Data import API routes."""

from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from src.database import ImportedDataRepository, OperationLogRepository
from src.import_utils import IMPORT_TEMPLATES, parse_import_file, validate_import_records
from src.web_common import get_current_user

router = APIRouter(tags=["import"])


@router.post("/api/import")
async def import_data(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    try:
        data = await request.json()
        metrics = data.get("metrics", [])
        comments = data.get("comments", [])

        if not isinstance(metrics, list) or not isinstance(comments, list):
            raise HTTPException(status_code=400, detail="metrics 和 comments 必须是数组")
        if not metrics and not comments:
            raise HTTPException(status_code=400, detail="至少需要提供 metrics 或 comments")
        if metrics:
            validate_import_records("metrics", metrics)
        if comments:
            validate_import_records("comments", comments)

        counts = ImportedDataRepository.replace_for_user(
            current_user.username,
            metrics=metrics,
            comments=comments,
        )
        OperationLogRepository.log(
            current_user.username,
            "import_data",
            f"Imported metrics={counts['metrics']}, comments={counts['comments']}",
        )
        return {"success": True, "message": "数据导入成功", "counts": counts}
    except HTTPException:
        raise
    except Exception as exc:
        return {"success": False, "message": f"数据导入失败: {exc}"}


@router.get("/api/import/template")
async def import_template(
    dataset_type: str = Query(..., pattern="^(metrics|comments)$"),
    token: Optional[str] = Query(None),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    rows = IMPORT_TEMPLATES[dataset_type]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        io.StringIO(output.getvalue()),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={dataset_type}_import_template.csv",
            "Cache-Control": "no-cache",
        },
    )


@router.post("/api/import/file")
async def import_data_file(
    dataset_type: str = Query(..., pattern="^(metrics|comments)$"),
    token: Optional[str] = Query(None),
    file: UploadFile = File(...),
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)

    records = await parse_import_file(file)
    validate_import_records(dataset_type, records)
    metrics = records if dataset_type == "metrics" else []
    comments = records if dataset_type == "comments" else []

    counts = ImportedDataRepository.replace_for_user(
        current_user.username,
        metrics=metrics,
        comments=comments,
    )
    OperationLogRepository.log(
        current_user.username,
        "import_file",
        f"Imported {dataset_type} from {file.filename}: metrics={counts['metrics']}, comments={counts['comments']}",
    )
    return {
        "success": True,
        "message": "文件导入成功",
        "dataset_type": dataset_type,
        "filename": file.filename,
        "counts": counts,
    }
