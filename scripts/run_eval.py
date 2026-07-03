import os
import sys
import json
import asyncio
from datetime import datetime
from backend.council import run_uav_council
from backend.log_parser import generate_text_report

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

GROUND_TRUTH_PATH = "data/alfa_dataset/ground_truth.json"
CACHE_DIR = "data/log_cache"
EVAL_MD_PATH = "data/alfa_dataset/evaluation_report.md"
EVAL_JSON_PATH = "data/alfa_dataset/evaluation_results.json"

async def run_evaluation():
    print("=== UAV Council ALFA Dataset Evaluation Pipeline ===")
    
    # 1. Load ground truth
    if not os.path.exists(GROUND_TRUTH_PATH):
        print(f"Error: Ground truth file not found at {GROUND_TRUTH_PATH}")
        sys.exit(1)
        
    with open(GROUND_TRUTH_PATH, "r") as f:
        ground_truth = json.load(f)
        
    # Get ALFA logs present in cache
    alfa_logs = [f for f in os.listdir(CACHE_DIR) if f.startswith("flight_") and f.endswith(".json")]
    if not alfa_logs:
        print(f"Error: No converted ALFA log reports found in {CACHE_DIR}")
        sys.exit(1)
        
    print(f"Found {len(alfa_logs)} flight logs to evaluate.")
    
    results = {}
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0
    total_latency = 0.0
    latency_count = 0
    
    for log_file in sorted(alfa_logs):
        log_id = log_file.replace(".json", "")
        gt = ground_truth.get(log_id)
        if not gt:
            print(f"Warning: Log '{log_id}' not found in ground truth config, skipping.")
            continue
            
        print(f"\nEvaluating {log_id}...")
        
        # Load cache data
        with open(os.path.join(CACHE_DIR, log_file), "r") as f:
            log_data = json.load(f)
            
        text_report = generate_text_report(log_data)
        persona_dataset = log_data.get("persona_dataset")
        
        # Run through council
        print(f"Sending {log_id} to Council stages...")
        try:
            council_out = await run_uav_council(
                log_report=text_report,
                user_query="Detaylı anomalileri tespit et ve kritik düzeltici parametre reçetelerini çıkar.",
                model=None,
                persona_dataset=persona_dataset,
                report_dict=log_data
            )
        except Exception as e:
            print(f"Error running council on {log_id}: {e}")
            continue
            
        stage3 = council_out.get("stage3", {})
        recipes = stage3.get("recipes", [])
        
        print(f"Council finished. Extracted {len(recipes)} recipes.")
        
        # Ground Truth check
        expected_param = gt.get("fault_param")
        expected_type = gt.get("fault_type")
        expected_time = gt.get("fault_time")
        
        # We check if the council recommended the expected parameter change as safety_critical
        matched_recipe = None
        for r in recipes:
            param = r.get("parametre", "")
            if expected_param and param.upper() == expected_param.upper():
                matched_recipe = r
                break
                
        # Metrics update
        status = "NORMAL"
        detected = False
        latency = None
        
        if expected_type == "belirsiz":
            status = "BELİRSİZ (YORUM DIŞI)"
            # Skip metrics calculation
        elif expected_type == "none":
            # Normal flight: should have NO safety_critical parameters triggered by the fault
            has_sc = any(r.get("safety_critical") for r in recipes)
            if has_sc:
                false_positives += 1
                status = "FALSE_POSITIVE (Normal uçuşta gereksiz kritik alarm verildi)"
            else:
                true_negatives += 1
                status = "TRUE_NEGATIVE (Normal uçuş başarıyla geçti)"
        else:
            # Anomalous flight: must recommend the expected parameter change as safety_critical
            if matched_recipe and matched_recipe.get("safety_critical"):
                true_positives += 1
                detected = True
                status = "TRUE_POSITIVE (Hata başarıyla tespit edildi)"
                
                # Calculate latency (t_detect - t_fault)
                detect_time = matched_recipe.get("kanit_zaman_damgasi", 0.0)
                if expected_time is not None:
                    latency = max(0.0, float(detect_time) - float(expected_time))
                    total_latency += latency
                    latency_count += 1
            else:
                false_negatives += 1
                status = "FALSE_NEGATIVE (Kritik hata gözden kaçırıldı)"
                
        results[log_id] = {
            "ground_truth": gt,
            "status": status,
            "detected": detected,
            "latency_s": latency,
            "recipes_count": len(recipes),
            "safety_critical_count": len([r for r in recipes if r.get("safety_critical")]),
            "recipes": recipes
        }
        
        print(f"Result for {log_id}: {status} (Latency: {latency}s)")
        
    # Calculate accuracy metrics
    total_cases = true_positives + false_positives + false_negatives + true_negatives
    accuracy = (true_positives + true_negatives) / total_cases if total_cases > 0 else 0.0
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    avg_latency = total_latency / latency_count if latency_count > 0 else 0.0
    
    # Save JSON results
    eval_summary = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_cases": total_cases,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "true_negatives": true_negatives,
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "average_latency_seconds": round(avg_latency, 2)
        },
        "results": results
    }
    
    with open(EVAL_JSON_PATH, "w") as f:
        json.dump(eval_summary, f, indent=2)
        
    # Save MD report
    report_lines = [
        "# ALFA Dataset Evaluation Report",
        "",
        f"**Değerlendirme Tarihi:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## ÖZET PERFORMANS METRİKLERİ",
        "",
        "| Metrik | Değer | Açıklama |",
        "|---|---|---|",
        f"| **Doğrulak (Accuracy)** | `{accuracy:.2%}` | Başarılı sınıflandırma oranı |",
        f"| **Hassasiyet (Precision)** | `{precision:.2%}` | Doğru alarm verme oranı |",
        f"| **Duyarlılık (Recall)** | `{recall:.2%}` | Hataları yakalama oranı |",
        f"| **Ortalama Tespit Gecikmesi (Avg Latency)** | `{avg_latency:.2f}s` | Hata anı ile kanıt zamanı arasındaki fark |",
        f"| **Toplam Test Senaryosu** | `{total_cases}` | Değerlendirilen uçuş sayısı |",
        "",
        "## HATA MATRİSİ (CONFUSION MATRIX)",
        "",
        "| | Gerçek Hata (Anomalous) | Gerçek Normal (Normal) |",
        "|---|---|---|",
        f"| **Tespit Edildi (Alarm)** | TP: `{true_positives}` | FP: `{false_positives}` |",
        f"| **Tespit Edilmedi (No Alarm)** | FN: `{false_negatives}` | TN: `{true_negatives}` |",
        "",
        "## UÇUŞ BAZLI DEĞERLENDİRME DETAYLARI",
        ""
    ]
    
    for log_id, res in results.items():
        gt = res["ground_truth"]
        report_lines.append(f"### Uçuş: `{log_id}`")
        report_lines.append(f"- **Gerçek Durum:** `{gt.get('fault_type')}` (Parametre: `{gt.get('fault_param')}`)")
        report_lines.append(f"- **Council Kararı:** `{res['status']}`")
        report_lines.append(f"- **Toplam Reçete Sayısı:** `{res['recipes_count']}` (Kritik: `{res['safety_critical_count']}`)")
        if res['latency_s'] is not None:
            report_lines.append(f"- **Tespit Gecikmesi:** `{res['latency_s']:.2f}s`")
            
        report_lines.append("\n**Önerilen Reçeteler:**")
        if not res["recipes"]:
            report_lines.append("*Hiçbir reçete üretilmedi.*")
        else:
            report_lines.append("| Reçete ID | Parametre | Mevcut | Önerilen | Kritik | Güven |")
            report_lines.append("|---|---|---|---|---|---|")
            for r in res["recipes"]:
                mevcut = r.get("mevcut_deger")
                mevcut_str = f"{mevcut}" if mevcut is not None else "N/A"
                report_lines.append(
                    f"| `{r.get('recete_id')}` | `{r.get('parametre')}` | `{mevcut_str}` | `{r.get('onerilen_deger')}` | "
                    f"{'Evet ⚠️' if r.get('safety_critical') else 'Hayır'} | {r.get('guven_seviyesi')} |"
                )
        report_lines.append("\n" + "-"*40 + "\n")
        
    with open(EVAL_MD_PATH, "w") as f:
        f.write("\n".join(report_lines))
        
    print(f"\n[Evaluation] Raporlar kaydedildi:")
    print(f"  Markdown: {EVAL_MD_PATH}")
    print(f"  JSON: {EVAL_JSON_PATH}")
    print("=== Evaluation Pipeline Completed ===")

if __name__ == "__main__":
    asyncio.run(run_evaluation())
