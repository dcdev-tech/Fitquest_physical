from __future__ import annotations

import os
import tempfile
import uuid
import base64
import json
import asyncio
import requests
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from google.cloud import storage

from .config import (
    AGE_GROUPS,
    ACTIVITY_DURATION_SECONDS,
    ACTIVITY_DURATION_SECONDS_BY_GROUP,
    ACTIVITY_LABELS,
    ACTIVITY_LABELS_BY_GROUP,
    activities_for_group,
    canonical_age_group,
    validate_age_in_group,
    validate_activity_for_group,
)
from .assessment_metrics import build_assessment_metrics
from .csv_results import read_latest_csv_row
from .scoring import score_activity_video
from .logging_utils import get_activity_logger
from .progress import get_progress, initialize_progress
from activity_common.video_base import read_video_stats
from .schemas import AnalyzeResponse

app = FastAPI(title="FitQuest ML Engine (Pub/Sub Worker)", version="2.0.0")
logger = get_activity_logger()

# --- Pub/Sub Payload Schemas ---
class PubSubMessage(BaseModel):
    data: str
    messageId: str
    attributes: dict | None = None

class PubSubPushPayload(BaseModel):
    message: PubSubMessage
    subscription: str

# --- Internal Configuration ---
TEMP_UPLOAD_DIR = Path(os.getenv("TEMP_UPLOAD_DIR", tempfile.gettempdir())) / "fitquest_processing"
TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GCS Helper ---
def download_from_gcs(gcs_uri: str, target_path: Path) -> Path:
    """Downloads a file from a gs:// URI to the local filesystem."""
    try:
        client = storage.Client()
        # Parse gs://bucket-name/path/to/file.mp4
        parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        blob_name = parts[1]
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(str(target_path))
        logger.info(f"GCS_DOWNLOAD_SUCCESS | uri={gcs_uri} | path={target_path}")
        return target_path
    except Exception as exc:
        raise Exception(f"Failed to download from GCS: {exc}")

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": "pubsub-worker"}


@app.get("/")
def root() -> dict:
    return {"status": "ok", "service": "FitQuest ML Engine"}


@app.get("/metadata")
def metadata() -> dict:
    return {
        "age_groups": AGE_GROUPS,
        "activities": ACTIVITY_LABELS,
        "activities_by_group": ACTIVITY_LABELS_BY_GROUP,
        "durations_seconds": ACTIVITY_DURATION_SECONDS,
        "durations_seconds_by_group": ACTIVITY_DURATION_SECONDS_BY_GROUP,
    }


@app.get("/activities/{age_group}")
def activities(age_group: str) -> dict:
    return {"age_group": canonical_age_group(age_group), "activities": activities_for_group(age_group)}


@app.get("/api/v1/progress/{request_id}")
def progress(request_id: str) -> dict:
    return get_progress(request_id) or {
        "request_id": request_id,
        "status": "pending",
        "progress_percent": 0,
        "message": "Waiting to start",
    }


@app.post("/api/v1/log-event")
async def log_event(request: Request) -> dict:
    payload = await request.json()
    logger.info(
        "FRONTEND_EVENT | event=%s | activity=%s | age_group=%s | details=%s",
        payload.get("event"),
        payload.get("activity"),
        payload.get("age_group"),
        payload.get("details"),
    )
    return {"ok": True}


def _metric_input(value: float | int | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _is_unknown_evaluation(score: float, category: str) -> bool:
    return float(score or 0) <= 0 and str(category or "").strip().lower() == "unknown"


def _build_response_payload(
    *,
    submission_id: str,
    activity: str,
    age_group: str,
    name: str,
    age: float,
    gender: str,
    trial_results: list,
    trial_csv_results: list,
    trial_durations: list[float],
    jumped_lengths: list[float | None],
    landing_stabilities: list[int | None] | None = None,
) -> dict:
    direct_metrics = getattr(trial_results[0], "activity_metrics", None) if trial_results else None
    if direct_metrics:
        computed_score = float(trial_results[0].score)
        computed_max_score = float(trial_results[0].max_score)
        computed_category = str(trial_results[0].category)
        activity_metrics = direct_metrics
    else:
        metrics_source_rows = [
            csv_item.get("row", {}) if isinstance(csv_item, dict) else {}
            for csv_item in trial_csv_results
        ]
        activity_metrics, computed_score, computed_max_score, computed_category = build_assessment_metrics(
            activity=activity,
            age_group=age_group,
            candidate_name=name,
            age=age,
            gender=gender,
            trial_rows=metrics_source_rows,
            trial_durations=trial_durations,
            jumped_lengths=jumped_lengths,
            landing_stabilities=landing_stabilities or [None] * max(1, len(trial_results)),
        )
        if trial_results and _is_unknown_evaluation(computed_score, computed_category):
            primary_result = trial_results[0]
            computed_score = float(primary_result.score)
            computed_max_score = float(primary_result.max_score)
            computed_category = str(primary_result.category)
            activity_metrics = getattr(primary_result, "activity_metrics", None) or {
                "Final Score": {"score": computed_score, "maxValue": computed_max_score},
                "Final Marking": computed_category,
            }
    computed_duration = round(sum(trial_durations) / max(1, len(trial_durations)), 2)
    return {
        "submissionId": submission_id,
        "status": "completed",
        "evaluation": {
            "score": computed_score,
            "max_score": computed_max_score,
            "category": computed_category,
            "duration_seconds": computed_duration,
            "activity_metrics": activity_metrics,
        },
    }


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze_video(
    request_id: str | None = Form(None),
    name: str = Form(...),
    age: float = Form(...),
    age_group: str = Form(...),
    activity: str = Form(...),
    gender: str = Form("male"),
    jumped_length: float | None = Form(None),
    jumped_length_2: float | None = Form(None),
    landing_stability: int | None = Form(None),
    landing_stability_2: int | None = Form(None),
    blocks_stood: int | None = Form(None),
    blocks_dropped: int | None = Form(None),
    beads_threaded: int | None = Form(None),
    beads_dropped: int | None = Form(None),
    ball_catches: int | None = Form(None),
    ball_drops: int | None = Form(None),
    peg_count: int | None = Form(None),
    peg_drop_count: int | None = Form(None),
    bead_drop_count: int | None = Form(None),
    ladder_box_count: int | None = Form(None),
    file: UploadFile = File(...),
    file_2: UploadFile | None = File(None),
) -> AnalyzeResponse:
    out_paths: list[Path] = []
    try:
        request_id = request_id or uuid.uuid4().hex
        age_group = canonical_age_group(age_group)
        validate_age_in_group(age_group, age)
        validate_activity_for_group(age_group, activity)
        if activity == "long_jump" and jumped_length is None:
            raise ValueError("Trial 1 jumped distance is required for long jump.")
        if activity == "block_stacking" and (blocks_stood is None or blocks_dropped is None):
            raise ValueError("Blocks stood and blocks dropped are required for block stacking.")
        if activity == "bead_threading" and (beads_threaded is None or beads_dropped is None):
            raise ValueError("Beads threaded and beads dropped are required for bead threading.")
        if activity == "ball_catch" and (ball_catches is None or ball_drops is None):
            raise ValueError("Ball catch and drop counts are required for ball catch.")
        if activity == "peg_board" and peg_count is None:
            raise ValueError("Peg count is required for peg board.")
        if activity == "beads_fm" and beads_threaded is None:
            raise ValueError("Beads threaded is required for Beads FM.")
        if activity == "agility_ladder" and ladder_box_count is None:
            raise ValueError("Ladder box count is required for agility ladder.")

        target_dir = TEMP_UPLOAD_DIR / age_group / activity / request_id
        target_dir.mkdir(parents=True, exist_ok=True)

        uploads = [file]
        if file_2 is not None:
            uploads.append(file_2)

        for index, upload in enumerate(uploads, start=1):
            ext = Path(upload.filename or "").suffix.lower() or ".webm"
            path = target_dir / f"trial{index}{ext}"
            path.write_bytes(await upload.read())
            out_paths.append(path)

        stats = None if activity == "visual_integration" else read_video_stats(out_paths[0])
        initialize_progress(
            request_id=request_id,
            activity=activity,
            video_path=str(out_paths[0]),
            total_frames=stats.frame_count if stats else 1,
            expected_reads=max(1, stats.frame_count if stats else 1),
        )

        jumped_lengths = [jumped_length]
        if len(out_paths) > 1:
            jumped_lengths.append(jumped_length_2 if jumped_length_2 is not None else jumped_length)

        trial_results = []
        trial_csv_results = []
        trial_durations = []
        for index, out_path in enumerate(out_paths):
            trial_candidate_id = f"{request_id}_T{index + 1}"
            result = await asyncio.to_thread(
                score_activity_video,
                activity=activity,
                video_path=out_path,
                age_group=age_group,
                candidate_id=trial_candidate_id,
                candidate_name=name,
                age=age,
                gender=gender,
                jumped_length=jumped_lengths[index] if index < len(jumped_lengths) else jumped_length,
                blocks_stood=_metric_input(blocks_stood),
                blocks_dropped=_metric_input(blocks_dropped),
                beads_threaded=_metric_input(beads_threaded),
                beads_dropped=_metric_input(beads_dropped),
                ball_catches=_metric_input(ball_catches),
                ball_drops=_metric_input(ball_drops),
                peg_count=_metric_input(peg_count),
                peg_drop_count=_metric_input(peg_drop_count),
                bead_drop_count=_metric_input(bead_drop_count),
                ladder_box_count=_metric_input(ladder_box_count),
                progress_request_id=request_id,
            )
            trial_results.append(result)
            trial_csv_results.append(read_latest_csv_row(activity, candidate_id=trial_candidate_id, video_path=str(out_path)))
            trial_durations.append(result.duration_seconds)

        payload = _build_response_payload(
            submission_id=request_id,
            activity=activity,
            age_group=age_group,
            name=name,
            age=age,
            gender=gender,
            trial_results=trial_results,
            trial_csv_results=trial_csv_results,
            trial_durations=trial_durations,
            jumped_lengths=jumped_lengths,
            landing_stabilities=[landing_stability, landing_stability_2],
        )
        evaluation = payload["evaluation"]
        return AnalyzeResponse(
            name=name,
            age=age,
            age_group=age_group,
            activity=activity,
            score=evaluation["score"],
            max_score=evaluation["max_score"],
            category=evaluation["category"],
            duration_seconds=evaluation["duration_seconds"],
            csv_result=trial_csv_results[0] if trial_csv_results else None,
            activity_metrics=evaluation["activity_metrics"],
        )
    except Exception as exc:
        logger.exception("ANALYZE_FAIL | activity=%s | request_id=%s | error=%s", activity, request_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        for path in out_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

# --- The New Async Pub/Sub Endpoint ---
@app.post("/pubsub/process-activity", status_code=200)
async def process_activity_pubsub(payload: PubSubPushPayload):
    out_paths: list[Path] = []
    try:
        # 1. Decode the Pub/Sub base64 message
        decoded_data = base64.b64decode(payload.message.data).decode('utf-8')
        job_data = json.loads(decoded_data)
        
        submission_id = job_data.get("submissionId")
        media_url = job_data.get("mediaUrl")  # Expected: gs://bucket/path.mp4
        media_url_2 = job_data.get("mediaUrl2") # Optional second trial
        activity = job_data.get("activityType")
        webhook_url = job_data.get("webhookUrl")
        child_details = job_data.get("childDetails", {})
        
        name = child_details.get("name", "Unknown")
        age = float(child_details.get("age", 0))
        age_group = canonical_age_group(child_details.get("age_group", ""))
        gender = child_details.get("gender", "male")
        jumped_length = child_details.get("jumped_length")
        jumped_length_2 = child_details.get("jumped_length_2")
        blocks_stood = child_details.get("blocks_stood")
        blocks_dropped = child_details.get("blocks_dropped")
        beads_threaded = child_details.get("beads_threaded")
        beads_dropped = child_details.get("beads_dropped")
        ball_catches = child_details.get("ball_catches")
        ball_drops = child_details.get("ball_drops")
        peg_count = child_details.get("peg_count")
        peg_drop_count = child_details.get("peg_drop_count")
        bead_drop_count = child_details.get("bead_drop_count")
        ladder_box_count = child_details.get("ladder_box_count")

        logger.info(f"PUBSUB_JOB_START | submissionId={submission_id} | activity={activity}")

        # 2. Validation
        validate_age_in_group(age_group, age)
        validate_activity_for_group(age_group, activity)
        if activity == "long_jump" and jumped_length is None:
            raise ValueError("Trial 1 jumped distance is required for long jump.")
        if activity == "block_stacking" and (blocks_stood is None or blocks_dropped is None):
            raise ValueError("Blocks stood and blocks dropped are required for block stacking.")
        if activity == "bead_threading" and (beads_threaded is None or beads_dropped is None):
            raise ValueError("Beads threaded and beads dropped are required for bead threading.")
        if activity == "ball_catch" and (ball_catches is None or ball_drops is None):
            raise ValueError("Ball catch and drop counts are required for ball catch.")
        if activity == "peg_board" and peg_count is None:
            raise ValueError("Peg count is required for peg board.")
        if activity == "beads_fm" and beads_threaded is None:
            raise ValueError("Beads threaded is required for Beads FM.")
        if activity == "agility_ladder" and ladder_box_count is None:
            raise ValueError("Ladder box count is required for agility ladder.")

        # 3. Securely Download Video(s) from GCS
        target_dir = TEMP_UPLOAD_DIR / age_group / activity / submission_id
        target_dir.mkdir(parents=True, exist_ok=True)
        
        ext = Path(media_url).suffix.lower() or ".mp4"
        primary_path = target_dir / f"trial1{ext}"
        download_from_gcs(media_url, primary_path)
        out_paths.append(primary_path)
        
        if media_url_2:
            ext_2 = Path(media_url_2).suffix.lower() or ".mp4"
            secondary_path = target_dir / f"trial2{ext_2}"
            download_from_gcs(media_url_2, secondary_path)
            out_paths.append(secondary_path)

        # 4. Execute ML Processing Pipeline
        jumped_lengths = [jumped_length]
        if media_url_2:
            jumped_lengths.append(jumped_length_2 if jumped_length_2 is not None else jumped_length)

        trial_results = []
        trial_csv_results = []
        trial_durations = []
        
        for index, out_path in enumerate(out_paths):
            trial_candidate_id = f"{submission_id}_T{index+1}"
            result = await asyncio.to_thread(
                score_activity_video,
                activity=activity,
                video_path=out_path,
                age_group=age_group,
                candidate_id=trial_candidate_id,
                candidate_name=name,
                age=age,
                gender=gender,
                jumped_length=jumped_lengths[index] if index < len(jumped_lengths) else jumped_length,
                blocks_stood=_metric_input(blocks_stood),
                blocks_dropped=_metric_input(blocks_dropped),
                beads_threaded=_metric_input(beads_threaded),
                beads_dropped=_metric_input(beads_dropped),
                ball_catches=_metric_input(ball_catches),
                ball_drops=_metric_input(ball_drops),
                peg_count=_metric_input(peg_count),
                peg_drop_count=_metric_input(peg_drop_count),
                bead_drop_count=_metric_input(bead_drop_count),
                ladder_box_count=_metric_input(ladder_box_count),
                progress_request_id=submission_id,
            )
            csv_result = read_latest_csv_row(activity, candidate_id=trial_candidate_id, video_path=str(out_path))
            trial_results.append(result)
            trial_csv_results.append(csv_result)
            trial_durations.append(result.duration_seconds)

        payload_response = _build_response_payload(
            submission_id=submission_id,
            activity=activity,
            age_group=age_group,
            name=name,
            age=age,
            gender=gender,
            trial_results=trial_results,
            trial_csv_results=trial_csv_results,
            trial_durations=trial_durations,
            jumped_lengths=jumped_lengths,
            landing_stabilities=[None] * len(out_paths),
        )
        evaluation = payload_response["evaluation"]

        # 5. Construct Final Payload
        final_payload = {
            "submissionId": submission_id,
            "status": "completed",
            "evaluation": evaluation,
        }

        # 6. Post Webhook back to Node.js Backend
        if webhook_url:
            response = requests.post(webhook_url, json=final_payload, timeout=10)
            response.raise_for_status()
            logger.info(f"WEBHOOK_SUCCESS | submissionId={submission_id}")

        return {"status": "success", "message": "Job processed and webhook fired."}

    except requests.exceptions.RequestException as exc:
        logger.error(f"WEBHOOK_FAILED | submissionId={submission_id} | error={exc}")
        # Raising an exception will cause a 500, making Pub/Sub retry the message
        raise HTTPException(status_code=500, detail="Failed to deliver webhook.")
    
    except Exception as exc:
        # print("\n" + "="*50)
        # print("ML ENGINE CRASHED! HERE IS THE EXACT REASON:")
        # traceback.print_exc()
        # print("="*50 + "\n")
        logger.exception(f"PUBSUB_JOB_FATAL_ERROR | error={exc}")
        raise HTTPException(status_code=500, detail=str(exc))
        
    finally:
        # Crucial stateless cleanup
        for path in out_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("common_backend.app:app", host="0.0.0.0", port=port, reload=False)
