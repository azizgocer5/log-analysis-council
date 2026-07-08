"""ULog flight log parser and data extraction module.

Parses PX4 ULog files and extracts structured telemetry summaries
for LLM council consumption. Large binary logs are reduced to
statistical summaries and anomaly reports.
"""

import os
import hashlib
import json
import math
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

import numpy as np
import pandas as pd
from pyulog import ULog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quat_to_euler(q0, q1, q2, q3):
    """Convert quaternion to Euler angles (roll, pitch, yaw) in degrees."""
    # Roll (x-axis rotation)
    sinr_cosp = 2.0 * (q0 * q1 + q2 * q3)
    cosr_cosp = 1.0 - 2.0 * (q1 * q1 + q2 * q2)
    roll = np.arctan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2.0 * (q0 * q2 - q3 * q1)
    sinp = np.clip(sinp, -1.0, 1.0)
    pitch = np.arcsin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2.0 * (q0 * q3 + q1 * q2)
    cosy_cosp = 1.0 - 2.0 * (q2 * q2 + q3 * q3)
    yaw = np.arctan2(siny_cosp, cosy_cosp)

    return np.degrees(roll), np.degrees(pitch), np.degrees(yaw)


def _get_topic_data(ulog: ULog, topic_name: str, instance: int = 0) -> Optional[Dict]:
    """Get data for a specific topic and instance from ULog."""
    matches = [d for d in ulog.data_list if d.name == topic_name]
    if instance < len(matches):
        return matches[instance].data
    return None


def _safe_stats(arr) -> Dict[str, float]:
    """Compute safe statistics, handling NaN/Inf."""
    arr = np.asarray(arr, dtype=float)
    valid = arr[np.isfinite(arr)]
    if len(valid) == 0:
        return {"min": 0, "max": 0, "mean": 0, "std": 0, "count": 0}
    return {
        "min": round(float(np.min(valid)), 4),
        "max": round(float(np.max(valid)), 4),
        "mean": round(float(np.mean(valid)), 4),
        "std": round(float(np.std(valid)), 4),
        "count": int(len(valid)),
    }


def _timestamps_to_seconds(timestamps) -> np.ndarray:
    """Convert microsecond timestamps to seconds from start."""
    ts = np.asarray(timestamps, dtype=float)
    return (ts - ts[0]) / 1e6


def file_hash(filepath: str) -> str:
    """Compute MD5 hash of a file for cache keying."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Core Extraction Functions
# ---------------------------------------------------------------------------

def extract_flight_summary(ulog: ULog, filepath: str) -> Dict[str, Any]:
    """Extract high-level flight summary metadata."""
    summary: Dict[str, Any] = {}

    # File info
    summary["file"] = os.path.basename(filepath)
    summary["file_size_mb"] = round(os.path.getsize(filepath) / 1024 / 1024, 1)

    # Duration
    start_ts = ulog.start_timestamp
    last_ts = ulog.last_timestamp
    duration_s = (last_ts - start_ts) / 1e6
    summary["duration_s"] = round(duration_s, 1)
    summary["duration_str"] = f"{int(duration_s // 60)}m {int(duration_s % 60)}s"

    # Hardware & firmware from msg_info
    info = ulog.msg_info_dict
    summary["hardware"] = info.get("sys_hw", "Unknown")
    summary["firmware"] = info.get("ver_sw", "Unknown")
    summary["uuid"] = info.get("sys_uuid", "Unknown")

    # Parameters count
    summary["param_count"] = len(ulog.initial_parameters)

    # Vehicle status
    vs = _get_topic_data(ulog, "vehicle_status")
    if vs is not None:
        summary["is_vtol"] = bool(vs.get("is_vtol", [0])[0])
        summary["vehicle_type"] = int(vs.get("vehicle_type", [0])[0])

        # Nav state transitions
        nav_states = vs.get("nav_state", [])
        nav_map = {
            0: "MANUAL", 1: "ALTCTL", 2: "POSCTL", 3: "AUTO_MISSION",
            4: "AUTO_LOITER", 5: "AUTO_RTL", 10: "ACRO", 12: "DESCEND",
            13: "TERMINATION", 14: "OFFBOARD", 17: "STAB", 18: "AUTO_TAKEOFF",
            19: "AUTO_LAND", 20: "AUTO_FOLLOW", 21: "AUTO_PRECLAND",
            22: "ORBIT",
        }
        nav_labels = [nav_map.get(int(s), f"UNKNOWN({int(s)})") for s in nav_states]
        # Deduplicate consecutive
        transitions = []
        for label in nav_labels:
            if not transitions or transitions[-1] != label:
                transitions.append(label)
        summary["nav_state_transitions"] = transitions

        # Arming
        arming = vs.get("arming_state", [])
        summary["was_armed"] = any(int(a) == 2 for a in arming)

        # Preflight checks
        pfc = vs.get("pre_flight_checks_pass", [])
        summary["preflight_pass"] = all(bool(p) for p in pfc) if len(pfc) > 0 else None

    # Position data for altitude
    vlp = _get_topic_data(ulog, "vehicle_local_position")
    if vlp is not None:
        z = np.asarray(vlp.get("z", [0]))
        valid_z = z[np.isfinite(z)]
        if len(valid_z) > 0:
            summary["max_altitude_m"] = round(float(-np.min(valid_z)), 1)  # NED: z negative = up
            summary["avg_altitude_m"] = round(float(-np.mean(valid_z)), 1)

    return summary


def extract_attitude_tracking(ulog: ULog) -> Dict[str, Any]:
    """Extract attitude tracking performance (actual vs setpoint)."""
    result = {}

    att = _get_topic_data(ulog, "vehicle_attitude")
    att_sp = _get_topic_data(ulog, "vehicle_attitude_setpoint")

    if att is None or att_sp is None:
        return {"error": "Attitude data not available"}

    # Convert actual quaternions to euler
    roll_act, pitch_act, yaw_act = _quat_to_euler(
        att["q[0]"], att["q[1]"], att["q[2]"], att["q[3]"]
    )

    # Convert setpoint quaternions to euler
    roll_sp, pitch_sp, yaw_sp = _quat_to_euler(
        att_sp["q_d[0]"], att_sp["q_d[1]"], att_sp["q_d[2]"], att_sp["q_d[3]"]
    )

    # Interpolate setpoints to actual timestamps
    ts_act = att["timestamp"]
    ts_sp = att_sp["timestamp"]

    # Use pandas for time-aligned comparison
    df_act = pd.DataFrame({
        "ts": ts_act, "roll": roll_act, "pitch": pitch_act, "yaw": yaw_act
    })
    df_sp = pd.DataFrame({
        "ts": ts_sp, "roll_sp": roll_sp, "pitch_sp": pitch_sp, "yaw_sp": yaw_sp
    })

    # Merge on nearest timestamp
    df_act = df_act.sort_values("ts")
    df_sp = df_sp.sort_values("ts")
    merged = pd.merge_asof(df_act, df_sp, on="ts", direction="nearest", tolerance=500000)
    merged = merged.dropna()

    if len(merged) < 5:
        return {"error": "Insufficient data for attitude tracking analysis"}

    for axis in ["roll", "pitch", "yaw"]:
        actual = merged[axis].values
        setpoint = merged[f"{axis}_sp"].values
        error = actual - setpoint

        # Wrap yaw error to [-180, 180]
        if axis == "yaw":
            error = (error + 180) % 360 - 180

        rmse = float(np.sqrt(np.mean(error ** 2)))
        max_error = float(np.max(np.abs(error)))
        mean_error = float(np.mean(error))

        result[axis] = {
            "rmse_deg": round(rmse, 3),
            "max_error_deg": round(max_error, 3),
            "mean_error_deg": round(mean_error, 3),
            "actual_stats": _safe_stats(actual),
            "setpoint_stats": _safe_stats(setpoint),
        }

    # Rate tracking (angular velocity vs setpoint)
    ang_vel = _get_topic_data(ulog, "vehicle_angular_velocity")
    rate_sp = _get_topic_data(ulog, "vehicle_rates_setpoint")

    if ang_vel is not None and rate_sp is not None:
        df_rate = pd.DataFrame({
            "ts": ang_vel["timestamp"],
            "roll_rate": np.degrees(ang_vel["xyz[0]"]),
            "pitch_rate": np.degrees(ang_vel["xyz[1]"]),
            "yaw_rate": np.degrees(ang_vel["xyz[2]"]),
        })
        df_rate_sp = pd.DataFrame({
            "ts": rate_sp["timestamp"],
            "roll_rate_sp": np.degrees(rate_sp.get("xyz[0]", rate_sp.get("roll", []))),
            "pitch_rate_sp": np.degrees(rate_sp.get("xyz[1]", rate_sp.get("pitch", []))),
            "yaw_rate_sp": np.degrees(rate_sp.get("xyz[2]", rate_sp.get("yaw", []))),
        })
        rate_merged = pd.merge_asof(
            df_rate.sort_values("ts"), df_rate_sp.sort_values("ts"),
            on="ts", direction="nearest", tolerance=500000
        ).dropna()

        if len(rate_merged) > 5:
            result["rate_tracking"] = {}
            for axis in ["roll_rate", "pitch_rate", "yaw_rate"]:
                actual = rate_merged[axis].values
                setpoint = rate_merged[f"{axis}_sp"].values
                error = actual - setpoint
                result["rate_tracking"][axis] = {
                    "rmse_deg_s": round(float(np.sqrt(np.mean(error ** 2))), 3),
                    "max_error_deg_s": round(float(np.max(np.abs(error))), 3),
                }

    return result


def extract_battery_data(ulog: ULog) -> Dict[str, Any]:
    """Extract battery telemetry and anomalies."""
    bs = _get_topic_data(ulog, "battery_status")
    if bs is None:
        return {"error": "Battery data not available"}

    voltage = np.asarray(bs.get("voltage_v", []))
    current = np.asarray(bs.get("current_a", []))
    remaining = np.asarray(bs.get("remaining", []))

    result = {
        "voltage": _safe_stats(voltage),
        "current": _safe_stats(current),
        "remaining": _safe_stats(remaining),
    }

    # Anomaly detection
    anomalies = []
    neg_voltage = np.sum(voltage <= 0)
    if neg_voltage > 0:
        result["negative_voltage_count"] = int(neg_voltage)
        anomalies.append(f"⚠️ {neg_voltage} negative/zero voltage readings detected")

    # Voltage drops
    valid_v = voltage[voltage > 0]
    if len(valid_v) > 1:
        v_diff = np.diff(valid_v)
        sudden_drops = np.sum(v_diff < -1.0)  # >1V drop between samples
        if sudden_drops > 0:
            anomalies.append(f"⚠️ {sudden_drops} sudden voltage drops (>1V) detected")

    # Cell voltages
    cell_voltages = []
    for i in range(14):
        key = f"voltage_cell_v[{i}]"
        if key in bs:
            cv = np.asarray(bs[key])
            valid_cv = cv[cv > 0]
            if len(valid_cv) > 0:
                cell_voltages.append({
                    "cell": i + 1,
                    "avg_v": round(float(np.mean(valid_cv)), 3),
                    "min_v": round(float(np.min(valid_cv)), 3),
                })
    if cell_voltages:
        result["cell_voltages"] = cell_voltages

    result["anomalies"] = anomalies
    return result


def extract_vibration_data(ulog: ULog) -> Dict[str, Any]:
    """Extract vibration analysis from IMU data using FFT."""
    result = {}

    # Try sensor_combined first (higher sample rate)
    sc = _get_topic_data(ulog, "sensor_combined")
    if sc is not None and len(sc.get("timestamp", [])) > 50:
        ts = _timestamps_to_seconds(sc["timestamp"])
        dt = np.median(np.diff(ts))
        if dt > 0:
            fs = 1.0 / dt
            result["sample_rate_hz"] = round(fs, 1)

            for axis, key in [("x", "accelerometer_m_s2[0]"),
                              ("y", "accelerometer_m_s2[1]"),
                              ("z", "accelerometer_m_s2[2]")]:
                if key in sc:
                    data = np.asarray(sc[key], dtype=float)
                    data = data[np.isfinite(data)]
                    if len(data) > 50:
                        # Remove DC offset
                        data = data - np.mean(data)
                        # FFT
                        n = len(data)
                        fft_vals = np.abs(np.fft.rfft(data))
                        freqs = np.fft.rfftfreq(n, d=dt)

                        # Find dominant frequencies (top 5)
                        idx = np.argsort(fft_vals)[::-1]
                        peaks = []
                        for i in idx[:10]:
                            if freqs[i] > 1.0:  # Skip DC and very low freq
                                peaks.append({
                                    "freq_hz": round(float(freqs[i]), 1),
                                    "magnitude": round(float(fft_vals[i]), 2),
                                })
                                if len(peaks) >= 5:
                                    break

                        result[f"accel_{axis}"] = {
                            "rms_m_s2": round(float(np.sqrt(np.mean(data ** 2))), 4),
                            "peak_m_s2": round(float(np.max(np.abs(data))), 4),
                            "dominant_frequencies": peaks,
                        }

    # Gyro vibration
    for instance in range(3):
        gyro = _get_topic_data(ulog, "sensor_gyro", instance)
        if gyro is not None and len(gyro.get("timestamp", [])) > 20:
            for axis in ["x", "y", "z"]:
                if axis in gyro:
                    data = np.asarray(gyro[axis], dtype=float)
                    valid = data[np.isfinite(data)]
                    if len(valid) > 10:
                        result[f"gyro_{axis}_inst{instance}"] = {
                            "rms_rad_s": round(float(np.sqrt(np.mean(valid ** 2))), 4),
                            "peak_rad_s": round(float(np.max(np.abs(valid))), 4),
                        }
            break  # Only need one instance

    # IMU clipping
    for instance in range(3):
        accel = _get_topic_data(ulog, "sensor_accel", instance)
        if accel is not None:
            total_clips = 0
            for i in range(3):
                key = f"clip_counter[{i}]"
                if key in accel:
                    total_clips += int(np.sum(accel[key]))
            if total_clips > 0:
                result[f"imu_clips_inst{instance}"] = total_clips
            break

    return result


def extract_ekf_data(ulog: ULog) -> Dict[str, Any]:
    """Extract EKF health and innovation diagnostics."""
    result = {}

    # Innovation test ratios
    itr = _get_topic_data(ulog, "estimator_innovation_test_ratios")
    if itr is not None:
        for key_prefix, label in [
            ("gps_hvel", "GPS Horizontal Velocity"),
            ("gps_vvel", "GPS Vertical Velocity"),
            ("gps_hpos", "GPS Horizontal Position"),
            ("gps_vpos", "GPS Vertical Position"),
        ]:
            vals = []
            for suffix in ["", "[0]", "[1]"]:
                k = f"{key_prefix}{suffix}"
                if k in itr:
                    v = np.asarray(itr[k], dtype=float)
                    valid = v[np.isfinite(v)]
                    vals.extend(valid.tolist())
            if vals:
                arr = np.array(vals)
                exceeds = np.sum(arr > 1.0)
                result[label] = {
                    "mean_ratio": round(float(np.mean(arr)), 4),
                    "max_ratio": round(float(np.max(arr)), 4),
                    "times_exceeded_threshold": int(exceeds),
                    "percent_exceeded": round(float(exceeds / len(arr) * 100), 1) if len(arr) > 0 else 0,
                }

    # Estimator status flags
    esf = _get_topic_data(ulog, "estimator_status_flags")
    if esf is not None:
        flags = {}
        for key in ["cs_gnss_pos", "cs_gnss_vel", "cs_gnss_hgt",
                     "cs_baro_hgt", "cs_mag_3d", "cs_tilt_align", "cs_yaw_align"]:
            if key in esf:
                vals = esf[key]
                flags[key] = bool(vals[-1]) if len(vals) > 0 else None
        result["estimator_flags"] = flags

    # GPS quality
    gps = _get_topic_data(ulog, "sensor_gps") or _get_topic_data(ulog, "vehicle_gps_position")
    if gps is not None:
        for key in ["fix_type", "satellites_used", "hdop", "vdop"]:
            if key in gps:
                result[f"gps_{key}"] = _safe_stats(gps[key])

    return result


def extract_actuator_data(ulog: ULog) -> Dict[str, Any]:
    """Extract motor and actuator output data."""
    result = {}

    # Actuator motors
    am = _get_topic_data(ulog, "actuator_motors")
    if am is not None:
        motor_stats = {}
        for i in range(12):
            key = f"control[{i}]"
            if key in am:
                vals = np.asarray(am[key], dtype=float)
                valid = vals[np.isfinite(vals)]
                non_zero = valid[valid != 0]
                if len(non_zero) > 0:
                    motor_stats[f"motor_{i + 1}"] = _safe_stats(non_zero)
        result["motors"] = motor_stats

        # Motor balance check
        if len(motor_stats) >= 4:
            means = [v["mean"] for v in motor_stats.values()]
            spread = max(means) - min(means)
            result["motor_balance"] = {
                "spread": round(spread, 4),
                "balanced": spread < 0.1,
                "individual_means": {k: v["mean"] for k, v in motor_stats.items()},
            }

    # Actuator outputs
    ao = _get_topic_data(ulog, "actuator_outputs")
    if ao is not None:
        output_stats = {}
        for i in range(16):
            key = f"output[{i}]"
            if key in ao:
                vals = np.asarray(ao[key], dtype=float)
                valid = vals[np.isfinite(vals)]
                non_zero = valid[valid != 0]
                if len(non_zero) > 0:
                    output_stats[f"output_{i + 1}"] = _safe_stats(non_zero)
        if output_stats:
            result["outputs"] = output_stats

    return result


def extract_pid_parameters(ulog: ULog) -> Dict[str, Any]:
    """Extract PID-related and sensor/safety parameters from the log."""
    params = ulog.initial_parameters
    pid_params = {}

    prefixes = [
        "MC_ROLLRATE_", "MC_PITCHRATE_", "MC_YAWRATE_",
        "MC_ROLL_", "MC_PITCH_", "MC_YAW_",
        "MPC_Z_", "MPC_XY_", "MPC_ACC_",
        "FW_R_", "FW_P_", "FW_Y_",
        "VT_",  # VTOL transition params
        "IMU_",  # IMU filters / notch filters
        "EKF2_", # EKF2 gates / parameters
        "COM_",  # Commander safety actions
        "BAT_",  # Battery thresholds
        "NAV_",  # Navigation limits / failsafes
        "GF_",   # Geofence
        "RTL_",  # Return-to-launch rules
        "WEIGHT_", # Weight parameters
        "FW_WING_SPAN", # Wing span
        "CA_", # Control allocation / airframe geometry
    ]

    for key, value in sorted(params.items()):
        for prefix in prefixes:
            if key.startswith(prefix):
                pid_params[key] = round(float(value), 6) if isinstance(value, float) else value
                break

    return pid_params


def extract_failsafe_events(ulog: ULog) -> Dict[str, Any]:
    """Extract failsafe and event data."""
    result = {}

    # Failsafe flags
    ff = _get_topic_data(ulog, "failsafe_flags")
    if ff is not None:
        ts = _timestamps_to_seconds(ff["timestamp"])
        result["failsafe_timeline"] = {
            "duration_s": round(float(ts[-1] - ts[0]), 1) if len(ts) > 1 else 0,
            "sample_count": len(ts),
        }

    # Vehicle status for failsafe
    vs = _get_topic_data(ulog, "vehicle_status")
    if vs is not None:
        failsafe_vals = vs.get("failsafe", [])
        if len(failsafe_vals) > 0:
            failsafe_active = np.sum(np.asarray(failsafe_vals, dtype=bool))
            result["failsafe_active_count"] = int(failsafe_active)

    # Failure detector
    fd = _get_topic_data(ulog, "failure_detector_status")
    if fd is not None:
        result["failure_detector"] = {
            "sample_count": len(fd.get("timestamp", [])),
        }
        # Check for specific failure flags
        for key in fd:
            if key != "timestamp" and key != "timestamp_sample":
                vals = np.asarray(fd[key])
                if np.any(vals != 0):
                    result["failure_detector"][key] = _safe_stats(vals)

    # Events (logged messages)
    if hasattr(ulog, 'logged_messages'):
        messages = []
        for msg in ulog.logged_messages:
            messages.append({
                "timestamp_s": round((msg.timestamp - ulog.start_timestamp) / 1e6, 2),
                "level": msg.log_level_str() if hasattr(msg, 'log_level_str') else str(msg.log_level),
                "message": msg.message,
            })
        if messages:
            result["logged_messages"] = messages

    return result


def extract_wind_data(ulog: ULog) -> Dict[str, Any]:
    """Extract wind speed and variance from wind_estimate topic."""
    result = {}
    we = _get_topic_data(ulog, "wind_estimate")
    if we is not None and "windspeed_north" in we and "windspeed_east" in we:
        try:
            vn = np.asarray(we["windspeed_north"])
            ve = np.asarray(we["windspeed_east"])
            
            # Calculate horizontal wind speed: sqrt(north^2 + east^2)
            wind_speeds = np.sqrt(vn**2 + ve**2)
            if len(wind_speeds) > 0:
                avg_speed = float(np.mean(wind_speeds))
                max_speed = float(np.max(wind_speeds))
                
                # Categorize wind severity
                if avg_speed < 3.0:
                    status = "Hafif Rüzgar (Düşük Etki)"
                elif avg_speed < 8.0:
                    status = "Orta Rüzgar (Kontrolcü test edilebilir)"
                else:
                    status = "Kuvvetli Rüzgar (Güvenlik Riski, PID performansını düşürebilir)"
                    
                result = {
                    "avg_wind_speed_m_s": round(avg_speed, 2),
                    "max_wind_speed_m_s": round(max_speed, 2),
                    "wind_speed_status": status
                }
        except Exception as e:
            print(f"[LogParser] Wind calculation error: {e}")
    return result


# ---------------------------------------------------------------------------
# Main Report Generator
# ---------------------------------------------------------------------------

def parse_single_log(filepath: str) -> Dict[str, Any]:
    """Parse a single ULog file and return comprehensive analysis data.

    Returns a dictionary with all extracted data sections.
    """
    ulog = ULog(filepath)

    report = {
        "filepath": filepath,
        "parsed_at": datetime.now().isoformat(),
        "summary": extract_flight_summary(ulog, filepath),
        "attitude_tracking": extract_attitude_tracking(ulog),
        "battery": extract_battery_data(ulog),
        "vibration": extract_vibration_data(ulog),
        "ekf": extract_ekf_data(ulog),
        "actuators": extract_actuator_data(ulog),
        "pid_parameters": extract_pid_parameters(ulog),
        "failsafe_events": extract_failsafe_events(ulog),
        "wind": extract_wind_data(ulog),
    }

    # Add the persona specific datasets
    report["persona_dataset"] = build_persona_dataset(ulog, report)

    return report


def generate_text_report(report: Dict[str, Any]) -> str:
    """Convert parsed log data into a structured text report for LLM consumption."""
    lines = []
    s = report["summary"]

    lines.append("=" * 70)
    lines.append(f"FLIGHT LOG ANALYSIS REPORT: {s.get('file', 'Unknown')}")
    lines.append("=" * 70)

    # Summary section
    lines.append("\n## FLIGHT SUMMARY")
    lines.append(f"  File: {s.get('file', '?')} ({s.get('file_size_mb', '?')} MB)")
    lines.append(f"  Duration: {s.get('duration_str', '?')} ({s.get('duration_s', '?')}s)")
    lines.append(f"  Hardware: {s.get('hardware', '?')}")
    lines.append(f"  Firmware: {s.get('firmware', '?')}")
    lines.append(f"  VTOL: {s.get('is_vtol', '?')} | Vehicle Type: {s.get('vehicle_type', '?')}")
    lines.append(f"  Armed: {s.get('was_armed', '?')}")
    lines.append(f"  Preflight Checks: {'PASS' if s.get('preflight_pass') else 'FAIL/UNKNOWN'}")
    lines.append(f"  Max Altitude: {s.get('max_altitude_m', '?')}m")
    lines.append(f"  Nav States: {' → '.join(s.get('nav_state_transitions', ['?']))}")

    # Wind & Atmospheric conditions
    wind = report.get("wind", {})
    if wind:
        lines.append("\n## WIND & ATMOSPHERIC CONDITIONS")
        lines.append(f"  Estimated Horizontal Wind Speed: {wind.get('avg_wind_speed_m_s', 0.0)} m/s avg (max: {wind.get('max_wind_speed_m_s', 0.0)} m/s)")
        lines.append(f"  Wind Severity Status: {wind.get('wind_speed_status', 'Bilinmeyen / Tahmin Verisi Yok')}")

    # Attitude tracking
    att = report.get("attitude_tracking", {})
    if "error" not in att:
        lines.append("\n## ATTITUDE TRACKING PERFORMANCE")
        for axis in ["roll", "pitch", "yaw"]:
            if axis in att:
                a = att[axis]
                lines.append(f"  {axis.upper()}:")
                lines.append(f"    RMSE: {a['rmse_deg']}° | Max Error: {a['max_error_deg']}° | Mean Error: {a['mean_error_deg']}°")
                lines.append(f"    Actual range: [{a['actual_stats']['min']}°, {a['actual_stats']['max']}°]")
                lines.append(f"    Setpoint range: [{a['setpoint_stats']['min']}°, {a['setpoint_stats']['max']}°]")

        if "rate_tracking" in att:
            lines.append("  RATE TRACKING:")
            for axis, data in att["rate_tracking"].items():
                lines.append(f"    {axis}: RMSE={data['rmse_deg_s']}°/s, Max Error={data['max_error_deg_s']}°/s")
    else:
        lines.append(f"\n## ATTITUDE TRACKING: {att['error']}")

    # Battery
    bat = report.get("battery", {})
    if "error" not in bat:
        lines.append("\n## BATTERY STATUS")
        if "voltage" in bat:
            v = bat["voltage"]
            lines.append(f"  Voltage: {v['mean']}V avg (range: {v['min']}V – {v['max']}V)")
        if "current" in bat:
            c = bat["current"]
            lines.append(f"  Current: {c['mean']}A avg (max: {c['max']}A)")
        if "remaining" in bat:
            r = bat["remaining"]
            lines.append(f"  Remaining: {r['min']*100:.0f}% – {r['max']*100:.0f}%")
        if bat.get("anomalies"):
            for a in bat["anomalies"]:
                lines.append(f"  {a}")
        if "cell_voltages" in bat:
            lines.append("  Cell Voltages:")
            for cv in bat["cell_voltages"]:
                lines.append(f"    Cell {cv['cell']}: avg={cv['avg_v']}V, min={cv['min_v']}V")

    # Vibration
    vib = report.get("vibration", {})
    if vib:
        lines.append("\n## VIBRATION ANALYSIS")
        if "sample_rate_hz" in vib:
            lines.append(f"  IMU Sample Rate: {vib['sample_rate_hz']}Hz")
        for axis in ["accel_x", "accel_y", "accel_z"]:
            if axis in vib:
                v = vib[axis]
                lines.append(f"  {axis.upper()}: RMS={v['rms_m_s2']}m/s², Peak={v['peak_m_s2']}m/s²")
                if v.get("dominant_frequencies"):
                    freqs = ", ".join([f"{f['freq_hz']}Hz({f['magnitude']:.0f})" for f in v["dominant_frequencies"][:3]])
                    lines.append(f"    Dominant frequencies: {freqs}")
        for key in vib:
            if "clips" in key:
                lines.append(f"  ⚠️ IMU Clipping: {vib[key]} clips on {key}")

    # EKF
    ekf = report.get("ekf", {})
    if ekf:
        lines.append("\n## EKF / SENSOR FUSION")
        for label, data in ekf.items():
            if isinstance(data, dict) and "mean_ratio" in data:
                status = "⚠️ EXCEEDED" if data["times_exceeded_threshold"] > 0 else "✅ OK"
                lines.append(f"  {label}: mean={data['mean_ratio']}, max={data['max_ratio']} "
                             f"[{status} - exceeded {data['percent_exceeded']}% of time]")
        if "estimator_flags" in ekf:
            lines.append("  Estimator Flags:")
            for k, v in ekf["estimator_flags"].items():
                lines.append(f"    {k}: {'Active' if v else 'Inactive'}")
        for key in ekf:
            if key.startswith("gps_"):
                lines.append(f"  {key}: {ekf[key]}")

    # Actuators
    act = report.get("actuators", {})
    if act:
        lines.append("\n## ACTUATOR / MOTOR DATA")
        if "motor_balance" in act:
            mb = act["motor_balance"]
            status = "✅ BALANCED" if mb["balanced"] else "⚠️ IMBALANCED"
            lines.append(f"  Motor Balance: {status} (spread={mb['spread']})")
            for motor, mean_val in mb["individual_means"].items():
                lines.append(f"    {motor}: avg output = {mean_val}")

    # PID Parameters
    pid = report.get("pid_parameters", {})
    if pid:
        lines.append("\n## PID PARAMETERS (Current Settings)")
        for param, value in pid.items():
            lines.append(f"  {param} = {value}")

    # Failsafe & Events
    fs = report.get("failsafe_events", {})
    if fs:
        lines.append("\n## FAILSAFE & EVENTS")
        if fs.get("failsafe_active_count", 0) > 0:
            lines.append(f"  ⚠️ Failsafe activated {fs['failsafe_active_count']} times")
        if "logged_messages" in fs:
            lines.append("  Logged Messages:")
            for msg in fs["logged_messages"][:30]:  # Limit to 30 messages
                lines.append(f"    [{msg['timestamp_s']}s] [{msg['level']}] {msg['message']}")

    # Similar vehicles
    similar_md = get_similar_vehicles_markdown(report)
    lines.append("\n" + similar_md)

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def generate_multi_log_comparison(reports: List[Dict[str, Any]]) -> str:
    """Generate a comparison report across multiple log files for PID tuning progression."""
    lines = []
    lines.append("=" * 70)
    lines.append("MULTI-LOG COMPARISON REPORT")
    lines.append(f"Comparing {len(reports)} flight logs")
    lines.append("=" * 70)

    # Summary table
    lines.append("\n## FLIGHT OVERVIEW")
    lines.append(f"{'Log':<25} {'Duration':<12} {'Max Alt':<10} {'Armed':<8} {'Nav States'}")
    lines.append("-" * 90)
    for r in reports:
        s = r["summary"]
        lines.append(
            f"{s.get('file', '?'):<25} "
            f"{s.get('duration_str', '?'):<12} "
            f"{s.get('max_altitude_m', '?'):<10} "
            f"{str(s.get('was_armed', '?')):<8} "
            f"{' → '.join(s.get('nav_state_transitions', ['?'])[:4])}"
        )

    # Attitude tracking comparison
    lines.append("\n## ATTITUDE TRACKING COMPARISON (RMSE in degrees)")
    lines.append(f"{'Log':<25} {'Roll RMSE':<12} {'Pitch RMSE':<12} {'Yaw RMSE':<12}")
    lines.append("-" * 65)
    for r in reports:
        att = r.get("attitude_tracking", {})
        if "error" not in att:
            lines.append(
                f"{r['summary'].get('file', '?'):<25} "
                f"{att.get('roll', {}).get('rmse_deg', '?'):<12} "
                f"{att.get('pitch', {}).get('rmse_deg', '?'):<12} "
                f"{att.get('yaw', {}).get('rmse_deg', '?'):<12}"
            )

    # PID parameter comparison
    lines.append("\n## PID PARAMETER COMPARISON")
    # Collect all unique PID params
    all_params = set()
    for r in reports:
        all_params.update(r.get("pid_parameters", {}).keys())

    important_params = [p for p in sorted(all_params) if any(
        p.startswith(pre) for pre in ["MC_ROLLRATE_", "MC_PITCHRATE_", "MC_YAWRATE_"]
    )]

    if important_params:
        header = f"{'Parameter':<25}" + "".join(f" {r['summary'].get('file', '?')[:15]:<17}" for r in reports)
        lines.append(header)
        lines.append("-" * len(header))
        for param in important_params:
            row = f"{param:<25}"
            values = []
            for r in reports:
                val = r.get("pid_parameters", {}).get(param, "N/A")
                row += f" {str(val):<17}"
                values.append(val)
            # Mark if changed
            unique_vals = set(str(v) for v in values if v != "N/A")
            if len(unique_vals) > 1:
                row += " ← CHANGED"
            lines.append(row)

    # Battery comparison
    lines.append("\n## BATTERY COMPARISON")
    for r in reports:
        bat = r.get("battery", {})
        s = r["summary"]
        if "voltage" in bat:
            lines.append(f"  {s.get('file', '?')}: V={bat['voltage']['mean']}V, "
                         f"I={bat.get('current', {}).get('mean', '?')}A")
            if bat.get("anomalies"):
                for a in bat["anomalies"]:
                    lines.append(f"    {a}")

    # Vibration comparison
    lines.append("\n## VIBRATION COMPARISON (Accel RMS in m/s²)")
    lines.append(f"{'Log':<25} {'X RMS':<12} {'Y RMS':<12} {'Z RMS':<12}")
    lines.append("-" * 65)
    for r in reports:
        vib = r.get("vibration", {})
        lines.append(
            f"{r['summary'].get('file', '?'):<25} "
            f"{vib.get('accel_x', {}).get('rms_m_s2', 'N/A'):<12} "
            f"{vib.get('accel_y', {}).get('rms_m_s2', 'N/A'):<12} "
            f"{vib.get('accel_z', {}).get('rms_m_s2', 'N/A'):<12}"
        )

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_logs(log_dir: str) -> List[Dict[str, Any]]:
    """Discover all valid ULog files in a directory tree."""
    logs = []
    for root, dirs, files in os.walk(log_dir):
        for f in files:
            if f.endswith(".ulg"):
                path = os.path.join(root, f)
                size = os.path.getsize(path)
                if size > 1000:  # Skip empty/corrupt files
                    # Determine session/date from path
                    rel = os.path.relpath(path, log_dir)
                    parts = Path(rel).parts
                    session = parts[0] if len(parts) > 1 else "unknown"

                    logs.append({
                        "id": rel.replace(os.sep, "__").replace(".ulg", ""),
                        "path": path,
                        "filename": f,
                        "session": session,
                        "size_bytes": size,
                        "size_mb": round(size / 1024 / 1024, 1),
                        "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
                    })

    # Sort by modification time
    logs.sort(key=lambda x: x["modified"])
    return logs


# ---------------------------------------------------------------------------
# Vehicle Specifications & Similarity Matching
# ---------------------------------------------------------------------------

def get_vehicle_specs(report: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to extract vehicle specifications from parsed parameters or summary."""
    params = report.get("pid_parameters", {})
    summary = report.get("summary", {})
    
    is_vtol = summary.get("is_vtol", False)
    vehicle_type = summary.get("vehicle_type", 0)
    
    weight = params.get("WEIGHT_BASE") or params.get("WEIGHT_GROSS")
    wing_span = params.get("FW_WING_SPAN")
    ca_airframe = params.get("CA_AIRFRAME")
    rotor_count = params.get("CA_ROTOR_COUNT")
    vt_type = params.get("VT_TYPE")
    
    # Try to guess weight if not available
    if weight is None:
        weight = 23.50 if is_vtol else 2.0
        
    return {
        "is_vtol": is_vtol,
        "vehicle_type": vehicle_type,
        "weight_kg": weight,
        "wing_span_m": wing_span,
        "ca_airframe": ca_airframe,
        "rotor_count": rotor_count,
        "vt_type": vt_type,
        "hardware": summary.get("hardware", "Unknown"),
        "firmware": summary.get("firmware", "Unknown")
    }


def find_similar_vehicles(current_specs: Dict[str, Any], current_file: str) -> List[Dict[str, Any]]:
    """Scan all logs in the local log cache directory to find runs with similar hardware and configurations."""
    similar_runs = []
    cache_dir = "data/log_cache"
    if not os.path.exists(cache_dir):
        return []
        
    for f in os.listdir(cache_dir):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(cache_dir, f), "r", encoding="utf-8") as file:
                data = json.load(file)
                # Skip current log
                filepath = data.get("filepath", "")
                filename = data.get("summary", {}).get("file", "")
                if filepath == current_file or filename == os.path.basename(current_file):
                    continue
                
                # Extract properties
                s = data.get("summary", {})
                is_vtol = s.get("is_vtol", False)
                vehicle_type = s.get("vehicle_type", 0)
                pid = data.get("pid_parameters", {})
                weight = pid.get("WEIGHT_BASE") or pid.get("WEIGHT_GROSS")
                
                # Check config similarity
                if is_vtol == current_specs["is_vtol"] or vehicle_type == current_specs["vehicle_type"]:
                    # Match weight class if possible
                    curr_weight = current_specs.get("weight_kg")
                    if curr_weight is not None and weight is not None:
                        weight_diff = abs(curr_weight - weight) / curr_weight
                        if weight_diff > 0.35: # weight diff limit 35%
                            continue
                            
                    # Extract target properties for context
                    att = data.get("attitude_tracking", {})
                    vib = data.get("vibration", {})
                    similar_runs.append({
                        "filename": filename or os.path.basename(filepath),
                        "weight": weight or (23.50 if is_vtol else 2.0),
                        "rotors": pid.get("CA_ROTOR_COUNT") or (5 if is_vtol else 4),
                        "roll_rmse": att.get("roll", {}).get("rmse_deg", "N/A"),
                        "pitch_rmse": att.get("pitch", {}).get("rmse_deg", "N/A"),
                        "MC_ROLLRATE_P": pid.get("MC_ROLLRATE_P", "N/A"),
                        "MC_ROLLRATE_I": pid.get("MC_ROLLRATE_I", "N/A"),
                        "MC_PITCHRATE_P": pid.get("MC_PITCHRATE_P", "N/A"),
                        "MC_PITCHRATE_I": pid.get("MC_PITCHRATE_I", "N/A"),
                        "accel_x_rms": vib.get("accel_x", {}).get("rms_m_s2", "N/A"),
                        "accel_y_rms": vib.get("accel_y", {}).get("rms_m_s2", "N/A"),
                        "accel_z_rms": vib.get("accel_z", {}).get("rms_m_s2", "N/A"),
                    })
        except Exception as e:
            print(f"[similar_runs] Error reading cached log {f}: {e}")
            
    return similar_runs


def format_similar_vehicles_context(similar_runs: List[Dict[str, Any]]) -> str:
    """Format similar vehicle runs as a beautiful Markdown reference table."""
    if not similar_runs:
        return "## BENZER ARAÇLAR REFERANS VERİSİ\nSistemde daha önce analiz edilmiş benzer özellikte bir araç bulunamadı."
        
    lines = []
    lines.append("## BENZER ARAÇLAR REFERANS VERİSİ (Filo Analizi)")
    lines.append("Daha önce başarılı veya başarısız uçuş gerçekleştirmiş benzer özellikteki İHA'ların verileri:")
    lines.append("")
    lines.append("| Dosya | Ağırlık | Motor Sayısı | Roll RMSE | Pitch RMSE | MC_ROLLRATE_P/I | MC_PITCHRATE_P/I | Titreşim RMS (X/Y/Z) |")
    lines.append("|-------|---------|--------------|-----------|------------|-----------------|------------------|----------------------|")
    
    for r in similar_runs:
        lines.append(
            f"| {r['filename']} | {r['weight']} kg | {r['rotors']} | {r['roll_rmse']}° | {r['pitch_rmse']}° | "
            f"{r['MC_ROLLRATE_P']}/{r['MC_ROLLRATE_I']} | {r['MC_PITCHRATE_P']}/{r['MC_PITCHRATE_I']} | "
            f"{r['accel_x_rms']}/{r['accel_y_rms']}/{r['accel_z_rms']} |"
        )
        
    lines.append("")
    lines.append("> [!TIP]")
    lines.append("> Uzmanlar, yukarıdaki benzer araçların parametrelerini ve elde ettikleri RMSE takip başarımlarını referans alarak yeni parametre önerilerinde bulunmalıdır.")
    return "\n".join(lines)


def get_similar_vehicles_markdown(report: Dict[str, Any]) -> str:
    """Convenience helper to get similar vehicles as markdown."""
    specs = get_vehicle_specs(report)
    similar_runs = find_similar_vehicles(specs, report.get("filepath", ""))
    return format_similar_vehicles_context(similar_runs)


# ---------------------------------------------------------------------------
# Persona-Specific Grounding and Context Formatting
# ---------------------------------------------------------------------------

def build_persona_dataset(ulog: ULog, report: Dict[str, Any]) -> Dict[str, Any]:
    """Build a persona-specific dataset for each of the 3 expert personas,
    incorporating the grounding and context-reduction design from ornek_log_extractor.py.
    
    Persona mapping:
    - pid_tuning_expert: Attitude tracking, rate tracking, PID/Position/FW parameters
    - hardware_diagnostics_expert: Vibration, FFT, motor balance, notch filter params
    - sensor_safety_expert: EKF, GPS, compass, battery, failsafe, safety params
    """
    dataset = {}

    # Helper to get parameter subsets
    all_params = report.get("pid_parameters", {})
    def filter_params(prefixes: List[str]) -> Dict[str, Any]:
        return {k: v for k, v in all_params.items() if any(k.startswith(p) for p in prefixes)}

    # Helper to filter logged messages
    logged_messages = report.get("failsafe_events", {}).get("logged_messages", [])
    def filter_messages(keywords: List[str]) -> List[Dict[str, Any]]:
        return [
            m for m in logged_messages
            if any(k.lower() in m["message"].lower() for k in keywords)
        ]

    # --- GENEL (General Flight Dataset, shared by all personas) ---
    genel = {"veri_durumu": "ok"}
    pos_data = _get_topic_data(ulog, "vehicle_local_position")
    if pos_data is None:
        genel["altitude"] = "veri yok (vehicle_local_position bulunamadı)"
    else:
        z = -np.asarray(pos_data.get("z", [0]))
        t = np.asarray(pos_data.get("timestamp", [0])) / 1e6
        genel["altitude_min_m"] = round(float(np.min(z)), 2) if len(z) > 0 else 0.0
        genel["altitude_max_m"] = round(float(np.max(z)), 2) if len(z) > 0 else 0.0
        genel["duration_sec"] = round(float(t[-1] - t[0]), 1) if len(t) > 1 else 0.0

        x = np.asarray(pos_data.get("x", [0]))
        y = np.asarray(pos_data.get("y", [0]))
        if len(x) > 0 and len(y) > 0:
            genel["hover_xy_stddev_m"] = round(float(np.sqrt(np.std(x) ** 2 + np.std(y) ** 2)), 3)
        else:
            genel["hover_xy_stddev_m"] = 0.0

    status_data = _get_topic_data(ulog, "vehicle_status")
    if status_data is not None and "nav_state" in status_data:
        states, counts = np.unique(status_data["nav_state"], return_counts=True)
        genel["nav_state_gozlemleri"] = {int(s): int(c) for s, c in zip(states, counts)}

    genel["actuators"] = report.get("actuators", {})
    genel["wind"] = report.get("wind", {})
    dataset["genel"] = genel

    # --- 1. PID Tuning Expert (Kontrol Mühendisi Deniz) Dataset ---
    att_tracking = report.get("attitude_tracking", {})
    pid_tuning_expert = {"veri_durumu": "ok"}
    if "error" in att_tracking:
        pid_tuning_expert["veri_durumu"] = f"veri yok ({att_tracking['error']})"
    else:
        pid_tuning_expert.update(att_tracking)
    pid_tuning_expert["ilgili_parametreler"] = filter_params([
        "MC_ROLLRATE", "MC_PITCHRATE", "MC_YAWRATE",
        "MC_ROLL_P", "MC_PITCH_P", "MC_YAW_P", "MC_YAW_WEIGHT",
        "MC_AT_",  # Autotune params
        "MPC_XY_", "MPC_Z_", "MPC_ACC_",  # Position/velocity controller
        "FW_R_", "FW_P_", "FW_Y_",  # Fixed-wing controller
        "VT_",  # VTOL transition parameters
    ])
    # Include motor balance for cross-coupling context
    pid_tuning_expert["motor_balance"] = report.get("actuators", {}).get("motor_balance", {})
    dataset["pid_tuning_expert"] = pid_tuning_expert

    # --- 2. Hardware Diagnostics Expert (Saha Mühendisi Kemal) Dataset ---
    vib_data = report.get("vibration", {})
    hardware_diagnostics_expert = {"veri_durumu": "ok"}
    
    # Run Gyro FFT just like ornek_log_extractor.py
    gyro_fft_success = False
    gyro = _get_topic_data(ulog, "sensor_combined") or _get_topic_data(ulog, "sensor_gyro")
    if gyro is not None:
        field = "x" if "x" in gyro else "gyro_rad[0]"
        if field in gyro:
            t = np.asarray(gyro["timestamp"]) / 1e6
            signal = np.asarray(gyro[field])
            fft_window = min(4096, 2 ** int(math.log2(len(signal)))) if len(signal) > 0 else 0
            if fft_window >= 128:
                dt = float(np.median(np.diff(t)))
                fs = 1.0 / dt if dt > 0 else 0
                if fs > 0:
                    window = signal[:fft_window] - np.mean(signal[:fft_window])
                    fft_vals = np.abs(np.fft.rfft(window))
                    freqs = np.fft.rfftfreq(fft_window, d=dt)

                    mask = freqs > 5.0
                    idx = np.argsort(fft_vals[mask])[::-1][:3]
                    peaks = [
                        {"freq_hz": round(float(freqs[mask][i]), 1), "magnitude": round(float(fft_vals[mask][i]), 2)}
                        for i in idx
                    ]
                    hardware_diagnostics_expert["sample_rate_hz_approx"] = round(fs, 1)
                    hardware_diagnostics_expert["dominant_peaks"] = peaks
                    gyro_fft_success = True

    if not gyro_fft_success:
        hardware_diagnostics_expert["dominant_peaks"] = "veri yok (FFT için yeterli gyro verisi bulunamadı)"

    hardware_diagnostics_expert["accel_vibration"] = {
        k: v for k, v in vib_data.items()
        if k in ["accel_x", "accel_y", "accel_z", "sample_rate_hz"]
    }
    hardware_diagnostics_expert["gyro_vibration_rms_peak"] = {
        k: v for k, v in vib_data.items()
        if "gyro_" in k
    }
    hardware_diagnostics_expert["imu_clipping"] = {
        k: v for k, v in vib_data.items()
        if "clips" in k
    }
    hardware_diagnostics_expert["ilgili_parametreler"] = filter_params([
        "IMU_GYRO_CUTOFF", "IMU_GYRO_NF", "IMU_ACCEL_CUTOFF", "IMU_DGYRO_CUTOFF",
        "CA_ROTOR",  # Motor geometry for CoG analysis
    ])
    # Include full motor/actuator data for CoG and motor balance analysis
    hardware_diagnostics_expert["motor_data"] = report.get("actuators", {})
    dataset["hardware_diagnostics_expert"] = hardware_diagnostics_expert

    # --- 3. Sensor & Safety Expert (Dr. Güvenlik) Dataset ---
    ekf_data = report.get("ekf", {})
    battery_data = report.get("battery", {})
    failsafe_events = report.get("failsafe_events", {})
    
    sensor_safety_expert = {"veri_durumu": "ok"}
    # EKF data
    sensor_safety_expert["ekf"] = ekf_data
    sensor_safety_expert["ekf_parametreleri"] = filter_params([
        "EKF2_GPS", "EKF2_MAG", "EKF2_HGT", "EKF2_NOAID", "EKF2_REQ", "EKF2_BARO"
    ])
    sensor_safety_expert["compass_ve_gps_mesajlari"] = filter_messages(["compass", "gps", "heading", "mag"])
    
    # Battery & Safety data
    if "error" in battery_data:
        sensor_safety_expert["battery"] = "veri yok (battery_status bulunamadı)"
    else:
        sensor_safety_expert["battery"] = {
            "min_v": battery_data.get("voltage", {}).get("min", 0.0),
            "max_v": battery_data.get("voltage", {}).get("max", 0.0),
            "negatif_veya_sifir_okuma_sayisi": battery_data.get("negative_voltage_count", 0),
            "toplam_ornek": battery_data.get("voltage", {}).get("count", 0),
            "anomalies": battery_data.get("anomalies", [])
        }
    
    sensor_safety_expert["failsafe_timeline"] = failsafe_events.get("failsafe_timeline", {})
    sensor_safety_expert["failsafe_active_count"] = failsafe_events.get("failsafe_active_count", 0)
    sensor_safety_expert["failure_detector"] = failsafe_events.get("failure_detector", {})
    sensor_safety_expert["preflight_ve_failsafe_mesajlari"] = filter_messages([
        "preflight", "failsafe", "fail", "emergency", "warn"
    ])
    sensor_safety_expert["guvenlik_parametreleri"] = filter_params([
        "COM_LOW_BAT", "BAT_CRIT", "BAT_EMERGEN", "BAT_LOW",
        "NAV_RCL", "NAV_DLL", "GF_ACTION", "RTL_",
        "COM_ARM_", "COM_PREARM",
    ])
    dataset["sensor_safety_expert"] = sensor_safety_expert
    
    # Add vehicle specs & similar runs to the dataset (shared)
    specs = get_vehicle_specs(report)
    similar_runs = find_similar_vehicles(specs, report.get("filepath", ""))
    dataset["similar_vehicles"] = similar_runs

    return dataset


def format_context_block(persona_id: str, dataset: Dict[str, Any]) -> str:
    """Turn extracted data into a markdown block to inject as a user
    message alongside the persona's system prompt."""
    persona_data = dataset.get(persona_id, {"veri_durumu": "veri yok"})
    genel = dataset.get("genel", {})
    similar = dataset.get("similar_vehicles", [])
    
    similar_text = ""
    if similar:
        similar_text = "\n### Benzer Araçların Özellikleri ve Parametreleri (Filo Referansı)\n"
        for r in similar:
            similar_text += (
                f"- **Dosya:** {r['filename']}, **Ağırlık:** {r['weight']} kg, **Rotor:** {r['rotors']}, "
                f"**Roll RMSE:** {r['roll_rmse']}°, **Pitch RMSE:** {r['pitch_rmse']}°\n"
                f"  *Önemli Parametreler:* MC_ROLLRATE_P={r['MC_ROLLRATE_P']}, MC_ROLLRATE_I={r['MC_ROLLRATE_I']}, "
                f"MC_PITCHRATE_P={r['MC_PITCHRATE_P']}, MC_PITCHRATE_I={r['MC_PITCHRATE_I']}\n"
            )
            
    return f"""## Bu Log İçin Çıkarılmış Veri (GERÇEK — sadece bunu kullan, dışına çıkma)

### Genel Uçuş Bilgisi
```json
{json.dumps(genel, ensure_ascii=False, indent=2)}
```
{similar_text}
### Senin Uzmanlık Alanına Özel Veri
```json
{json.dumps(persona_data, ensure_ascii=False, indent=2)}
```

Yukarıdaki veri ve referanslar dışında hiçbir sayısal değer (RMSE, frekans, voltaj, parametre
değeri vb.) kullanma. Bir alan "veri yok" diyorsa o konuda kesin bulgu değil,
en fazla "veri toplanmalı" önerisi sun.
"""
