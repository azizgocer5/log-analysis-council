import os
import json
from typing import List, Dict, Any, Tuple, Optional

# Use an absolute path so the config file is found regardless of cwd
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
SAFETY_CRITICAL_FILE = os.path.join(_MODULE_DIR, "..", "config", "safety_critical_params.json")
DEFAULT_SAFETY_CRITICAL = ["BAT1_V_DIV", "SYS_HAS_MAG", "COM_LOW_BAT_ACT", "BAT_CRIT_THR", "BAT_EMERGEN_THR"]

def load_safety_critical_params() -> List[str]:
    """Load parameter names from safety critical params config file."""
    if os.path.exists(SAFETY_CRITICAL_FILE):
        try:
            with open(SAFETY_CRITICAL_FILE, "r") as f:
                params = json.load(f)
                if isinstance(params, list):
                    return [str(p).upper() for p in params]
        except Exception as e:
            print(f"[Validator] Error reading safety critical file: {e}")
    return DEFAULT_SAFETY_CRITICAL


def lookup_value(report: Dict[str, Any], name: str) -> Tuple[Optional[float], bool]:
    """Look up a parameter or metric value in the log report.
    Returns (value, found).
    """
    name_upper = name.upper()
    
    # 1. Search in pid_parameters
    pid_params = report.get("pid_parameters", {})
    if name_upper in pid_params:
        val = pid_params[name_upper]
        if val is not None:
            return float(val), True
        return None, True
        
    # 2. Search in battery
    battery = report.get("battery", {})
    if "voltage" in battery and isinstance(battery["voltage"], dict):
        if name_upper in ["VOLTAGE", "BATTERY_VOLTAGE", "BAT_V"]:
            return float(battery["voltage"].get("mean", 0.0)), True
    if "current" in battery and isinstance(battery["current"], dict):
        if name_upper in ["CURRENT", "BATTERY_CURRENT", "BAT_I"]:
            return float(battery["current"].get("mean", 0.0)), True
            
    # 3. Search in vibration
    vibration = report.get("vibration", {})
    for axis in ["x", "y", "z"]:
        key = f"accel_{axis}"
        if key in vibration:
            if name_upper in [f"ACCEL_{axis.upper()}", f"VIBRATION_{axis.upper()}"]:
                return float(vibration[key].get("rms_m_s2", 0.0)), True

    # 4. Search in EKF
    ekf = report.get("ekf", {})
    for label in ["GPS Horizontal Velocity", "GPS Vertical Velocity", "GPS Horizontal Position", "GPS Vertical Position"]:
        if label in ekf:
            if name_upper.replace("_", " ") in [label.upper(), f"EKF {label.upper()}"]:
                return float(ekf[label].get("mean_ratio", 0.0)), True

    # 5. Recursive check for general match
    def recursive_find(d: Any, target: str) -> Tuple[Optional[float], bool]:
        if isinstance(d, dict):
            for k, v in d.items():
                if k.upper() == target:
                    if isinstance(v, (int, float)):
                        return float(v), True
                    if isinstance(v, dict) and "mean" in v:
                        return float(v["mean"]), True
                    if isinstance(v, dict) and "rms_m_s2" in v:
                        return float(v["rms_m_s2"]), True
                res, found = recursive_find(v, target)
                if found:
                    return res, found
        elif isinstance(d, list):
            for item in d:
                res, found = recursive_find(item, target)
                if found:
                    return res, found
        return None, False

    return recursive_find(report, name_upper)


def is_topic_in_log(report: Dict[str, Any], topic: str) -> bool:
    """Check if the given topic is present and contains valid data in the log report."""
    if not topic or topic == "N/A":
        return True # Skip checking if not specified
        
    t_lower = topic.lower()
    
    # Mapping common topic names to report sections
    if "battery" in t_lower:
        return "voltage" in report.get("battery", {}) or "error" not in report.get("battery", {})
    if "attitude" in t_lower or "rate" in t_lower or "velocity" in t_lower:
        return "roll" in report.get("attitude_tracking", {}) or "error" not in report.get("attitude_tracking", {})
    if "vibration" in t_lower or "sensor_combined" in t_lower or "accel" in t_lower or "gyro" in t_lower:
        return len(report.get("vibration", {})) > 0
    if "ekf" in t_lower or "innovation" in t_lower or "estimator" in t_lower:
        return len(report.get("ekf", {})) > 0
    if "actuator" in t_lower or "motor" in t_lower:
        return len(report.get("actuators", {})) > 0
    if "failsafe" in t_lower or "message" in t_lower or "timeline" in t_lower:
        return len(report.get("failsafe_events", {})) > 0
        
    # Fallback: check if topic name is mentioned in the report JSON
    try:
        report_str = json.dumps(report).lower()
        return t_lower in report_str
    except Exception:
        return True
        

def validate_recipe(recipe: Dict[str, Any], report: Dict[str, Any], safety_critical_list: List[str]) -> Dict[str, Any]:
    """Validate a single recipe against the actual log data."""
    # Ensure keys exist
    recipe["dogrulanamadi"] = False
    recipe["zayif_kanit"] = False
    
    param = recipe.get("parametre", "")
    mevcut = recipe.get("mevcut_deger")
    topic = recipe.get("kanit_topic", "")
    
    # 1. Update safety critical flag if the parameter is in the safety critical list
    if param and param.upper() in safety_critical_list:
        recipe["safety_critical"] = True
        
    # 2. Check if topic is present in log
    topic_ok = is_topic_in_log(report, topic)
    if not topic_ok:
        recipe["dogrulanamadi"] = True
        recipe["zayif_kanit"] = True
        recipe["validation_error"] = f"Kanıt topici '{topic}' logda bulunamadı."
        return recipe
        
    # 3. Check parameter value
    val, found = lookup_value(report, param)
    if not found:
        # If the parameter is not found but LLM said mevcut_deger is null/None, we allow it (could be mechanical check or unlogged param)
        if mevcut is not None:
            recipe["dogrulanamadi"] = True
            recipe["zayif_kanit"] = True
            recipe["validation_error"] = f"Parametre/metrik '{param}' log verilerinde bulunamadı."
        return recipe
        
    # Check matching with tolerance payı
    if mevcut is not None:
        try:
            m_val = float(mevcut)
            # Define tolerance (e.g. 5% tolerance or absolute 0.01, whichever is larger)
            tolerance = max(0.01, 0.05 * abs(val))
            if abs(m_val - val) > tolerance:
                recipe["dogrulanamadi"] = True
                recipe["zayif_kanit"] = True
                recipe["validation_error"] = f"Mevcut değer '{m_val}' logdaki değer olan '{val}' ile eşleşmiyor (tolerans payı: {tolerance:.4f})."
        except (ValueError, TypeError):
            recipe["dogrulanamadi"] = True
            recipe["zayif_kanit"] = True
            recipe["validation_error"] = f"Mevcut değer '{mevcut}' sayısal değere dönüştürülemedi."
            
    return recipe
