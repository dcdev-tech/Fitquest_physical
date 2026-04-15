from __future__ import annotations

import os
import tempfile
import traceback
import uuid
from datetime import datetime
from pathlib import Path
import asyncio

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel

from .config import (
    AGE_GROUPS,
    ACTIVITY_DURATION_SECONDS,
    ACTIVITY_LABELS,
    activities_for_group,
    canonical_age_group,
    validate_age_in_group,
    validate_activity_for_group,
)
from .assessment_metrics import DUAL_TRIAL_ACTIVITIES, build_assessment_metrics
from .schemas import AnalyzeResponse
from .csv_results import read_latest_csv_row
from .scoring import score_activity_video
from .storage import (
    append_score_record,
    get_video_bytes_from_mongodb,
    initialize_mongodb_schema,
    mongo_connection_status,
    persist_record_to_mongodb,
)
from .logging_utils import get_activity_logger
from .progress import get_progress, initialize_progress, set_progress_message
from activity_common.video_base import read_video_stats

app = FastAPI(title="Child Activity Assessment API", version="1.0.0")
logger = get_activity_logger()


@app.on_event("startup")
def startup_initialize_services() -> None:
    mongo_status = initialize_mongodb_schema()
    if mongo_status.get("ok"):
        logger.info(
            "MONGO_SCHEMA_INIT_OK | db=%s | created=%s",
            mongo_status.get("db"),
            ",".join(mongo_status.get("created_collections", [])) or "none",
        )
    else:
        logger.warning(
            "MONGO_SCHEMA_INIT_SKIPPED | db=%s | error=%s",
            mongo_status.get("db"),
            mongo_status.get("error"),
        )


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

TEMP_UPLOAD_DIR = Path(os.getenv("TEMP_UPLOAD_DIR", tempfile.gettempdir())) / "fitquest_processing"
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health")
def health() -> dict:
    mongo_status = mongo_connection_status()
    overall_ok = bool(mongo_status.get("ok") or not mongo_status.get("configured"))
    return {
        "status": "ok" if overall_ok else "degraded",
        "mongo": mongo_status,
    }


@app.get("/metadata")
def metadata() -> dict:
    return {
        "age_groups": AGE_GROUPS,
        "activities": ACTIVITY_LABELS,
        "durations_seconds": ACTIVITY_DURATION_SECONDS,
    }


@app.get("/api/v1/video/{candidate_id}/{trial_no}")
def get_saved_video(candidate_id: str, trial_no: int, activity: str | None = None) -> Response:
    status = get_video_bytes_from_mongodb(
        candidate_id=candidate_id,
        trial_no=trial_no,
        activity=activity,
    )
    if not status.get("ok"):
        raise HTTPException(status_code=404, detail=status.get("error") or "Stored video not found.")
    filename = str(status.get("filename") or f"{candidate_id}_trial{trial_no}.mp4")
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return Response(
        content=status["content"],
        media_type=str(status.get("content_type") or "application/octet-stream"),
        headers=headers,
    )


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
    jumped_length_2: float | None = Form(None),
    landing_stability: int | None = Form(None),
    landing_stability_2: int | None = Form(None),
    request_id: str | None = Form(None),
    file: UploadFile = File(...),
    file_2: UploadFile | None = File(None),
) -> AnalyzeResponse:
    return await _analyze_internal(
        name=name,
        age=age,
        age_group=age_group,
        activity=activity,
        gender=gender,
        jumped_length=jumped_length,
        jumped_length_2=jumped_length_2,
        landing_stability=landing_stability,
        landing_stability_2=landing_stability_2,
        request_id=request_id,
        file=file,
        file_2=file_2,
    )


@app.post("/api/v1/analyze/{activity_name}", response_model=AnalyzeResponse)
async def analyze_by_activity(
    activity_name: str,
    name: str = Form(...),
    age: int = Form(...),
    age_group: str = Form(...),
    gender: str = Form("male"),
    jumped_length: float | None = Form(None),
    jumped_length_2: float | None = Form(None),
    landing_stability: int | None = Form(None),
    landing_stability_2: int | None = Form(None),
    request_id: str | None = Form(None),
    file: UploadFile = File(...),
    file_2: UploadFile | None = File(None),
) -> AnalyzeResponse:
    return await _analyze_internal(
        name=name,
        age=age,
        age_group=age_group,
        activity=activity_name,
        gender=gender,
        jumped_length=jumped_length,
        jumped_length_2=jumped_length_2,
        landing_stability=landing_stability,
        landing_stability_2=landing_stability_2,
        request_id=request_id,
        file=file,
        file_2=file_2,
    )


@app.get("/api/v1/progress/{request_id}")
def analyze_progress(request_id: str) -> dict:
    progress = get_progress(request_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Progress request not found.")
    return progress


async def _read_upload_content(upload: UploadFile, label: str) -> bytes:
    try:
        content = await upload.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read {label}: {exc}") from exc
    if not content:
        raise HTTPException(status_code=400, detail=f"Uploaded {label} is empty.")
    return content


def _save_upload_content(*, content: bytes, file_name: str, target_dir: Path, name: str, suffix: str) -> Path:
    ext = Path(file_name).suffix.lower()
    if ext not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail=f"Unsupported video format for {file_name}.")
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = "_".join(name.strip().split())
    out_path = target_dir / f"{timestamp}_{safe_name}_{suffix}_{uuid.uuid4().hex[:8]}{ext}"
    try:
        out_path.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded video: {exc}") from exc
    return out_path


def _candidate_label(candidate_id: str, index: int) -> str:
    return f"{candidate_id}T{index + 1}"


def _build_csv_result_payload(
    *,
    activity: str,
    trial_csv_results: list[dict | None],
    jumped_lengths: list[float | None],
) -> dict | None:
    usable = [item for item in trial_csv_results if isinstance(item, dict)]
    if not usable:
        return None
    if activity != "long_jump":
        return usable[0]
    best_index = 0
    numeric_distances = [float(value or 0.0) for value in jumped_lengths]
    if numeric_distances:
        best_index = max(range(len(numeric_distances)), key=lambda idx: numeric_distances[idx])
    if best_index < len(trial_csv_results) and isinstance(trial_csv_results[best_index], dict):
        return trial_csv_results[best_index]
    return usable[0]


async def _analyze_internal(
    name: str,
    age: int,
    age_group: str,
    activity: str,
    gender: str,
    jumped_length: float | None,
    jumped_length_2: float | None,
    landing_stability: int | None,
    landing_stability_2: int | None,
    request_id: str | None,
    file: UploadFile,
    file_2: UploadFile | None,
) -> AnalyzeResponse:
    out_paths: list[Path] = []
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
        age_group = canonical_age_group(age_group)

        try:
            validate_age_in_group(age_group, age)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        validate_activity_for_group(age_group, activity)

        if activity == "long_jump" and jumped_length is None:
            raise HTTPException(
                status_code=400,
                detail="Trial 1 jumped distance is required for long jump.",
            )

        if not file.filename:
            raise HTTPException(status_code=400, detail="Video file name is missing.")

        target_dir = TEMP_UPLOAD_DIR / age_group / activity
        target_dir.mkdir(parents=True, exist_ok=True)

        resolved_request_id = request_id or uuid.uuid4().hex
        primary_content = await _read_upload_content(file, "video")
        secondary_content = None
        if file_2 and file_2.filename:
            secondary_content = await _read_upload_content(file_2, "second video")
        elif activity in DUAL_TRIAL_ACTIVITIES:
            secondary_content = primary_content

        uploads: list[tuple[UploadFile, bytes]] = [(file, primary_content)]
        if secondary_content is not None:
            uploads.append((file_2 or file, secondary_content))

        frame_counts: list[int] = []
        mongo_video_uploads: list[dict[str, object]] = []
        for index, (upload_obj, content) in enumerate(uploads):
            out_path = _save_upload_content(
                content=content,
                file_name=upload_obj.filename or file.filename,
                target_dir=target_dir,
                name=name,
                suffix=f"trial{index + 1}",
            )
            out_paths.append(out_path)
            logger.info("VIDEO_SAVED | activity=%s | trial=%s | video_path=%s", activity, index + 1, out_path)
            mongo_video_uploads.append(
                {
                    "trial_no": index + 1,
                    "filename": upload_obj.filename or file.filename,
                    "content_type": upload_obj.content_type or "application/octet-stream",
                    "content": content,
                    "video_path": str(out_path),
                }
            )
            try:
                video_stats = read_video_stats(str(out_path))
                frame_counts.append(int(video_stats.frame_count))
            except Exception:
                frame_counts.append(0)

        pass_multiplier = 2 if activity == "shuttle_run" else 1
        initialize_progress(
            request_id=resolved_request_id,
            activity=activity,
            video_path=str(out_paths[0]),
            total_frames=sum(frame_counts),
            expected_reads=max(1, sum(frame_counts) * pass_multiplier),
        )
        set_progress_message(resolved_request_id, "Video uploaded. Starting analysis", status="processing")

        candidate_id = f"DC{uuid.uuid4().hex[:8].upper()}"
        jumped_lengths = [jumped_length]
        landing_stabilities = [landing_stability]
        if len(out_paths) > 1:
            jumped_lengths.append(jumped_length_2 if jumped_length_2 is not None else jumped_length)
            landing_stabilities.append(
                landing_stability_2 if landing_stability_2 is not None else landing_stability
            )

        trial_results = []
        trial_csv_results = []
        trial_durations = []
        for index, out_path in enumerate(out_paths):
            trial_candidate_id = _candidate_label(candidate_id, index)
            try:
                result = await asyncio.to_thread(
                    score_activity_video,
                    activity=activity,
                    video_path=out_path,
                    age_group=age_group,
                    candidate_id=trial_candidate_id,
                    candidate_name=name.strip(),
                    age=age,
                    gender=gender,
                    jumped_length=jumped_lengths[index] if index < len(jumped_lengths) else jumped_length,
                    progress_request_id=resolved_request_id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            logger.info(
                "SCORING_DONE | activity=%s | candidate_id=%s | trial=%s | score=%s | category=%s",
                activity,
                trial_candidate_id,
                index + 1,
                result.score,
                result.category,
            )
            csv_result = read_latest_csv_row(
                activity,
                candidate_id=trial_candidate_id,
                video_path=str(out_path),
            )
            trial_results.append(result)
            trial_csv_results.append(csv_result)
            trial_durations.append(result.duration_seconds)

        metrics_source_rows = [
            csv_item.get("row", {}) if isinstance(csv_item, dict) else {}
            for csv_item in trial_csv_results
        ]
        activity_metrics, computed_score, computed_max_score, computed_category = build_assessment_metrics(
            activity=activity,
            age_group=age_group,
            candidate_name=name.strip(),
            age=age,
            gender=gender,
            trial_rows=metrics_source_rows,
            trial_durations=trial_durations,
            jumped_lengths=jumped_lengths,
            landing_stabilities=landing_stabilities,
        )
        primary_csv_result = _build_csv_result_payload(
            activity=activity,
            trial_csv_results=trial_csv_results,
            jumped_lengths=jumped_lengths,
        )
        computed_duration = round(sum(trial_durations) / max(1, len(trial_durations)), 2)

        record = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "candidate_id": candidate_id,
            "name": name.strip(),
            "age": age,
            "age_group": age_group,
            "activity": activity,
            "gender": gender,
            "jumped_length": jumped_length,
            "jumped_length_2": jumped_length_2,
            "landing_stability": landing_stability,
            "landing_stability_2": landing_stability_2,
            "score": computed_score,
            "max_score": computed_max_score,
            "category": computed_category,
            "duration_seconds": computed_duration,
            "video_path": f"mongodb://video_files/{candidate_id}/trial1",
            "video_path_2": f"mongodb://video_files/{candidate_id}/trial2" if len(out_paths) > 1 else None,
            "activity_metrics": activity_metrics,
        }
        saved_path = append_score_record(record)
        mongo_status = persist_record_to_mongodb(
            record=record,
            csv_result=primary_csv_result,
            video_uploads=mongo_video_uploads,
        )
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
            csv_result=primary_csv_result,
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
    finally:
        for path in out_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("common_backend.app:app", host="0.0.0.0", port=8000, reload=True)
