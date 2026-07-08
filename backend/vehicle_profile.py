"""Vehicle profile modeling and utility functions."""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class VehicleProfile:
    is_vtol: bool = False
    vehicle_type: str = "Unknown"  # e.g., "Multirotor", "Fixed Wing", "VTOL", "Rover"
    vt_type_id: Optional[int] = None
    vt_type_desc: Optional[str] = None  # "Tailsitter", "Tiltrotor", "Standard VTOL (Quadplane)"
    weight_kg: float = 2.0
    wing_span_m: Optional[float] = None
    ca_airframe: Optional[int] = None
    rotor_count: Optional[int] = None
    hardware: str = "Unknown"
    firmware: str = "Unknown"
    rotor_positions: List[Dict[str, float]] = field(default_factory=list)
    raw_params: Dict[str, Any] = field(default_factory=dict)

    def get_vt_type_description(self) -> str:
        if self.vt_type_desc:
            return self.vt_type_desc
        if self.vt_type_id is not None:
            mapping = {
                0: "Tailsitter VTOL",
                1: "Tiltrotor VTOL",
                2: "Standard VTOL (Quadplane)"
            }
            return mapping.get(self.vt_type_id, "Unknown VTOL Type")
        return "Not a VTOL"

def build_profile_from_log(report: Dict[str, Any]) -> VehicleProfile:
    """Constructs a VehicleProfile from parsed log report containing pid_parameters and summary."""
    params = report.get("pid_parameters", {})
    summary = report.get("summary", {})
    
    is_vtol = summary.get("is_vtol", False)
    vehicle_type_code = summary.get("vehicle_type", 0) # 0: Unknown, 1: Multirotor, 2: Fixed Wing, 3: VTOL, etc.
    
    # Map vehicle type code to human-readable string
    vtype_mapping = {
        1: "Multirotor",
        2: "Fixed Wing",
        3: "VTOL",
        4: "Rover"
    }
    vehicle_type = vtype_mapping.get(vehicle_type_code, "Multirotor" if is_vtol else "Unknown")
    if is_vtol and vehicle_type != "VTOL":
        vehicle_type = "VTOL"

    # Extract weight
    weight = params.get("WEIGHT_BASE") or params.get("WEIGHT_GROSS")
    if weight is None:
        weight = 23.50 if is_vtol else 2.0
    
    wing_span = params.get("FW_WING_SPAN")
    ca_airframe = params.get("CA_AIRFRAME")
    
    # Rotor Count
    rotor_count = params.get("CA_ROTOR_COUNT")
    if rotor_count is not None:
        rotor_count = int(rotor_count)
    elif is_vtol:
        # standard Quadplane has 4 lift rotors + 1 pusher (often CA_ROTOR_COUNT doesn't count the pusher, or does)
        rotor_count = 4
        
    # VTOL Type
    vt_type_id = params.get("VT_TYPE")
    if vt_type_id is not None:
        vt_type_id = int(vt_type_id)
        
    # Extract rotor positions if available
    rotor_positions = []
    if rotor_count:
        for i in range(rotor_count):
            px = params.get(f"CA_ROTOR{i}_PX")
            py = params.get(f"CA_ROTOR{i}_PY")
            pz = params.get(f"CA_ROTOR{i}_PZ")
            if px is not None or py is not None or pz is not None:
                rotor_positions.append({
                    "index": i,
                    "x": float(px or 0.0),
                    "y": float(py or 0.0),
                    "z": float(pz or 0.0)
                })

    return VehicleProfile(
        is_vtol=is_vtol,
        vehicle_type=vehicle_type,
        vt_type_id=vt_type_id,
        weight_kg=float(weight),
        wing_span_m=float(wing_span) if wing_span is not None else None,
        ca_airframe=int(ca_airframe) if ca_airframe is not None else None,
        rotor_count=rotor_count,
        hardware=summary.get("hardware", "Unknown"),
        firmware=summary.get("firmware", "Unknown"),
        rotor_positions=rotor_positions,
        raw_params=params
    )

def generate_search_queries(profile: VehicleProfile) -> List[str]:
    """Generates optimal Google search queries based on the vehicle specs."""
    queries = []
    
    # Type description
    if profile.is_vtol:
        type_desc = profile.get_vt_type_description()
    else:
        type_desc = profile.vehicle_type

    # Query 1: Similar vehicle PID tuning / configuration
    q1 = f"PX4 {type_desc} PID tuning "
    if profile.weight_kg:
        q1 += f"{profile.weight_kg}kg "
    if profile.rotor_count:
        q1 += f"{profile.rotor_count} rotors"
    queries.append(q1.strip())
    
    # Query 2: Specific VTOL / Multi-rotor configuration issues
    if profile.is_vtol:
        queries.append(f"PX4 VTOL transition yaw instability {profile.get_vt_type_description()}")
    else:
        queries.append(f"PX4 {profile.vehicle_type} attitude tracking latency controller saturation")
        
    # Query 3: Vibration isolation/damping for this weight class
    if profile.weight_kg > 10.0:
        queries.append(f"heavy UAV {profile.weight_kg}kg vibration damping IMU notch filter PX4")
    else:
        queries.append(f"UAV structural resonance high vibration frequencies PX4")
        
    return queries

def format_vehicle_context(profile: VehicleProfile) -> str:
    """Formats the vehicle profile into a clean Markdown table/bullet-points block for LLM prompts."""
    lines = []
    lines.append("### ARAÇ PROFİLİ (VİDEO/LOG VERİLERİNDEN DİNAMİK ELDE EDİLEN)")
    lines.append(f"- **Tip**: {profile.vehicle_type}" + (f" ({profile.get_vt_type_description()})" if profile.is_vtol else ""))
    lines.append(f"- **Ağırlık**: {profile.weight_kg:.2f} kg")
    
    if profile.wing_span_m:
        lines.append(f"- **Kanat Açıklığı**: {profile.wing_span_m:.2f} m")
    if profile.rotor_count:
        lines.append(f"- **Rotor Sayısı**: {profile.rotor_count}")
    if profile.ca_airframe:
        lines.append(f"- **Control Allocation Havadaki Gövde Sınıfı (CA_AIRFRAME)**: {profile.ca_airframe}")
        
    lines.append(f"- **Otopilot Donanımı**: {profile.hardware}")
    lines.append(f"- **Yazılım Sürümü**: {profile.firmware}")

    if profile.rotor_positions:
        lines.append("\n**Rotor Pozisyonları (Control Allocation):**")
        lines.append("| Motor # | X (Ön/Arka) | Y (Sağ/Sol) | Z (Yukarı/Aşağı) |")
        lines.append("|---|---|---|---|")
        for pos in profile.rotor_positions:
            lines.append(f"| Motor {pos['index']} | {pos['x']:.3f} | {pos['y']:.3f} | {pos['z']:.3f} |")
            
    return "\n".join(lines)


def extract_anomalies_for_search(report: Dict[str, Any]) -> List[str]:
    """Identify key anomalies in the log report to focus search queries."""
    anomalies = []
    
    # 1. Vibration anomalies
    vib = report.get("vibration", {})
    for axis in ["x", "y", "z"]:
        axis_data = vib.get(f"accel_{axis}", {})
        rms = axis_data.get("rms_m_s2", 0.0)
        peak = axis_data.get("peak_m_s2", 0.0)
        if rms > 15.0:
            anomalies.append(f"Critical {axis.upper()}-axis IMU vibration RMS {rms:.2f} m/s²")
        elif rms > 8.0:
            anomalies.append(f"High {axis.upper()}-axis IMU vibration RMS {rms:.2f} m/s²")
        if peak > 50.0:
            anomalies.append(f"IMU accel peak {peak:.2f} m/s² on {axis.upper()}-axis")

    # 2. Tracking anomalies
    att = report.get("attitude_tracking", {})
    for axis in ["roll", "pitch", "yaw"]:
        axis_data = att.get(axis, {})
        rmse = axis_data.get("rmse_deg")
        if rmse is not None and rmse > (3.5 if axis == "yaw" else 2.2):
            anomalies.append(f"High {axis} tracking RMSE {rmse:.2f} degrees")
            
    # 3. Failsafe or message errors
    failsafe = report.get("failsafe_events", {})
    if failsafe and failsafe.get("failsafe_active_count", 0) > 0:
        anomalies.append("Failsafe event triggered during flight")
        
    logged_msg = failsafe.get("logged_messages", [])
    for msg in logged_msg:
        msg_text = msg.get("message", "").lower()
        if "compass" in msg_text or "heading" in msg_text or "mag" in msg_text:
            if "heading estimate not stable" in msg_text or "compass inconsistent" in msg_text:
                anomalies.append("Compass magnetic interference and heading instability")
                break

    # Default if none found
    if not anomalies:
        anomalies.append("Actuator control latency and loop performance")
        
    return anomalies


if __name__ == "__main__":
    # Small test
    dummy_report = {
        "summary": {
            "is_vtol": True,
            "vehicle_type": 3,
            "hardware": "Cube Orange+",
            "firmware": "PX4 1.14.0"
        },
        "pid_parameters": {
            "WEIGHT_BASE": 24.5,
            "FW_WING_SPAN": 3.2,
            "CA_AIRFRAME": 2,
            "CA_ROTOR_COUNT": 4,
            "VT_TYPE": 2,
            "CA_ROTOR0_PX": 0.5,
            "CA_ROTOR0_PY": 0.5,
            "CA_ROTOR0_PZ": -0.1
        },
        "vibration": {
            "accel_z": {
                "rms_m_s2": 11.2,
                "peak_m_s2": 42.1
            }
        }
    }
    p = build_profile_from_log(dummy_report)
    print(format_vehicle_context(p))
    print("Queries:", generate_search_queries(p))
    print("Anomalies:", extract_anomalies_for_search(dummy_report))
