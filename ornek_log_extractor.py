"""ULog data extraction for the UAV Log Analysis Council.

This module is the missing "grounding" layer: it reads a PX4 .ulg file
with pyulog and turns it into small, structured, PERSONA-SPECIFIC data
blocks that get injected into each persona's prompt. This is what lets
personas stop guessing and start citing real numbers.

Design principle: every function returns a plain dict of numbers/strings
(no numpy types, no NaN silently hidden) so it can be safely dropped into
an f-string or json.dumps() and handed to an LLM.
"""

from __future__ import annotations

import math
import json
from typing import Dict, List, Optional, Any

import numpy as np
from pyulog import ULog


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def load_log(path: str) -> ULog:
    """Load a .ulg file. Raises if the file is corrupt/unreadable."""
    return ULog(path)


def get_dataset(ulog: ULog, name: str, instance: int = 0):
    """Return the pyulog Dataset for a topic, or None if not logged.

    IMPORTANT: returning None here (instead of raising) is what lets the
    extraction functions below produce "veri yok" instead of crashing —
    and it's what lets the personas honestly say a topic wasn't logged.
    """
    for d in ulog.data_list:
        if d.name == name and d.multi_id == instance:
            return d
    return None


def _safe_float(x) -> Optional[float]:
    try:
        v = float(x)
        return None if (math.isnan(v) or math.isinf(v)) else v
    except (TypeError, ValueError):
        return None


def quat_to_euler_deg(q0, q1, q2, q3):
    """Convert PX4 quaternion (w,x,y,z order) arrays to roll/pitch/yaw degrees."""
    q0, q1, q2, q3 = map(np.asarray, (q0, q1, q2, q3))
    roll = np.arctan2(2 * (q0 * q1 + q2 * q3), 1 - 2 * (q1 ** 2 + q2 ** 2))
    pitch = np.arcsin(np.clip(2 * (q0 * q2 - q3 * q1), -1.0, 1.0))
    yaw = np.arctan2(2 * (q0 * q3 + q1 * q2), 1 - 2 * (q2 ** 2 + q3 ** 2))
    return np.degrees(roll), np.degrees(pitch), np.degrees(yaw)


def get_relevant_params(ulog: ULog, prefixes: List[str]) -> Dict[str, float]:
    """Real current parameter values from the log — this is what fixes the
    'Mevcut Değer' hallucination problem. `ulog.initial_parameters` holds
    every parameter as it was armed at flight start."""
    out = {}
    for name, value in ulog.initial_parameters.items():
        if any(name.startswith(p) for p in prefixes):
            out[name] = value
    return out


def get_logged_messages(ulog: ULog, keywords: Optional[List[str]] = None) -> List[Dict]:
    """Text messages PX4 logged during flight (preflight fails, failsafe
    triggers, mode changes, warnings). Filters by keyword if given."""
    result = []
    for m in ulog.logged_messages:
        text = m.message
        if keywords and not any(k.lower() in text.lower() for k in keywords):
            continue
        result.append({
            "t_sec": round(m.timestamp / 1e6, 2),
            "level": m.log_level,
            "message": text,
        })
    return result


# ---------------------------------------------------------------------------
# Domain-specific extractors — one per persona's focus area
# ---------------------------------------------------------------------------

def extract_general_flight(ulog: ULog) -> Dict[str, Any]:
    """For: Test Pilotu Ece (and shared context for everyone)."""
    out: Dict[str, Any] = {"veri_durumu": "ok"}

    pos = get_dataset(ulog, "vehicle_local_position")
    if pos is None:
        out["altitude"] = "veri yok (vehicle_local_position bulunamadı)"
    else:
        z = -np.asarray(pos.data["z"])  # NED -> altitude up
        t = np.asarray(pos.data["timestamp"]) / 1e6
        out["altitude_min_m"] = round(float(np.min(z)), 2)
        out["altitude_max_m"] = round(float(np.max(z)), 2)
        out["duration_sec"] = round(float(t[-1] - t[0]), 1)

        # crude position-hold quality: stddev of horizontal position
        # during the flight (only meaningful for hover/loiter tests)
        x, y = np.asarray(pos.data["x"]), np.asarray(pos.data["y"])
        out["hover_xy_stddev_m"] = round(float(np.sqrt(np.std(x) ** 2 + np.std(y) ** 2)), 3)

    status = get_dataset(ulog, "vehicle_status")
    if status is not None and "nav_state" in status.data:
        states, counts = np.unique(status.data["nav_state"], return_counts=True)
        out["nav_state_gozlemleri"] = {int(s): int(c) for s, c in zip(states, counts)}

    return out


def extract_attitude_tracking(ulog: ULog) -> Dict[str, Any]:
    """For: Prof. Aerodinamik (PID expert)."""
    att = get_dataset(ulog, "vehicle_attitude")
    sp = get_dataset(ulog, "vehicle_attitude_setpoint")
    if att is None:
        return {"veri_durumu": "veri yok (vehicle_attitude bulunamadı)"}

    r, p, y = quat_to_euler_deg(att.data["q[0]"], att.data["q[1]"],
                                 att.data["q[2]"], att.data["q[3]"])
    t = np.asarray(att.data["timestamp"]) / 1e6
    out: Dict[str, Any] = {
        "veri_durumu": "ok",
        "roll_deg_range": [round(float(np.min(r)), 2), round(float(np.max(r)), 2)],
        "pitch_deg_range": [round(float(np.min(p)), 2), round(float(np.max(p)), 2)],
        "sample_hz_approx": round(1.0 / float(np.median(np.diff(t))), 1) if len(t) > 1 else None,
    }

    if sp is not None and "q_d[0]" in sp.data:
        rs, ps, ys = quat_to_euler_deg(sp.data["q_d[0]"], sp.data["q_d[1]"],
                                        sp.data["q_d[2]"], sp.data["q_d[3]"])
        ts = np.asarray(sp.data["timestamp"]) / 1e6
        # interpolate setpoint onto attitude timestamps for RMSE
        rs_i = np.interp(t, ts, rs)
        ps_i = np.interp(t, ts, ps)
        out["roll_rmse_deg"] = round(float(np.sqrt(np.mean((r - rs_i) ** 2))), 3)
        out["pitch_rmse_deg"] = round(float(np.sqrt(np.mean((p - ps_i) ** 2))), 3)
    else:
        out["setpoint_karsilastirmasi"] = "veri yok (vehicle_attitude_setpoint bulunamadı)"

    out["ilgili_parametreler"] = get_relevant_params(
        ulog, ["MC_ROLLRATE", "MC_PITCHRATE", "MC_YAWRATE", "MC_ROLL_P", "MC_PITCH_P", "MC_YAW_P"]
    )
    return out


def extract_vibration(ulog: ULog, fft_window: int = 4096) -> Dict[str, Any]:
    """For: Saha Mühendisi Kemal (vibration analyst)."""
    gyro = get_dataset(ulog, "sensor_gyro") or get_dataset(ulog, "sensor_combined")
    if gyro is None:
        return {"veri_durumu": "veri yok (sensor_gyro/sensor_combined bulunamadı)"}

    field = "x" if "x" in gyro.data else "gyro_rad[0]"
    if field not in gyro.data:
        return {"veri_durumu": "veri yok (uygun gyro alanı bulunamadı)"}

    t = np.asarray(gyro.data["timestamp"]) / 1e6
    signal = np.asarray(gyro.data[field])
    if len(signal) < fft_window:
        return {"veri_durumu": f"veri yok (örnek sayısı {len(signal)}, FFT için yetersiz)"}

    dt = float(np.median(np.diff(t)))
    fs = 1.0 / dt if dt > 0 else None
    if not fs:
        return {"veri_durumu": "veri yok (örnekleme frekansı hesaplanamadı)"}

    window = signal[:fft_window] - np.mean(signal[:fft_window])
    fft_vals = np.abs(np.fft.rfft(window))
    freqs = np.fft.rfftfreq(fft_window, d=dt)

    # top 3 peaks above 5Hz (ignore DC/attitude-band content)
    mask = freqs > 5.0
    idx = np.argsort(fft_vals[mask])[::-1][:3]
    peaks = [
        {"freq_hz": round(float(freqs[mask][i]), 1), "magnitude": round(float(fft_vals[mask][i]), 2)}
        for i in idx
    ]

    return {
        "veri_durumu": "ok",
        "sample_rate_hz_approx": round(fs, 1),
        "dominant_peaks": peaks,
        "ilgili_parametreler": get_relevant_params(
            ulog, ["IMU_GYRO_CUTOFF", "IMU_GYRO_NF", "IMU_ACCEL_CUTOFF"]
        ),
    }


def extract_ekf_health(ulog: ULog) -> Dict[str, Any]:
    """For: Dr. Sensör (sensor fusion expert)."""
    innov = get_dataset(ulog, "estimator_innovation_test_ratios")
    if innov is None:
        return {"veri_durumu": "veri yok (estimator_innovation_test_ratios bulunamadı)"}

    out: Dict[str, Any] = {"veri_durumu": "ok", "innovation_ozetleri": {}}
    for key in innov.data:
        if key == "timestamp":
            continue
        arr = np.asarray(innov.data[key], dtype=float)
        arr = arr[~np.isnan(arr)]
        if len(arr) == 0:
            continue
        out["innovation_ozetleri"][key] = {
            "max": round(float(np.max(arr)), 3),
            "mean": round(float(np.mean(arr)), 3),
            "gate_asim_sayisi_1_0_uzeri": int(np.sum(arr > 1.0)),
        }

    out["ilgili_parametreler"] = get_relevant_params(
        ulog, ["EKF2_GPS", "EKF2_MAG", "EKF2_HGT", "EKF2_NOAID", "EKF2_REQ"]
    )
    out["compass_ve_gps_mesajlari"] = get_logged_messages(
        ulog, keywords=["compass", "gps", "heading", "mag"]
    )
    return out


def extract_safety(ulog: ULog) -> Dict[str, Any]:
    """For: Kaptan Güvenlik (safety officer)."""
    out: Dict[str, Any] = {"veri_durumu": "ok"}

    batt = get_dataset(ulog, "battery_status")
    if batt is not None and "voltage_v" in batt.data:
        v = np.asarray(batt.data["voltage_v"], dtype=float)
        out["battery"] = {
            "min_v": round(float(np.min(v)), 2),
            "max_v": round(float(np.max(v)), 2),
            "negatif_veya_sifir_okuma_sayisi": int(np.sum(v <= 0)),
            "toplam_ornek": int(len(v)),
        }
    else:
        out["battery"] = "veri yok (battery_status bulunamadı)"

    out["preflight_ve_failsafe_mesajlari"] = get_logged_messages(
        ulog, keywords=["preflight", "failsafe", "fail", "emergency", "warn"]
    )
    out["ilgili_parametreler"] = get_relevant_params(
        ulog, ["COM_LOW_BAT", "BAT_CRIT", "BAT_EMERGEN", "BAT_LOW", "NAV_RCL", "NAV_DLL", "GF_ACTION", "RTL_"]
    )
    return out


# ---------------------------------------------------------------------------
# Orchestration: one shared extraction pass -> per-persona context blocks
# ---------------------------------------------------------------------------

EXTRACTORS = {
    "pid_expert": extract_attitude_tracking,
    "vibration_analyst": extract_vibration,
    "sensor_fusion_expert": extract_ekf_health,
    "safety_officer": extract_safety,
    "test_pilot": extract_general_flight,
}


def build_flight_dataset(ulog_path: str) -> Dict[str, Any]:
    """Run every extractor once and return a dict keyed by persona id.
    Call this ONCE per log; reuse the result for all council members."""
    ulog = load_log(ulog_path)
    dataset = {"genel": extract_general_flight(ulog)}
    for persona_id, fn in EXTRACTORS.items():
        if persona_id == "test_pilot":
            continue  # already computed as "genel"
        dataset[persona_id] = fn(ulog)
    dataset["test_pilot"] = dataset["genel"]
    return dataset


def format_context_block(persona_id: str, dataset: Dict[str, Any]) -> str:
    """Turn extracted data into a markdown block to inject as a user
    message alongside the persona's system prompt."""
    persona_data = dataset.get(persona_id, {"veri_durumu": "veri yok"})
    genel = dataset.get("genel", {})
    return f"""## Bu Log İçin Çıkarılmış Veri (GERÇEK — sadece bunu kullan, dışına çıkma)

### Genel Uçuş Bilgisi
```json
{json.dumps(genel, ensure_ascii=False, indent=2)}
```

### Senin Uzmanlık Alanına Özel Veri
```json
{json.dumps(persona_data, ensure_ascii=False, indent=2)}
```

Yukarıdaki veri dışında hiçbir sayısal değer (RMSE, frekans, voltaj, parametre
değeri vb.) kullanma. Bir alan "veri yok" diyorsa o konuda kesin bulgu değil,
en fazla "veri toplanmalı" önerisi sun.
"""