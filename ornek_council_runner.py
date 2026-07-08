
"""UAV Log Analysis Council — CLI runner (standalone bağımsız script).

Usage:
    python ornek_council_runner.py path/to/flight.ulg

Flow:
    1. Parse the .ulg file ONCE (ornek_log_extractor.build_flight_dataset)
    2. For each of the 3 personas: system prompt (backend/personas.py) + a
       grounded data block (ornek_log_extractor.format_context_block) -> API call
    3. Feed all 3 outputs to the chairman persona for synthesis
    4. Save the final report as markdown

Requires: ANTHROPIC_API_KEY environment variable.
"""

from __future__ import annotations

import os
import sys
import datetime
from typing import Dict

import anthropic

# Add project root to path so backend.* imports work when running from root dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.personas import get_all_personas, get_chairman
from ornek_log_extractor import build_flight_dataset, format_context_block

# Update this to whichever Claude model your account has access to.
MODEL_NAME = "claude-opus-4-1"
MAX_TOKENS = 4000


def run_persona(client: anthropic.Anthropic, persona_id: str, persona: Dict, data_block: str) -> str:
    print(f"  -> {persona['name']} ({persona_id}) çalışıyor...")
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        system=persona["system_prompt"],
        messages=[{
            "role": "user",
            "content": f"{data_block}\n\nBu log'u kendi uzmanlık alanın açısından analiz et ve "
                       f"reçete formatında bulgularını sun."
        }],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def run_chairman(client: anthropic.Anthropic, expert_reports: Dict[str, str]) -> str:
    chairman = get_chairman()
    personas = get_all_personas()
    combined = "\n\n".join(
        f"---\n## {personas[pid]['name']} ({personas[pid]['title']}) Raporu\n{report}"
        for pid, report in expert_reports.items()
        if pid in personas
    )
    print(f"  -> {chairman['name']} sentezliyor...")
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        system=chairman["system_prompt"],
        messages=[{
            "role": "user",
            "content": f"Aşağıda council üyelerinin bireysel raporları var. Bunları sentezleyip "
                       f"nihai rapor formatında bir çıktı üret:\n\n{combined}"
        }],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def main():
    if len(sys.argv) != 2:
        print("Kullanım: python ornek_council_runner.py <flight.ulg>")
        sys.exit(1)

    ulog_path = sys.argv[1]
    if not os.path.exists(ulog_path):
        print(f"Dosya bulunamadı: {ulog_path}")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY ortam değişkeni ayarlanmamış.")
        sys.exit(1)

    client = anthropic.Anthropic()

    print(f"[1/3] Log parse ediliyor: {ulog_path}")
    dataset = build_flight_dataset(ulog_path)

    print("Persona dataset anahtarları:", list(dataset.keys()))

    print("\n[2/3] Uzmanlar analiz yapıyor...")
    personas = get_all_personas()  # Returns 3 personas: pid_tuning_expert, hardware_diagnostics_expert, sensor_safety_expert
    expert_reports: Dict[str, str] = {}
    for persona_id, persona in personas.items():
        data_block = format_context_block(persona_id, dataset)
        expert_reports[persona_id] = run_persona(client, persona_id, persona, data_block)

    print("\n[3/3] Chairman sentez yapıyor...")
    final_report = run_chairman(client, expert_reports)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(os.path.expanduser("~/Downloads"), f"council_report_{timestamp}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# UAV Log Council Raporu\n\nLog: `{ulog_path}`\nTarih: {timestamp}\n\n")
        f.write(final_report)
        f.write("\n\n---\n\n# Uzman Raporları (Detay)\n\n")
        for persona_id, report in expert_reports.items():
            if persona_id in personas:
                f.write(f"\n## {personas[persona_id]['name']}\n\n{report}\n")

    print(f"\nRapor kaydedildi: {out_path}")


if __name__ == "__main__":
    main()