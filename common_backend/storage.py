from pathlib import Path
import ast
import json
import os
from typing import Dict, Any, List

from .logging_utils import get_activity_logger

RESULTS_DIR = Path("common_backend") / "results"
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", str(RESULTS_DIR)))
SCORES_FILE = RESULTS_DIR / "scores.json"
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "FitQuest_Physical_database")
logger = get_activity_logger()

STORAGE_ACTIVITIES = (
    "high_knee_jump",
    "shuttle_run",
    "sprint_run_20m",
    "long_jump",
    "running",
    "galloping",
    "hopping",
    "skipping",
    "jumping",
    "bead_threading",
    "block_stacking",
    "ball_catch",
    "peg_board",
    "visual_integration",
    "beads_fm",
    "agility_ladder",
    "agility_test",
)


def mongo_uri_configured() -> bool:
    return bool(str(os.getenv("MONGO_URI", "")).strip())


def ensure_storage() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not SCORES_FILE.exists():
        SCORES_FILE.write_text("[]", encoding="utf-8")


def append_score_record(record: Dict[str, Any]) -> Path:
    ensure_storage()
    existing: List[Dict[str, Any]]
    try:
        existing = json.loads(SCORES_FILE.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    except json.JSONDecodeError:
        existing = []

    existing.append(record)
    SCORES_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return SCORES_FILE


def _normalized_mongo_uri(uri: str) -> str:
    # User-provided URI can come as mongodb://localhost://27017; normalize it.
    if uri.startswith("mongodb://localhost://"):
        return uri.replace("mongodb://localhost://", "mongodb://localhost:", 1)
    return uri


def _mongo_client():
    from pymongo import MongoClient

    raw_uri = str(os.getenv("MONGO_URI", "")).strip()
    if not raw_uri:
        raise ValueError("MONGO_URI is not configured.")
    uri = _normalized_mongo_uri(raw_uri)
    return MongoClient(uri, serverSelectionTimeoutMS=3000)


def mongo_connection_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "configured": mongo_uri_configured(),
        "ok": False,
        "db": MONGO_DB_NAME,
        "error": None,
    }
    if not status["configured"]:
        status["error"] = "MONGO_URI is not configured."
        return status
    try:
        client = _mongo_client()
        client.admin.command("ping")
        resolved_db_name = _resolve_db_name(client)
        status["db"] = resolved_db_name
        status["ok"] = True
        return status
    except Exception as exc:
        status["error"] = str(exc)
        return status


def initialize_mongodb_schema() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "ok": False,
        "db": MONGO_DB_NAME,
        "created_collections": [],
        "error": None,
    }
    if not mongo_uri_configured():
        status["error"] = "MONGO_URI is not configured."
        return status
    try:
        client = _mongo_client()
        client.admin.command("ping")
        resolved_db_name = _resolve_db_name(client)
        status["db"] = resolved_db_name
        db = client[resolved_db_name]

        required_collections = {
            "users",
            "children",
            "data_storage",
            "video_files.files",
            "video_files.chunks",
        }
        for activity in STORAGE_ACTIVITIES:
            required_collections.add(_activity_collection_name(activity))
            required_collections.add(_activity_vars_collection_name(activity))
            required_collections.add(_video_metadata_collection_name(activity))

        existing = set(db.list_collection_names())
        for collection_name in sorted(required_collections):
            if collection_name not in existing:
                db.create_collection(collection_name)
                status["created_collections"].append(collection_name)

        db["users"].create_index("name", unique=True)
        db["children"].create_index("candidate_id", unique=True)
        db["data_storage"].create_index("candidate_id")
        db["video_files.files"].create_index("metadata.candidate_id")
        db["video_files.files"].create_index("metadata.activity")

        for activity in STORAGE_ACTIVITIES:
            db[_activity_collection_name(activity)].create_index("candidate_id")
            db[_activity_vars_collection_name(activity)].create_index("candidate_id")
            db[_video_metadata_collection_name(activity)].create_index("candidate_id")
            db[_video_metadata_collection_name(activity)].create_index("gridfs_file_id")

        status["ok"] = True
        return status
    except Exception as exc:
        status["error"] = str(exc)
        logger.exception("MONGO_SCHEMA_INIT_FAIL | error=%s", exc)
        return status


def _activity_collection_name(activity: str) -> str:
    return f"{activity}_results"


def _activity_vars_collection_name(activity: str) -> str:
    return f"{activity}_calculation_variables"


def _video_metadata_collection_name(activity: str) -> str:
    return f"{activity}_video_metadata"


def _resolve_db_name(client) -> str:
    target = MONGO_DB_NAME
    try:
        existing_names = client.list_database_names()
    except Exception:
        return target

    lookup = {name.lower(): name for name in existing_names}
    return lookup.get(target.lower(), target)


def _parse_csv_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return text
    if text.startswith("[") and text.endswith("]"):
        try:
            return ast.literal_eval(text)
        except Exception:
            return text
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


NON_METRIC_KEYS = {
    "ID",
    "Name",
    "Video_path",
}


def extract_calculation_variables(activity: str, csv_result: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(csv_result, dict):
        return {}
    row = csv_result.get("row")
    if not isinstance(row, dict):
        return {}
    return {
        k: _parse_csv_value(v)
        for k, v in row.items()
        if k not in NON_METRIC_KEYS
    }


def save_videos_to_mongodb(
    *,
    db,
    record: Dict[str, Any],
    uploads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "ok": False,
        "saved": [],
        "error": None,
    }
    try:
        from gridfs import GridFS

        fs = GridFS(db, collection="video_files")
        video_metadata = db[_video_metadata_collection_name(record["activity"])]
        saved: List[Dict[str, Any]] = []
        for upload in uploads:
            content = upload.get("content")
            if not isinstance(content, (bytes, bytearray)):
                continue
            trial_no = int(upload.get("trial_no", 1))
            file_name = str(upload.get("filename") or f"trial_{trial_no}.mp4")
            metadata = {
                "candidate_id": record.get("candidate_id"),
                "activity": record.get("activity"),
                "age_group": record.get("age_group"),
                "name": record.get("name"),
                "age": record.get("age"),
                "gender": record.get("gender"),
                "trial_no": trial_no,
                "original_filename": file_name,
                "content_type": upload.get("content_type") or "application/octet-stream",
                "video_path": upload.get("video_path"),
                "uploaded_at": record.get("created_at"),
            }
            file_id = fs.put(
                content,
                filename=file_name,
                metadata=metadata,
                content_type=metadata["content_type"],
            )
            metadata_doc = dict(metadata)
            metadata_doc["gridfs_file_id"] = file_id
            video_metadata.insert_one(metadata_doc)
            saved.append(
                {
                    "trial_no": trial_no,
                    "gridfs_file_id": str(file_id),
                    "filename": file_name,
                    "video_path": upload.get("video_path"),
                }
            )
        status["saved"] = saved
        status["ok"] = True
        return status
    except Exception as exc:
        status["error"] = str(exc)
        logger.exception(
            "MONGO_VIDEO_SAVE_FAIL | activity=%s | candidate_id=%s | error=%s",
            record.get("activity"),
            record.get("candidate_id"),
            exc,
        )
        return status


def get_video_bytes_from_mongodb(
    *,
    candidate_id: str,
    trial_no: int = 1,
    activity: str | None = None,
) -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "ok": False,
        "content": None,
        "filename": None,
        "content_type": None,
        "error": None,
    }
    try:
        from bson import ObjectId
        from gridfs import GridFS

        if not mongo_uri_configured():
            status["error"] = "MONGO_URI is not configured."
            return status

        client = _mongo_client()
        client.admin.command("ping")
        resolved_db_name = _resolve_db_name(client)
        db = client[resolved_db_name]

        metadata_collections = (
            [_video_metadata_collection_name(activity)]
            if activity
            else [_video_metadata_collection_name(item) for item in STORAGE_ACTIVITIES]
        )

        metadata_doc = None
        for collection_name in metadata_collections:
            metadata_doc = db[collection_name].find_one(
                {"candidate_id": candidate_id, "trial_no": trial_no}
            )
            if metadata_doc:
                break
        if not metadata_doc:
            status["error"] = "Stored video metadata not found."
            return status

        gridfs_file_id = metadata_doc.get("gridfs_file_id")
        if not gridfs_file_id:
            status["error"] = "GridFS file id not found."
            return status

        fs = GridFS(db, collection="video_files")
        grid_out = fs.get(ObjectId(gridfs_file_id) if not isinstance(gridfs_file_id, ObjectId) else gridfs_file_id)
        status["content"] = grid_out.read()
        status["filename"] = metadata_doc.get("original_filename") or grid_out.filename
        status["content_type"] = metadata_doc.get("content_type") or getattr(grid_out, "content_type", None) or "application/octet-stream"
        status["ok"] = True
        return status
    except Exception as exc:
        status["error"] = str(exc)
        logger.exception(
            "MONGO_VIDEO_FETCH_FAIL | candidate_id=%s | trial_no=%s | activity=%s | error=%s",
            candidate_id,
            trial_no,
            activity,
            exc,
        )
        return status


def persist_record_to_mongodb(
    record: Dict[str, Any],
    csv_result: Dict[str, Any] | None,
    *,
    video_uploads: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Persist to MongoDB collections:
    - users
    - children
    - <activity>_results (activity-specific collection)
    - data_storage (CSV-equivalent storage)
    - video_files + <activity>_video_metadata for uploaded video binaries
    """
    status: Dict[str, Any] = {
        "ok": False,
        "db": MONGO_DB_NAME,
        "error": None,
        "collections": [],
    }

    try:
        from pymongo.errors import PyMongoError

        if not mongo_uri_configured():
            status["error"] = "MONGO_URI is not configured."
            logger.warning(
                "MONGO_WRITE_SKIPPED | activity=%s | candidate_id=%s | reason=%s",
                record.get("activity"),
                record.get("candidate_id"),
                status["error"],
            )
            return status

        client = _mongo_client()
        client.admin.command("ping")
        resolved_db_name = _resolve_db_name(client)
        status["db"] = resolved_db_name
        db = client[resolved_db_name]
        logger.info(
            "MONGO_CONNECT_OK | db=%s | activity=%s | candidate_id=%s",
            resolved_db_name,
            record.get("activity"),
            record.get("candidate_id"),
        )

        users = db["users"]
        children = db["children"]
        activity_results = db[_activity_collection_name(record["activity"])]
        activity_vars = db[_activity_vars_collection_name(record["activity"])]
        data_storage = db["data_storage"]

        if video_uploads:
            video_status = save_videos_to_mongodb(db=db, record=record, uploads=video_uploads)
            if not video_status.get("ok"):
                status["error"] = video_status.get("error")
                return status
            record["mongo_videos"] = video_status.get("saved", [])
            status["collections"].append("video_files")
            status["collections"].append(_video_metadata_collection_name(record["activity"]))
            logger.info(
                "MONGO_VIDEO_SAVE_OK | activity=%s | candidate_id=%s | count=%s",
                record.get("activity"),
                record.get("candidate_id"),
                len(video_status.get("saved", [])),
            )

        user_doc = {
            "name": record.get("name"),
            "updated_at": record.get("created_at"),
        }
        users.update_one({"name": user_doc["name"]}, {"$set": user_doc}, upsert=True)
        status["collections"].append("users")
        logger.info("MONGO_WRITE_OK | collection=users | candidate_id=%s", record.get("candidate_id"))

        child_doc = {
            "candidate_id": record.get("candidate_id"),
            "name": record.get("name"),
            "age": record.get("age"),
            "age_group": record.get("age_group"),
            "gender": record.get("gender"),
            "updated_at": record.get("created_at"),
        }
        children.update_one({"candidate_id": child_doc["candidate_id"]}, {"$set": child_doc}, upsert=True)
        status["collections"].append("children")
        logger.info("MONGO_WRITE_OK | collection=children | candidate_id=%s", record.get("candidate_id"))

        activity_results.insert_one(record)
        status["collections"].append(_activity_collection_name(record["activity"]))
        logger.info(
            "MONGO_WRITE_OK | collection=%s | candidate_id=%s",
            _activity_collection_name(record["activity"]),
            record.get("candidate_id"),
        )

        calc_vars_doc = {
            "created_at": record.get("created_at"),
            "candidate_id": record.get("candidate_id"),
            "activity": record.get("activity"),
            "age_group": record.get("age_group"),
            "name": record.get("name"),
            "calculation_variables": record.get("activity_metrics")
            or extract_calculation_variables(record["activity"], csv_result),
        }
        activity_vars.insert_one(calc_vars_doc)
        status["collections"].append(_activity_vars_collection_name(record["activity"]))
        logger.info(
            "MONGO_WRITE_OK | collection=%s | candidate_id=%s",
            _activity_vars_collection_name(record["activity"]),
            record.get("candidate_id"),
        )

        csv_row = (csv_result or {}).get("row") if isinstance(csv_result, dict) else None
        data_storage_doc = {
            "created_at": record.get("created_at"),
            "candidate_id": record.get("candidate_id"),
            "activity": record.get("activity"),
            "name": record.get("name"),
            "age": record.get("age"),
            "csv_row": csv_row,
            "record": record,
        }
        data_storage.insert_one(data_storage_doc)
        status["collections"].append("data_storage")
        logger.info("MONGO_WRITE_OK | collection=data_storage | candidate_id=%s", record.get("candidate_id"))

        status["ok"] = True
        return status
    except PyMongoError as exc:
        status["error"] = str(exc)
        logger.exception(
            "MONGO_WRITE_FAIL | db=%s | activity=%s | candidate_id=%s | error=%s",
            status.get("db"),
            record.get("activity"),
            record.get("candidate_id"),
            exc,
        )
        return status
    except Exception as exc:
        status["error"] = str(exc)
        logger.exception(
            "MONGO_WRITE_FAIL | db=%s | activity=%s | candidate_id=%s | error=%s",
            status.get("db"),
            record.get("activity"),
            record.get("candidate_id"),
            exc,
        )
        return status
