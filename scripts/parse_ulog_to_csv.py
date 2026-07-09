#!/usr/bin/env python3
"""Convert PX4 ULog files to CSV, optionally filtering to flight-only data.

By default, CSV output is filtered to the actual flight window (takeoff → landing)
using `vehicle_land_detected`. Use `--no-flight-filter` to keep the full log.
"""
import os
import sys
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from pyulog import ULog

# Curated set of relevant topics for analyzing the council's claims:
# - vibration/accel/gyro: sensor_combined, sensor_accel, sensor_gyro
# - PID tracking/att/rates: vehicle_attitude, vehicle_attitude_setpoint, vehicle_angular_velocity, vehicle_rates_setpoint
# - actuators/motors: actuator_motors, actuator_outputs
# - battery/voltage: battery_status
# - EKF/GPS/estimation: estimator_innovation_test_ratios, estimator_status_flags, vehicle_gps_position, vehicle_status, vehicle_local_position
CURATED_TOPICS = (
    "sensor_combined,"
    "sensor_accel,"
    "sensor_gyro,"
    "vehicle_attitude,"
    "vehicle_attitude_setpoint,"
    "vehicle_angular_velocity,"
    "vehicle_rates_setpoint,"
    "actuator_motors,"
    "actuator_outputs,"
    "battery_status,"
    "estimator_innovation_test_ratios,"
    "estimator_status_flags,"
    "vehicle_gps_position,"
    "vehicle_status,"
    "vehicle_local_position"
)


def detect_flight_window_from_ulog(ulog_path: str):
    """Detect takeoff→landing timestamps from a ULog file.

    Returns (takeoff_us, landing_us) or None if detection fails.
    """
    try:
        ulog = ULog(ulog_path)
    except Exception as e:
        print(f"  ⚠️ ULog okunamadı: {e}")
        return None

    # Primary: vehicle_land_detected
    ld_matches = [d for d in ulog.data_list if d.name == "vehicle_land_detected"]
    if ld_matches:
        ld = ld_matches[0].data
        if "landed" in ld:
            landed = np.asarray(ld["landed"], dtype=int)
            ts = np.asarray(ld["timestamp"])
            if len(landed) > 1:
                transitions = np.diff(landed)
                takeoff_indices = np.where(transitions == -1)[0] + 1
                landing_indices = np.where(transitions == 1)[0] + 1

                # Handle case where log starts already in the air
                if landed[0] == 0:
                    takeoff_indices = np.concatenate([[0], takeoff_indices])

                segments = []
                for to_idx in takeoff_indices:
                    later = landing_indices[landing_indices > to_idx]
                    if len(later) > 0:
                        segments.append((int(ts[to_idx]), int(ts[later[0]])))
                    else:
                        segments.append((int(ts[to_idx]), int(ts[-1])))

                if segments:
                    longest = max(segments, key=lambda s: s[1] - s[0])
                    dur = (longest[1] - longest[0]) / 1e6
                    total = (ulog.last_timestamp - ulog.start_timestamp) / 1e6
                    print(f"  ✈️  Uçuş penceresi: {dur:.1f}s / {total:.1f}s ({dur/total*100:.1f}%) [vehicle_land_detected]")
                    return longest

    # Fallback: arming_state
    vs_matches = [d for d in ulog.data_list if d.name == "vehicle_status"]
    if vs_matches:
        vs = vs_matches[0].data
        if "arming_state" in vs:
            arming = np.asarray(vs["arming_state"], dtype=int)
            ts = np.asarray(vs["timestamp"])
            armed_mask = arming == 2
            if np.any(armed_mask):
                transitions = np.diff(armed_mask.astype(int))
                arm_indices = np.where(transitions == 1)[0] + 1
                disarm_indices = np.where(transitions == -1)[0] + 1
                if armed_mask[0]:
                    arm_indices = np.concatenate([[0], arm_indices])

                segments = []
                for arm_idx in arm_indices:
                    later = disarm_indices[disarm_indices > arm_idx]
                    if len(later) > 0:
                        segments.append((int(ts[arm_idx]), int(ts[later[0]])))
                    else:
                        segments.append((int(ts[arm_idx]), int(ts[-1])))

                if segments:
                    longest = max(segments, key=lambda s: s[1] - s[0])
                    dur = (longest[1] - longest[0]) / 1e6
                    total = (ulog.last_timestamp - ulog.start_timestamp) / 1e6
                    print(f"  ✈️  Uçuş penceresi: {dur:.1f}s / {total:.1f}s ({dur/total*100:.1f}%) [arming_state fallback]")
                    return longest

    print("  ⚠️ Uçuş penceresi tespit edilemedi, tüm veri korunuyor.")
    return None


def filter_csvs_to_flight_window(csv_dir: str, takeoff_us: int, landing_us: int):
    """Filter all CSV files in a directory to the flight window timestamps."""
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    filtered_count = 0

    for csv_file in csv_files:
        csv_path = os.path.join(csv_dir, csv_file)
        try:
            df = pd.read_csv(csv_path)
            if "timestamp" not in df.columns:
                continue

            original_rows = len(df)
            df = df[(df["timestamp"] >= takeoff_us) & (df["timestamp"] <= landing_us)]
            if len(df) == 0:
                # Remove empty files
                os.remove(csv_path)
                continue

            df.to_csv(csv_path, index=False)
            filtered_count += 1
        except Exception:
            continue  # Skip non-parseable CSVs

    print(f"  🔍 {filtered_count}/{len(csv_files)} CSV dosyası uçuş penceresine göre filtrelendi.")


def parse_ulog(ulog_path: str, output_dir: str, all_topics: bool = False,
               flight_filter: bool = True):
    """Converts a single .ulg file to CSVs in a target directory."""
    ulog_path = os.path.abspath(ulog_path)
    if not os.path.exists(ulog_path):
        print(f"Hata: Log dosyası bulunamadı: {ulog_path}")
        return False

    basename = Path(ulog_path).stem
    log_output_dir = os.path.join(output_dir, basename)
    os.makedirs(log_output_dir, exist_ok=True)

    print(f"\n[ULog -> CSV] İşleniyor: {basename}")
    print(f"Kaynak: {ulog_path}")
    print(f"Hedef Klasör: {log_output_dir}")

    cmd = ["/home/batuhanfurkan5/.local/bin/ulog2csv", "-o", log_output_dir]
    if not all_topics:
        cmd.extend(["-m", CURATED_TOPICS])
        print("Mod: Filtrelenmiş (Sadece iddialarla ilgili kritik topicler çıkarılıyor)")
    else:
        print("Mod: Tam (Tüm topicler çıkarılıyor, bu işlem zaman alabilir)")

    cmd.append(ulog_path)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        file_count = len(os.listdir(log_output_dir))
        print(f"Başarıyla tamamlandı! Çıkarılan dosyalar: {file_count} adet.")

        # Apply flight window filter
        if flight_filter:
            window = detect_flight_window_from_ulog(ulog_path)
            if window:
                filter_csvs_to_flight_window(log_output_dir, window[0], window[1])

        return True
    except subprocess.CalledProcessError as e:
        print(f"Hata oluştu! Hata kodu: {e.returncode}")
        print(f"Stderr: {e.stderr}")
        print(f"Stdout: {e.stdout}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Kullanım:")
        print("  python parse_ulog_to_csv.py <dosya_veya_klasör_yolu> [--all] [--no-flight-filter]")
        print("\nÖrnek:")
        print("  python parse_ulog_to_csv.py /path/to/log.ulg")
        print("  python parse_ulog_to_csv.py /path/to/log_folder --all")
        print("  python parse_ulog_to_csv.py /path/to/log.ulg --no-flight-filter")
        print("\nVarsayılan olarak CSV'ler uçuş penceresi (takeoff→landing) ile filtrelenir.")
        sys.exit(1)

    target_path = sys.argv[1]
    all_topics = "--all" in sys.argv
    flight_filter = "--no-flight-filter" not in sys.argv

    output_base_dir = "/home/batuhanfurkan5/Downloads/parsed_csvs"
    
    if os.path.isdir(target_path):
        # Process all .ulg files in directory
        ulog_files = [os.path.join(target_path, f) for f in os.listdir(target_path) if f.endswith(".ulg")]
        if not ulog_files:
            print(f"Hata: Klasörde hiçbir .ulg dosyası bulunamadı: {target_path}")
            sys.exit(1)
        
        print(f"Klasörde {len(ulog_files)} adet .ulg dosyası bulundu. İşlem başlatılıyor...")
        if flight_filter:
            print("📌 Uçuş penceresi filtresi AKTİF (devre dışı bırakmak için: --no-flight-filter)")
        success_count = 0
        for f in ulog_files:
            if parse_ulog(f, output_base_dir, all_topics, flight_filter):
                success_count += 1
        print(f"\nTamamlandı! {success_count}/{len(ulog_files)} dosya başarıyla CSV'ye dönüştürüldü.")
    else:
        parse_ulog(target_path, output_base_dir, all_topics, flight_filter)

if __name__ == "__main__":
    main()

