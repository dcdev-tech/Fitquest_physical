from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

# Ensure project root is importable when streamlit is launched from subfolders.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common_backend.config import (
    ACTIVITY_DURATION_SECONDS,
    ACTIVITY_DURATION_SECONDS_BY_GROUP,
    ACTIVITY_LABELS,
    ACTIVITY_LABELS_BY_GROUP,
    AGE_GROUPS,
)


ANALYZE_TIMEOUT_SECONDS = 900
DUAL_TRIAL_ACTIVITIES = {"sprint_run_20m", "shuttle_run", "long_jump"}
IMAGE_UPLOAD_ACTIVITIES = {"visual_integration"}
PRESCHOOL_GROUP = "2.5-5"
PRESCHOOL_ACTIVITY_GROUPS = {
    "Gross Motor": ["running", "galloping", "hopping", "skipping", "jumping"],
    "Fine Motor": ["bead_threading", "block_stacking"],
}


def show_json_safe(value: object, *, fallback_message: str = "No data available.") -> None:
    if isinstance(value, (dict, list)):
        st.json(value)
        return
    if value is None:
        st.info(fallback_message)
        return
    st.write(value)


def user_visible_metrics(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {}
    activity_metrics = payload.get("activity_metrics")
    if isinstance(activity_metrics, dict) and activity_metrics:
        return activity_metrics

    csv_result = payload.get("csv_result")
    if not isinstance(csv_result, dict):
        return {}
    row = csv_result.get("row")
    if not isinstance(row, dict):
        return {}
    hidden = {"ID", "Name", "Video_path"}
    return {k: v for k, v in row.items() if k not in hidden}


def activity_duration_seconds(metadata: dict, age_group: str, activity: str) -> int:
    group_durations = metadata.get("durations_seconds_by_group", {}).get(age_group, {})
    return int(group_durations.get(activity, metadata["durations_seconds"].get(activity, 20)))


def activity_label(metadata: dict, age_group: str, activity: str) -> str:
    group_labels = metadata.get("activities_by_group", {}).get(age_group, {})
    return group_labels.get(activity, metadata["activities"].get(activity, activity))


def activity_option_label(metadata: dict, age_group: str, activity: str) -> str:
    duration = activity_duration_seconds(metadata, age_group, activity)
    return f"{activity_label(metadata, age_group, activity)} ({duration} sec)"

st.set_page_config(page_title="Child Activity Assessment", layout="wide")
st.title("Child Activity Assessment")

st.caption("Select age group and activity, record video for fixed duration, retry if needed, then upload for scoring.")

default_backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
backend_url = st.text_input("Backend URL", value=default_backend_url).rstrip("/")

metadata = {
    "age_groups": AGE_GROUPS,
    "activities": ACTIVITY_LABELS,
    "activities_by_group": ACTIVITY_LABELS_BY_GROUP,
    "durations_seconds": ACTIVITY_DURATION_SECONDS,
    "durations_seconds_by_group": ACTIVITY_DURATION_SECONDS_BY_GROUP,
}

try:
    response = requests.get(f"{backend_url}/metadata", timeout=5)
    response.raise_for_status()
    metadata = response.json()
except Exception:
    st.warning("Backend metadata not reachable, using local config.")

if "selected_age_group" not in st.session_state:
    st.session_state.selected_age_group = None
if "selected_activity" not in st.session_state:
    st.session_state.selected_activity = None

st.subheader("Step 1: Choose Age Group")
age_group_choice = st.selectbox("Age Group", list(metadata["age_groups"].keys()), key="age_group_choice")
if st.button("Confirm Age Group", type="primary"):
    st.session_state.selected_age_group = age_group_choice
    st.session_state.selected_activity = None

selected_age_group = st.session_state.selected_age_group
if not selected_age_group:
    st.info("Click 'Confirm Age Group' to continue.")
    st.stop()

allowed_activities = list(metadata["age_groups"][selected_age_group]["activities"])
try:
    activity_response = requests.get(f"{backend_url}/activities/{selected_age_group}", timeout=5)
    activity_response.raise_for_status()
    allowed_activities = activity_response.json().get("activities", allowed_activities)
except Exception:
    pass

st.subheader("Step 2: Choose Activity")
if selected_age_group == PRESCHOOL_GROUP:
    preschool_type = st.radio("Motor Type", list(PRESCHOOL_ACTIVITY_GROUPS.keys()), horizontal=True)
    allowed_activities = PRESCHOOL_ACTIVITY_GROUPS[preschool_type]
activity_choice = st.selectbox(
    "Activity",
    allowed_activities,
    format_func=lambda a: activity_option_label(metadata, selected_age_group, a),
    key="activity_choice",
)
if st.button("Confirm Activity", type="primary"):
    st.session_state.selected_activity = activity_choice

selected_activity = st.session_state.selected_activity
if not selected_activity:
    st.info("Click 'Confirm Activity' to continue.")
    st.stop()

st.subheader("Step 3: Enter Child Details and Record")
age_spec = metadata["age_groups"][selected_age_group]
min_age = float(age_spec["min_age"])
max_age = float(age_spec["max_age"])

col1, col2 = st.columns(2)
with col1:
    child_name = st.text_input("Child Name", key="child_name")
with col2:
    child_age = st.number_input(
        "Child Age",
        min_value=min_age,
        max_value=max_age,
        value=min_age,
        step=0.5 if selected_age_group == PRESCHOOL_GROUP else 1.0,
        key="child_age",
    )

trial1_jumped_distance_cm: float | None = None
trial2_jumped_distance_cm: float | None = None
trial1_landing_stability: int | None = None
trial2_landing_stability: int | None = None
blocks_stood: int | None = None
blocks_dropped: int | None = None
beads_threaded: int | None = None
beads_dropped: int | None = None
ball_catches: int | None = None
ball_drops: int | None = None
peg_count: int | None = None
peg_drop_count: int | None = None
bead_drop_count: int | None = None
ladder_box_count: int | None = None
if selected_activity == "long_jump":
    lj_col1, lj_col2 = st.columns(2)
    with lj_col1:
        trial1_jumped_distance_cm = st.number_input(
            "Trial 1 Distance (cm)",
            min_value=0.0,
            value=60.0,
            step=1.0,
            key="jumped_distance_cm_trial_1",
        )
        trial1_landing_stability = 1 if st.selectbox(
            "Trial 1 Landing Stability",
            ["Stable", "Unstable"],
            key="landing_stability_trial_1",
        ) == "Stable" else 0
    with lj_col2:
        trial2_jumped_distance_cm = st.number_input(
            "Trial 2 Distance (cm)",
            min_value=0.0,
            value=60.0,
            step=1.0,
            key="jumped_distance_cm_trial_2",
        )
        trial2_landing_stability = 1 if st.selectbox(
            "Trial 2 Landing Stability",
            ["Stable", "Unstable"],
            key="landing_stability_trial_2",
        ) == "Stable" else 0
elif selected_activity == "block_stacking":
    block_col1, block_col2 = st.columns(2)
    with block_col1:
        blocks_stood = st.number_input("Number of Blocks Stood", min_value=0, value=0, step=1)
    with block_col2:
        blocks_dropped = st.number_input("Number of Blocks Dropped", min_value=0, value=0, step=1)
elif selected_activity == "bead_threading":
    bead_col1, bead_col2 = st.columns(2)
    with bead_col1:
        beads_threaded = st.number_input("Number of Beads Threaded", min_value=0, value=0, step=1)
    with bead_col2:
        beads_dropped = st.number_input("Number of Beads Dropped", min_value=0, value=0, step=1)
elif selected_activity == "ball_catch":
    ball_col1, ball_col2 = st.columns(2)
    with ball_col1:
        ball_catches = st.number_input("Ball Catch Count", min_value=0, value=0, step=1)
    with ball_col2:
        ball_drops = st.number_input("Ball Drop Count", min_value=0, value=0, step=1)
elif selected_activity == "peg_board":
    peg_col1, peg_col2 = st.columns(2)
    with peg_col1:
        peg_count = st.number_input("Peg Count", min_value=0, value=0, step=1)
    with peg_col2:
        peg_drop_count = st.number_input("Peg Drop Count", min_value=0, value=0, step=1)
elif selected_activity == "beads_fm":
    beads_fm_col1, beads_fm_col2 = st.columns(2)
    with beads_fm_col1:
        beads_threaded = st.number_input("Beads Threaded", min_value=0, value=0, step=1)
    with beads_fm_col2:
        bead_drop_count = st.number_input("Bead Drop Count", min_value=0, value=0, step=1)
elif selected_activity == "agility_ladder":
    ladder_box_count = st.number_input("Number of Boxes in Ladder", min_value=1, value=10, step=1)

duration = activity_duration_seconds(metadata, selected_age_group, selected_activity)
st.info(
    f"Selected: {selected_age_group} -> {activity_label(metadata, selected_age_group, selected_activity)}. "
    f"Recording duration: {duration} seconds"
)
if selected_activity in DUAL_TRIAL_ACTIVITIES:
    st.caption("Final scoring for this activity uses two trials. Step 4 supports uploading both trial videos.")

payload = {
    "backend_url": backend_url,
    "name": child_name,
    "age": float(child_age),
    "age_group": selected_age_group,
    "activity": selected_activity,
    "duration": duration,
    "is_dual_trial_activity": selected_activity in DUAL_TRIAL_ACTIVITIES,
    "jumped_distance_cm_trial_1": trial1_jumped_distance_cm,
    "jumped_distance_cm_trial_2": trial2_jumped_distance_cm,
    "landing_stability_trial_1": trial1_landing_stability,
    "landing_stability_trial_2": trial2_landing_stability,
    "blocks_stood": blocks_stood,
    "blocks_dropped": blocks_dropped,
    "beads_threaded": beads_threaded,
    "beads_dropped": beads_dropped,
    "ball_catches": ball_catches,
    "ball_drops": ball_drops,
    "peg_count": peg_count,
    "peg_drop_count": peg_drop_count,
    "bead_drop_count": bead_drop_count,
    "ladder_box_count": ladder_box_count,
}

html = """
<div style="font-family: Arial, sans-serif; padding: 8px; border: 1px solid #ddd; border-radius: 10px; min-height: 900px;">
  <h4 style="margin-top:0;">Webcam Recorder</h4>
  <div id="previewWrap" style="position:relative; width:100%; max-width:640px; height:360px;">
    <video id="preview" autoplay muted playsinline style="width:100%; height:360px; object-fit:cover; background:#000; border-radius:8px;"></video>
    <canvas id="poseCanvas" style="position:absolute; left:0; top:0; width:100%; height:100%; pointer-events:none;"></canvas>
  </div>
  <video id="playback" controls style="display:none; width:100%; max-width:640px; height:360px; object-fit:contain; margin-top:10px; border-radius:8px;"></video>
  <div style="margin-top:10px; display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
    <button id="recordBtn">Start Recording</button>
    <button id="stopBtn" disabled>Stop Recording</button>
    <button id="playBtn" disabled>Play Video</button>
    <button id="retryBtn" disabled>Retry Recording</button>
    <button id="uploadBtn" disabled>Submit Video</button>
  </div>
  <p id="status" style="margin-top:10px;">Status: Idle</p>
  <pre id="resultBox" style="margin-top:10px; padding:10px; background:#f7f7f7; border-radius:8px; white-space:pre-wrap; max-height:220px; overflow:auto;"></pre>
</div>

<script src="https://cdn.jsdelivr.net/npm/@mediapipe/pose/pose.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@mediapipe/drawing_utils/drawing_utils.js"></script>
<script>
const cfg = __PAYLOAD_JSON__;
let stream = null;
let recorder = null;
let chunks = [];
let recordedBlob = null;
let recordedUrl = null;
let timer = null;
let finalized = false;
let isRecording = false;
let poseModel = null;
let poseAnimationId = null;
let poseBusy = false;

const preview = document.getElementById('preview');
const playback = document.getElementById('playback');
const poseCanvas = document.getElementById('poseCanvas');
const poseCtx = poseCanvas.getContext('2d');
const statusEl = document.getElementById('status');
const recordBtn = document.getElementById('recordBtn');
const stopBtn = document.getElementById('stopBtn');
const playBtn = document.getElementById('playBtn');
const retryBtn = document.getElementById('retryBtn');
const uploadBtn = document.getElementById('uploadBtn');
const resultBox = document.getElementById('resultBox');
let progressTimer = null;

function setStatus(msg) {
  statusEl.textContent = `Status: ${msg}`;
}

function setResult(msg) {
  resultBox.textContent = msg || '';
}

function startProgressPolling(requestId) {
  stopProgressPolling();
  progressTimer = setInterval(async () => {
    try {
      const res = await fetch(`${cfg.backend_url}/api/v1/progress/${requestId}`);
      if (!res.ok) return;
      const data = await res.json();
      const pct = data.progress_percent ?? 0;
      const msg = data.message || 'Processing video';
      setStatus(`${msg} (${pct}%)`);
    } catch (e) {
      // Ignore transient polling failures.
    }
  }, 1500);
}

function stopProgressPolling() {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
}

function formatUserResult(data) {
  const activityLabel = data.activity || cfg.activity;
  const lines = [
    `Name: ${data.name ?? cfg.name}`,
    `Age: ${data.age ?? cfg.age}`,
    `Activity: ${activityLabel}`,
    `Score: ${data.score}/${data.max_score}`,
    `Category: ${data.category}`,
  ];

  const metrics = data?.activity_metrics || {};
  const row = data?.csv_result?.row || {};
  const hidden = new Set(['ID', 'Name', 'Video_path']);
  const metricSource = Object.keys(metrics).length > 0
    ? metrics
    : Object.fromEntries(Object.entries(row).filter(([k, _v]) => !hidden.has(k)));
  const metricEntries = Object.entries(metricSource);
  if (metricEntries.length > 0) {
    lines.push('', 'Key Performance Metrics:');
    metricEntries.forEach(([k, v]) => {
      lines.push(`- ${k}: ${v}`);
    });
  }
  return lines.join('\n');
}

async function logEvent(eventName, details = '') {
  try {
    await fetch(`${cfg.backend_url}/api/v1/log-event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event: eventName,
        activity: cfg.activity,
        age_group: cfg.age_group,
        name: cfg.name,
        details: details
      })
    });
  } catch (e) {
    // Ignore logging failures in UI flow.
  }
}

function syncPoseCanvasSize() {
  const w = preview.videoWidth || 640;
  const h = preview.videoHeight || 360;
  if (poseCanvas.width !== w) poseCanvas.width = w;
  if (poseCanvas.height !== h) poseCanvas.height = h;
}

function clearPoseCanvas() {
  poseCtx.clearRect(0, 0, poseCanvas.width || 640, poseCanvas.height || 360);
}

async function initPoseModel() {
  if (poseModel) return;
  if (typeof Pose === 'undefined') {
    setStatus('Pose library unavailable in browser.');
    return;
  }
  poseModel = new Pose({
    locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/pose/${file}`,
  });
  poseModel.setOptions({
    modelComplexity: 1,
    smoothLandmarks: true,
    enableSegmentation: false,
    minDetectionConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });
  poseModel.onResults((results) => {
    clearPoseCanvas();
    if (!results.poseLandmarks) return;
    if (typeof drawConnectors === 'function') {
      drawConnectors(poseCtx, results.poseLandmarks, POSE_CONNECTIONS, { color: '#00FFAA', lineWidth: 3 });
      drawLandmarks(poseCtx, results.poseLandmarks, { color: '#FF2D55', lineWidth: 1, radius: 2 });
    }
  });
}

function stopPoseLoop() {
  if (poseAnimationId) {
    cancelAnimationFrame(poseAnimationId);
    poseAnimationId = null;
  }
  poseBusy = false;
  clearPoseCanvas();
}

function startPoseLoop() {
  stopPoseLoop();
  const loop = async () => {
    if (!isRecording || !poseModel || !stream) return;
    if (!poseBusy && preview.readyState >= 2) {
      poseBusy = true;
      syncPoseCanvasSize();
      try {
        await poseModel.send({ image: preview });
      } catch (e) {
        // keep UI running even if pose step fails
      } finally {
        poseBusy = false;
      }
    }
    poseAnimationId = requestAnimationFrame(loop);
  };
  poseAnimationId = requestAnimationFrame(loop);
}

function cleanupPlaybackUrl() {
  if (recordedUrl) {
    URL.revokeObjectURL(recordedUrl);
    recordedUrl = null;
  }
}

function stopCameraStream() {
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
    preview.srcObject = null;
  }
  stopPoseLoop();
}

function finalizeRecording() {
  if (finalized) return;
  finalized = true;
  isRecording = false;
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }

  if (chunks.length > 0) {
    recordedBlob = new Blob(chunks, { type: 'video/webm' });
    cleanupPlaybackUrl();
    recordedUrl = URL.createObjectURL(recordedBlob);
    playback.src = recordedUrl;
    playback.style.display = 'block';
    playBtn.disabled = false;
    uploadBtn.disabled = false;
    setStatus('Recording complete. Use Play Video, Retry Recording, or Submit Video.');
  } else {
    recordedBlob = null;
    playback.style.display = 'none';
    playBtn.disabled = true;
    uploadBtn.disabled = true;
    setStatus('Recording ended but no video data captured. Please Retry.');
  }

  retryBtn.disabled = false;
  stopBtn.disabled = true;
  recordBtn.disabled = false;
  retryBtn.style.display = 'inline-block';
  uploadBtn.style.display = 'inline-block';
  if (recordedBlob) {
    playback.style.display = 'block';
  }
  logEvent('recording_finalized', chunks.length > 0 ? 'video_ready' : 'no_video_data');
  stopCameraStream();
}

async function ensureStream() {
  if (stream) return stream;
  stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  preview.srcObject = stream;
  await new Promise((resolve) => {
    if (preview.readyState >= 1) { resolve(); return; }
    preview.onloadedmetadata = () => resolve();
  });
  return stream;
}

recordBtn.onclick = async () => {
  try {
    if (isRecording) {
      setStatus('Recording is already in progress.');
      return;
    }
    if (!cfg.name || String(cfg.name).trim().length === 0) {
      setStatus('Enter child name in Streamlit first.');
      return;
    }

    await ensureStream();
    await initPoseModel();
    chunks = [];
    recordedBlob = null;
    finalized = false;
    isRecording = true;
    playback.style.display = 'none';
    recordBtn.disabled = true;
    stopBtn.disabled = false;
    playBtn.disabled = true;
    uploadBtn.disabled = true;
    retryBtn.disabled = true;
    startPoseLoop();

    try {
      recorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
    } catch (e) {
      recorder = new MediaRecorder(stream);
    }
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };

    recorder.onstop = () => finalizeRecording();
    recorder.onerror = () => {
      finalizeRecording();
    };

    recorder.start();
    logEvent('recording_started', `duration=${cfg.duration}`);
    setStatus(`Recording for ${cfg.duration} seconds...`);

    timer = setTimeout(() => {
      if (recorder && recorder.state === 'recording') {
        recorder.stop();
      }
      // Fallback: unlock actions even if onstop is not emitted by browser.
      setTimeout(() => finalizeRecording(), 700);
    }, cfg.duration * 1000);
  } catch (err) {
    isRecording = false;
    recordBtn.disabled = false;
    stopBtn.disabled = true;
    stopCameraStream();
    logEvent('recording_error', String(err && err.message ? err.message : err));
    setStatus('Camera error: ' + err.message);
  }
};

stopBtn.onclick = () => {
  if (isRecording && recorder && recorder.state === 'recording') {
    recorder.stop();
    if (timer) clearTimeout(timer);
    setTimeout(() => finalizeRecording(), 500);
    logEvent('recording_stopped_manual', 'user_clicked_stop');
    setStatus('Recording stopped manually. Finalizing...');
  }
};

playBtn.onclick = async () => {
  if (!recordedBlob) {
    setStatus('No recorded video to play.');
    return;
  }
  playback.style.display = 'block';
  playback.currentTime = 0;
  try {
    await playback.play();
    setStatus('Playing recorded video.');
  } catch (err) {
    setStatus('Unable to play video: ' + err.message);
  }
};

retryBtn.onclick = () => {
  if (timer) clearTimeout(timer);
  chunks = [];
  recordedBlob = null;
  cleanupPlaybackUrl();
  playback.removeAttribute('src');
  playback.style.display = 'none';
  finalized = false;
  isRecording = false;
  recordBtn.disabled = false;
  stopBtn.disabled = true;
  playBtn.disabled = true;
  retryBtn.disabled = true;
  uploadBtn.disabled = true;
  stopCameraStream();
  logEvent('recording_retry', 'user_clicked_retry');
  setStatus('Retry ready. Press Start Recording again.');
};

uploadBtn.onclick = async () => {
  try {
    if (!recordedBlob) {
      setStatus('No recording available.');
      return;
    }

    const requestId = (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());
    const form = new FormData();
    form.append('request_id', requestId);
    form.append('name', cfg.name);
    form.append('age', String(cfg.age));
    form.append('age_group', cfg.age_group);
    form.append('activity', cfg.activity);
    if (cfg.activity === 'long_jump' && cfg.jumped_distance_cm_trial_1 != null) {
      form.append('jumped_length', String(cfg.jumped_distance_cm_trial_1));
      form.append('jumped_length_2', String(cfg.jumped_distance_cm_trial_2 ?? cfg.jumped_distance_cm_trial_1));
      form.append('landing_stability', String(cfg.landing_stability_trial_1 ?? 0));
      form.append('landing_stability_2', String(cfg.landing_stability_trial_2 ?? cfg.landing_stability_trial_1 ?? 0));
    }
    if (cfg.activity === 'block_stacking') {
      form.append('blocks_stood', String(cfg.blocks_stood ?? 0));
      form.append('blocks_dropped', String(cfg.blocks_dropped ?? 0));
    }
    if (cfg.activity === 'bead_threading') {
      form.append('beads_threaded', String(cfg.beads_threaded ?? 0));
      form.append('beads_dropped', String(cfg.beads_dropped ?? 0));
    }
    if (cfg.activity === 'ball_catch') {
      form.append('ball_catches', String(cfg.ball_catches ?? 0));
      form.append('ball_drops', String(cfg.ball_drops ?? 0));
    }
    if (cfg.activity === 'peg_board') {
      form.append('peg_count', String(cfg.peg_count ?? 0));
      form.append('peg_drop_count', String(cfg.peg_drop_count ?? 0));
    }
    if (cfg.activity === 'beads_fm') {
      form.append('beads_threaded', String(cfg.beads_threaded ?? 0));
      form.append('bead_drop_count', String(cfg.bead_drop_count ?? 0));
    }
    if (cfg.activity === 'agility_ladder') {
      form.append('ladder_box_count', String(cfg.ladder_box_count ?? 0));
    }
    form.append('file', recordedBlob, `${cfg.activity}.webm`);
    if (cfg.is_dual_trial_activity) {
      form.append('file_2', recordedBlob, `${cfg.activity}_trial2.webm`);
    }

    retryBtn.disabled = true;
    uploadBtn.disabled = true;
    recordBtn.disabled = true;
    stopBtn.disabled = true;
    playback.style.display = 'block';
    playback.currentTime = 0;
    try { await playback.play(); } catch (e) {}
    setStatus('Uploading and analyzing...');
    startProgressPolling(requestId);
    logEvent('upload_started', 'video_submit');
    const res = await fetch(`${cfg.backend_url}/api/v1/analyze`, {
      method: 'POST',
      body: form,
    });

    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      throw new Error('Backend response is not valid JSON.');
    }
    if (!res.ok) {
      throw new Error(data.detail || 'Upload failed');
    }

    stopProgressPolling();
    setStatus(`Done. Score: ${data.score}/${data.max_score}, Category: ${data.category}`);
    logEvent('upload_done', `score=${data.score};category=${data.category}`);
    setResult(formatUserResult(data));
    retryBtn.disabled = false;
    uploadBtn.disabled = false;
    recordBtn.disabled = false;
    playBtn.disabled = false;
  } catch (err) {
    stopProgressPolling();
    setStatus('Upload error: ' + err.message);
    setResult('Error while processing video. Please retry recording and submit again.');
    logEvent('upload_error', String(err && err.message ? err.message : err));
    retryBtn.disabled = false;
    recordBtn.disabled = false;
    playBtn.disabled = false;
    uploadBtn.disabled = false;
  }
};
</script>
"""
html = html.replace("__PAYLOAD_JSON__", json.dumps(payload))

st.subheader("Step 4: Upload Existing File" if selected_activity in IMAGE_UPLOAD_ACTIVITIES else "Step 4: Upload Existing Video")
upload_label = "Upload image file" if selected_activity in IMAGE_UPLOAD_ACTIVITIES else "Upload trial 1 video file"
upload_types = ["png", "jpg", "jpeg"] if selected_activity in IMAGE_UPLOAD_ACTIVITIES else ["mp4", "mov", "avi", "mkv", "webm"]
uploaded_video = st.file_uploader(
    upload_label,
    type=upload_types,
    accept_multiple_files=False,
    key="manual_video_upload_trial_1",
)
uploaded_video_2 = None
if selected_activity in DUAL_TRIAL_ACTIVITIES:
    uploaded_video_2 = st.file_uploader(
        "Upload trial 2 video file",
        type=["mp4", "mov", "avi", "mkv", "webm"],
        accept_multiple_files=False,
        key="manual_video_upload_trial_2",
    )

if uploaded_video is not None:
    if selected_activity in IMAGE_UPLOAD_ACTIVITIES:
        st.image(uploaded_video)
    else:
        st.video(uploaded_video)
    if uploaded_video_2 is not None:
        st.video(uploaded_video_2)
    submit_label = "Submit Uploaded Image" if selected_activity in IMAGE_UPLOAD_ACTIVITIES else "Submit Uploaded Video"
    if st.button(submit_label, type="primary"):
        try:
            if not str(child_name or "").strip():
                raise RuntimeError("Please enter Child Name in Step 3 before submitting uploaded video.")
            if selected_activity in DUAL_TRIAL_ACTIVITIES and uploaded_video_2 is None:
                raise RuntimeError("Please upload both trial videos for this activity.")
            request_id = uuid.uuid4().hex
            result_holder: dict[str, object] = {}

            def run_upload() -> None:
                try:
                    files = {
                        "file": (uploaded_video.name, uploaded_video.getvalue(), uploaded_video.type or "video/mp4")
                    }
                    if uploaded_video_2 is not None:
                        files["file_2"] = (
                            uploaded_video_2.name,
                            uploaded_video_2.getvalue(),
                            uploaded_video_2.type or "video/mp4",
                        )
                    data = {
                        "request_id": request_id,
                        "name": str(child_name).strip(),
                        "age": str(float(child_age)),
                        "age_group": selected_age_group,
                        "activity": selected_activity,
                        "gender": "male",
                    }
                    if selected_activity == "long_jump" and trial1_jumped_distance_cm is not None:
                        data["jumped_length"] = str(float(trial1_jumped_distance_cm))
                        data["jumped_length_2"] = str(float(trial2_jumped_distance_cm or trial1_jumped_distance_cm))
                        data["landing_stability"] = str(int(trial1_landing_stability or 0))
                        data["landing_stability_2"] = str(int(trial2_landing_stability or 0))
                    if selected_activity == "block_stacking":
                        data["blocks_stood"] = str(int(blocks_stood or 0))
                        data["blocks_dropped"] = str(int(blocks_dropped or 0))
                    if selected_activity == "bead_threading":
                        data["beads_threaded"] = str(int(beads_threaded or 0))
                        data["beads_dropped"] = str(int(beads_dropped or 0))
                    if selected_activity == "ball_catch":
                        data["ball_catches"] = str(int(ball_catches or 0))
                        data["ball_drops"] = str(int(ball_drops or 0))
                    if selected_activity == "peg_board":
                        data["peg_count"] = str(int(peg_count or 0))
                        data["peg_drop_count"] = str(int(peg_drop_count or 0))
                    if selected_activity == "beads_fm":
                        data["beads_threaded"] = str(int(beads_threaded or 0))
                        data["bead_drop_count"] = str(int(bead_drop_count or 0))
                    if selected_activity == "agility_ladder":
                        data["ladder_box_count"] = str(int(ladder_box_count or 0))
                    response = requests.post(
                        f"{backend_url}/api/v1/analyze",
                        files=files,
                        data=data,
                        timeout=ANALYZE_TIMEOUT_SECONDS,
                    )
                    result_holder["status_code"] = response.status_code
                    result_holder["payload"] = response.json()
                except Exception as exc:
                    result_holder["error"] = exc

            progress_text = st.empty()
            progress_bar = st.progress(0, text="Uploading video...")
            worker = threading.Thread(target=run_upload, daemon=True)
            worker.start()

            while worker.is_alive():
                try:
                    progress_response = requests.get(
                        f"{backend_url}/api/v1/progress/{request_id}",
                        timeout=5,
                    )
                    if progress_response.ok:
                        progress_payload = progress_response.json()
                        percent = int(progress_payload.get("progress_percent", 0))
                        message = progress_payload.get("message") or "Processing video..."
                        progress_bar.progress(percent, text=f"{message} ({percent}%)")
                        progress_text.caption(f"Video processed: {percent}%")
                    else:
                        progress_bar.progress(5, text="Uploading and starting analysis...")
                except Exception:
                    progress_bar.progress(5, text="Uploading and starting analysis...")
                time.sleep(1.0)

            worker.join()
            if "error" in result_holder:
                raise result_holder["error"]

            payload = result_holder.get("payload")
            status_code = int(result_holder.get("status_code", 500))
            if not isinstance(payload, dict):
                raise RuntimeError("Backend response is not valid JSON.")
            progress_bar.progress(100, text="Analysis complete (100%)")
            progress_text.caption("Video processed: 100%")
            if status_code >= 400:
                detail = payload.get("detail", "Upload failed")
                if isinstance(detail, list):
                    detail = "; ".join(item.get("msg", str(item)) for item in detail)
                raise RuntimeError(detail)

            st.success(
                f"Done. Score: {payload['score']}/{payload['max_score']} | Category: {payload['category']}"
            )
            st.write(f"Name: {payload.get('name', child_name)}")
            st.write(f"Age: {payload.get('age', child_age)}")
            st.write(
                f"Activity: {activity_label(metadata, selected_age_group, payload.get('activity', selected_activity))}"
            )
            metrics = user_visible_metrics(payload)
            if metrics:
                st.subheader("Key Performance Metrics")
                show_json_safe(metrics, fallback_message="No metrics found.")
        except Exception as exc:
            st.error(f"Upload error: {exc}")

if selected_activity not in IMAGE_UPLOAD_ACTIVITIES:
    st.subheader("Step 5: Or Record Video")
    components.html(
        html,
        height=980,
        scrolling=True,
    )
