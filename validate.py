#!/usr/bin/env python3
"""
validate.py — Phase 5 Validation Protocol (Person A)

Runs controlled walkthroughs against test footage and logs accuracy.

Usage:
  python validate.py --config config/site_config.yaml --mode entry_exit --expected logs/entry_exit_expected.json
  python validate.py --config config/site_config.yaml --mode posture   --expected logs/posture_expected.json

Outputs:
  logs/entry_exit_results.csv
  logs/posture_results.csv
  logs/summary.json
"""

import sys
import os
import json
import csv
import queue
import time
import argparse
import logging
from datetime import datetime

# Ensure core/ is importable
sys.path.insert(0, os.path.dirname(__file__))

from core.main_vision import VisionRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("validate")


def run_validation(config_path: str, mode: str, expected_path: str):
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Load expected ground truth if provided
    expected_events = []
    if expected_path and os.path.exists(expected_path):
        with open(expected_path) as f:
            expected_events = json.load(f)
        logger.info(f"Loaded {len(expected_events)} expected events from {expected_path}")
    else:
        logger.warning("No expected events file provided — will only log observed events.")

    shared_q = queue.Queue()
    runner = VisionRunner(config_path, shared_q)

    results = []
    runner.running = True

    # Filter cameras by role
    cameras_to_run = [
        cam for cam in runner.cameras_config
        if cam.get("role") == mode
    ]
    if not cameras_to_run:
        logger.error(f"No cameras with role '{mode}' found in config.")
        return

    runner.cameras_config = cameras_to_run

    import threading
    from core.adapters.rtsp import RTSPSource
    from core.pipeline.detector import Detector
    from core.pipeline.tracker import Tracker
    from core.pipeline.entry_exit import EntryExitLogic
    from core.pipeline.posture import PostureLogic

    logger.info(f"Starting validation run for mode: {mode}")
    logger.info(f"Cameras: {[c['camera_id'] for c in cameras_to_run]}")

    def collect(timeout=120):
        """Collect events from the queue until the video ends (None sentinel)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                ev = shared_q.get(timeout=1.0)
                if ev is None:
                    break
                results.append(ev)
            except queue.Empty:
                continue

    collector_thread = threading.Thread(target=collect, daemon=True)
    collector_thread.start()
    runner.start()
    collector_thread.join(timeout=180)
    runner.stop()

    logger.info(f"Collected {len(results)} events total.")

    # Write raw results CSV
    if mode == "entry_exit":
        csv_path = f"logs/entry_exit_results_{timestamp}.csv"
        fields = ["camera_id", "timestamp", "track_id", "bbox", "event"]
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in results:
                if r.get("event") is not None:
                    w.writerow(r)
        logger.info(f"Entry/exit results saved to {csv_path}")

        # Accuracy computation
        if expected_events:
            correct = missed = double_count = id_switch = 0
            observed_events = [r for r in results if r.get("event") is not None]
            obs_types = [e["event"] for e in observed_events]
            exp_types = [e["event"] for e in expected_events]

            for exp in exp_types:
                if exp in obs_types:
                    correct += 1
                    obs_types.remove(exp)
                else:
                    missed += 1
            double_count = len(obs_types)  # leftover observed = extra fires

            total = len(expected_events)
            accuracy = (correct / total * 100) if total > 0 else 0.0
            logger.info(f"Entry/Exit Accuracy: {accuracy:.1f}% ({correct}/{total} correct, {missed} missed, {double_count} double-counted)")

            summary = {
                "mode": "entry_exit",
                "timestamp": timestamp,
                "total_expected": total,
                "correct": correct,
                "missed": missed,
                "double_count": double_count,
                "id_switch": id_switch,
                "accuracy_pct": round(accuracy, 2)
            }
        else:
            summary = {"mode": "entry_exit", "timestamp": timestamp, "observed_events": len([r for r in results if r.get("event") is not None])}

    elif mode == "posture":
        csv_path = f"logs/posture_results_{timestamp}.csv"
        fields = ["camera_id", "timestamp", "track_id", "posture"]
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in results:
                if r.get("posture") is not None:
                    w.writerow(r)
        logger.info(f"Posture results saved to {csv_path}")

        # Accuracy computation (spot-check style)
        if expected_events:
            correct = wrong = unknown_count = 0
            for exp in expected_events:
                matching = [r for r in results if r.get("track_id") == exp.get("track_id")]
                if not matching:
                    wrong += 1
                    continue
                # Take majority vote from matching frames
                postures = [r["posture"] for r in matching if r.get("posture") and r["posture"] != "unknown"]
                if not postures:
                    unknown_count += 1
                    continue
                majority = max(set(postures), key=postures.count)
                if majority == exp.get("posture"):
                    correct += 1
                else:
                    wrong += 1

            total = len(expected_events)
            accuracy = (correct / total * 100) if total > 0 else 0.0
            logger.info(f"Posture Accuracy: {accuracy:.1f}% ({correct}/{total} correct, {wrong} wrong, {unknown_count} unknowns)")

            summary = {
                "mode": "posture",
                "timestamp": timestamp,
                "total_expected": total,
                "correct": correct,
                "wrong": wrong,
                "unknown": unknown_count,
                "accuracy_pct": round(accuracy, 2)
            }
        else:
            summary = {"mode": "posture", "timestamp": timestamp, "observed_events": len([r for r in results if r.get("posture") is not None])}
    else:
        summary = {}

    summary_path = f"logs/summary_{timestamp}.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Summary saved to {summary_path}")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Person A — Validation Protocol")
    parser.add_argument("--config", default="config/site_config.yaml")
    parser.add_argument("--mode", choices=["entry_exit", "posture"], required=True)
    parser.add_argument("--expected", default=None, help="Path to expected events JSON for accuracy scoring")
    args = parser.parse_args()
    run_validation(args.config, args.mode, args.expected)


if __name__ == "__main__":
    main()
