from __future__ import annotations

import traceback
import uuid
from datetime import datetime
from pathlib import Path
import asyncio

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .config import (
    AGE_GROUPS,
    ACTIVITY_DURATION_SECONDS,
    ACTIVITY_LABELS,
    activities_for_group,
    validate_age_in_group,
    validate_activity_for_group,
)
from .schemas import AnalyzeResponse
from .csv_results import read_latest_csv_row
from .scoring import score_activity_video
from .storage import append_score_record, extract_calculation_variables, persist_record_to_mongodb
from .logging_utils import get_activity_logger
from .progress import get_progress, initialize_progress, set_progress_message
from activity_common.video_base import read_video_stats

app = FastAPI(title="Child Activity Assessment API", version="1.0.0")
logger = get_activity_logger()


class FrontendLogEvent(BaseModel):
    event: str
    activity: str | None = None
    age_group: str | None = None
    name: str | None = None
    details: str | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_ROOT = Path("common_backend") / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/metadata")
def metadata() -> dict:
    return {
        "age_groups": AGE_GROUPS,
        "activities": ACTIVITY_LABELS,
        "durations_seconds": ACTIVITY_DURATION_SECONDS,
    }


@app.get("/activities/{age_group}")
def activities(age_group: str) -> dict:
    try:
        allowed = activities_for_group(age_group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"age_group": age_group, "activities": allowed}


@app.post("/api/v1/log-event")
def log_frontend_event(payload: FrontendLogEvent) -> dict:
    logger.info(
        "FRONTEND_EVENT | event=%s | activity=%s | age_group=%s | name=%s | details=%s",
        payload.event,
        payload.activity,
        payload.age_group,
        payload.name,
        payload.details,
    )
    return {"ok": True}


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(
    name: str = Form(...),
    age: int = Form(...),
    age_group: str = Form(...),
    activity: str = Form(...),
    gender: str = Form("male"),
    jumped_length: float | None = Form(None),
    request_id: str | None = Form(None),
    file: UploadFile = File(...),
) -> AnalyzeResponse:
    return await _analyze_internal(
        name=name,
        age=age,
        age_group=age_group,
        activity=activity,
        gender=gender,
        jumped_length=jumped_length,
        request_id=request_id,
        file=file,
    )


@app.post("/api/v1/analyze/{activity_name}", response_model=AnalyzeResponse)
async def analyze_by_activity(
    activity_name: str,
    name: str = Form(...),
    age: int = Form(...),
    age_group: str = Form(...),
    gender: str = Form("male"),
    jumped_length: float | None = Form(None),
    request_id: str | None = Form(None),
    file: UploadFile = File(...),
) -> AnalyzeResponse:
    return await _analyze_internal(
        name=name,
        age=age,
        age_group=age_group,
        activity=activity_name,
        gender=gender,
        jumped_length=jumped_length,
        request_id=request_id,
        file=file,
    )


@app.get("/api/v1/progress/{request_id}")
def analyze_progress(request_id: str) -> dict:
    progress = get_progress(request_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Progress request not found.")
    return progress


async def _analyze_internal(
    name: str,
    age: int,
    age_group: str,
    activity: str,
    gender: str,
    jumped_length: float | None,
    request_id: str | None,
    file: UploadFile,
) -> AnalyzeResponse:
    try:
        if not name.strip():
            raise HTTPException(status_code=400, detail="Name is required.")
        logger.info(
            "REQUEST_START | activity=%s | age_group=%s | age=%s | name=%s",
            activity,
            age_group,
            age,
            name.strip(),
        )

        try:
            validate_age_in_group(age_group, age)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        validate_activity_for_group(age_group, activity)

        if activity == "long_jump" and jumped_length is None:
            raise HTTPException(
                status_code=400,
                detail="Jumped distance is required for long jump.",
            )

        if not file.filename:
            raise HTTPException(status_code=400, detail="Video file name is missing.")

        ext = Path(file.filename).suffix.lower()
        if ext not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
            raise HTTPException(status_code=400, detail="Unsupported video format.")

        target_dir = UPLOAD_ROOT / age_group / activity
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = "_".join(name.strip().split())
        out_path = target_dir / f"{timestamp}_{safe_name}_{uuid.uuid4().hex[:8]}{ext}"

        try:
            content = await file.read()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to read uploaded video: {exc}") from exc
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded video is empty.")
        try:
            out_path.write_bytes(content)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded video: {exc}") from exc
        logger.info("VIDEO_SAVED | activity=%s | video_path=%s", activity, out_path)

        resolved_request_id = request_id or uuid.uuid4().hex
        try:
            video_stats = read_video_stats(str(out_path))
            frame_count = int(video_stats.frame_count)
        except Exception:
            frame_count = 0
        pass_multiplier = 2 if activity == "shuttle_run" else 1
        initialize_progress(
            request_id=resolved_request_id,
            activity=activity,
            video_path=str(out_path),
            total_frames=frame_count,
            expected_reads=max(1, frame_count * pass_multiplier),
        )
        set_progress_message(resolved_request_id, "Video uploaded. Starting analysis", status="processing")

        candidate_id = f"DC{uuid.uuid4().hex[:8].upper()}"
        try:
            result = await asyncio.to_thread(
                score_activity_video,
                activity=activity,
                video_path=out_path,
                age_group=age_group,
                candidate_id=candidate_id,
                candidate_name=name.strip(),
                age=age,
                gender=gender,
                jumped_length=jumped_length,
                progress_request_id=resolved_request_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info(
            "SCORING_DONE | activity=%s | candidate_id=%s | score=%s | category=%s",
            activity,
            candidate_id,
            result.score,
            result.category,
        )

        record = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "candidate_id": candidate_id,
            "name": name.strip(),
            "age": age,
            "age_group": age_group,
            "activity": activity,
            "gender": gender,
            "jumped_length": jumped_length,
            "score": result.score,
            "max_score": result.max_score,
            "category": result.category,
            "duration_seconds": result.duration_seconds,
            "video_path": str(out_path),
        }
        saved_path = append_score_record(record)
        csv_result = read_latest_csv_row(
            activity,
            candidate_id=candidate_id,
            video_path=str(out_path),
        )
        activity_metrics = extract_calculation_variables(activity, csv_result)
        if activity_metrics is None:
            activity_metrics = {}
        activity_metrics["Category"] = record["category"]
        if activity == "long_jump" and jumped_length is not None:
            activity_metrics["Jumped_distance_cm"] = float(jumped_length)
        mongo_status = persist_record_to_mongodb(record=record, csv_result=csv_result)
        if not mongo_status.get("ok"):
            logger.warning(
                "MONGO_SAVE_FAILED | activity=%s | candidate_id=%s | error=%s",
                activity,
                candidate_id,
                mongo_status.get("error"),
            )
        else:
            logger.info(
                "MONGO_SAVE_OK | activity=%s | candidate_id=%s | collections=%s",
                activity,
                candidate_id,
                ",".join(mongo_status.get("collections", [])),
            )
        logger.info(
            "REQUEST_DONE | activity=%s | candidate_id=%s | saved_json=%s",
            activity,
            candidate_id,
            saved_path,
        )

        return AnalyzeResponse(
            name=record["name"],
            age=record["age"],
            age_group=record["age_group"],
            activity=record["activity"],
            score=record["score"],
            max_score=record["max_score"],
            category=record["category"],
            duration_seconds=record["duration_seconds"],
            video_path=record["video_path"],
            saved_record_path=str(saved_path),
            csv_result=csv_result,
            activity_metrics=activity_metrics,
        )
    except HTTPException:
        logger.exception(
            "REQUEST_HTTP_ERROR | activity=%s | age_group=%s | age=%s | name=%s",
            activity,
            age_group,
            age,
            name.strip() if isinstance(name, str) else name,
        )
        raise
    except Exception as exc:
        traceback.print_exc()
        logger.exception(
            "REQUEST_FATAL_ERROR | activity=%s | age_group=%s | age=%s | name=%s | error=%s",
            activity,
            age_group,
            age,
            name.strip() if isinstance(name, str) else name,
            exc,
        )
        raise HTTPException(status_code=500, detail=f"Failed to analyze video: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("common_backend.app:app", host="0.0.0.0", port=8000, reload=True)
