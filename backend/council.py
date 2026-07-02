"""3-stage UAV Log Analysis LLM Council orchestration.

Stage 1: Each persona analyzes the flight log from their expertise
Stage 2: Cross-evaluation of each other's analyses
Stage 3: Chairman synthesizes final prioritized prescription list
"""

from typing import List, Dict, Any, Tuple, Optional
import asyncio

from .openrouter import query_model
from .config import COUNCIL_MODEL, CHAIRMAN_MODEL
from .personas import PERSONAS, CHAIRMAN_PERSONA, get_persona_names


async def _query_persona(
    persona_id: str,
    user_message: str,
    system_prompt: str,
    model: str = COUNCIL_MODEL,
) -> Dict[str, Any]:
    """Query a single persona with system prompt and user message."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = await query_model(model, messages, timeout=180.0)

    if response is None:
        return {
            "persona_id": persona_id,
            "response": "⚠️ Bu uzman yanıt veremedi. Lütfen tekrar deneyin.",
            "error": True,
        }

    return {
        "persona_id": persona_id,
        "response": response.get("content", ""),
        "error": False,
    }


# ---------------------------------------------------------------------------
# Stage 1: Individual Expert Analyses
# ---------------------------------------------------------------------------

async def stage1_expert_analyses(
    log_report: str,
    user_query: Optional[str] = None,
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Stage 1: Each persona analyzes the flight log independently.

    Args:
        log_report: Structured text report from log_parser
        user_query: Optional user question to focus the analysis
        model: Model identifier override

    Returns:
        List of dicts with persona_id, persona info, and response
    """
    active_model = model or COUNCIL_MODEL
    is_local = (active_model == "qwen3:8b")
    stagger_delay = 0.2 if is_local else 5.5

    # Build the user message
    if user_query:
        user_message = f"""Aşağıda bir VTOL drone uçuş logundaki analiz verilerini bulacaksın.

Kullanıcının sorusu: {user_query}

Bu soruyu kendi uzmanlık alanın çerçevesinde yanıtla. Analiz verilerini kullanarak somut, veri destekli cevaplar ve reçeteler sun.

--- UÇUŞ LOG VERİLERİ ---
{log_report}
"""
    else:
        user_message = f"""Aşağıda bir VTOL drone uçuş logundaki analiz verilerini bulacaksın.

Bu verileri kendi uzmanlık alanın çerçevesinde analiz et. Bulgularını ve reçetelerini sun.

--- UÇUŞ LOG VERİLERİ ---
{log_report}
"""

    # Query all personas sequentially with stagger delay to prevent 429 rate limits
    responses = []
    persona_ids = get_persona_names()
    for i, pid in enumerate(persona_ids):
        if i > 0:
            print(f"Staggering Stage 1 expert query for {pid}...")
            await asyncio.sleep(stagger_delay)
        persona = PERSONAS[pid]
        resp = await _query_persona(pid, user_message, persona["system_prompt"], active_model)
        responses.append(resp)

    # Enrich with persona info
    results = []
    for resp in responses:
        pid = resp["persona_id"]
        persona = PERSONAS[pid]
        results.append({
            "persona_id": pid,
            "persona_name": persona["name"],
            "persona_title": persona["title"],
            "persona_icon": persona["icon"],
            "persona_color": persona["color"],
            "response": resp["response"],
            "error": resp.get("error", False),
        })

    return results


# ---------------------------------------------------------------------------
# Stage 2: Cross-Evaluation
# ---------------------------------------------------------------------------

async def stage2_cross_evaluation(
    log_report: str,
    stage1_results: List[Dict[str, Any]],
    user_query: Optional[str] = None,
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Stage 2: Each persona evaluates the others' analyses.

    Args:
        log_report: Original log report for reference
        stage1_results: Results from Stage 1
        user_query: Optional original user query
        model: Model identifier override

    Returns:
        List of cross-evaluation results
    """
    active_model = model or COUNCIL_MODEL
    is_local = (active_model == "qwen3:8b")
    stagger_delay = 0.2 if is_local else 5.5

    # Build the compiled analyses text
    analyses_text = "\n\n".join([
        f"### {r['persona_icon']} {r['persona_name']} ({r['persona_title']}):\n{r['response']}"
        for r in stage1_results
        if not r.get("error")
    ])

    eval_prompt_template = """Aşağıda 5 uzmanın bir VTOL drone uçuş loguna dair analizlerini bulacaksın.
{query_section}
Her uzmanın analizini kendi uzmanlık alanın perspektifinden değerlendir:

1. **Katıldığın noktalar:** Hangi bulgulara ve reçetelere katılıyorsun? Neden?
2. **Katılmadığın noktalar:** Hangi önerilerden endişelisin? Neden?
3. **Eksik gördüğün noktalar:** Diğer uzmanlar neleri kaçırmış?
4. **Reçete güvenlik değerlendirmesi:** Önerilen parametre değişiklikleri güvenli mi?
5. **Önceliklendirme:** Hangi reçeteler önce uygulanmalı?

--- UZMAN ANALİZLERİ ---
{analyses}

--- REFERANS: UÇUŞ LOG VERİLERİ (ÖZET) ---
{log_summary}
"""

    query_section = f"\nKullanıcının orijinal sorusu: {user_query}\n" if user_query else ""

    # Shorten log report for stage 2 (use first 2000 chars as summary)
    log_summary = log_report[:3000] + "\n... [devamı kısaltıldı]" if len(log_report) > 3000 else log_report

    responses = []
    persona_ids = get_persona_names()
    for i, pid in enumerate(persona_ids):
        if i > 0:
            print(f"Staggering Stage 2 expert query for {pid}...")
            await asyncio.sleep(stagger_delay)
        persona = PERSONAS[pid]
        user_message = eval_prompt_template.format(
            query_section=query_section,
            analyses=analyses_text,
            log_summary=log_summary,
        )
        resp = await _query_persona(pid, user_message, persona["system_prompt"], active_model)
        responses.append(resp)

    results = []
    for resp in responses:
        pid = resp["persona_id"]
        persona = PERSONAS[pid]
        results.append({
            "persona_id": pid,
            "persona_name": persona["name"],
            "persona_title": persona["title"],
            "persona_icon": persona["icon"],
            "persona_color": persona["color"],
            "evaluation": resp["response"],
            "error": resp.get("error", False),
        })

    return results


# ---------------------------------------------------------------------------
# Stage 3: Chairman Synthesis
# ---------------------------------------------------------------------------

async def stage3_chairman_synthesis(
    log_report: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    user_query: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes all analyses into final prescription.

    Args:
        log_report: Original log report
        stage1_results: Individual expert analyses
        stage2_results: Cross-evaluations
        user_query: Optional original user query
        model: Model identifier override

    Returns:
        Chairman's final synthesis
    """
    active_model = model or CHAIRMAN_MODEL

    # Build Stage 1 summary
    stage1_text = "\n\n".join([
        f"### {r['persona_icon']} {r['persona_name']} ({r['persona_title']}):\n{r['response']}"
        for r in stage1_results
        if not r.get("error")
    ])

    # Build Stage 2 summary
    stage2_text = "\n\n".join([
        f"### {r['persona_icon']} {r['persona_name']} Değerlendirmesi:\n{r['evaluation']}"
        for r in stage2_results
        if not r.get("error")
    ])

    chairman_prompt = f"""Sen UAV Log Analysis Council'ın Baş Mühendisisin. 5 uzman bir VTOL drone'un uçuş loglarını analiz etti ve birbirlerinin analizlerini değerlendirdi.

{f"Kullanıcının orijinal sorusu: {user_query}" if user_query else "Görev: Kapsamlı uçuş logu analizi ve PID tuning reçetesi"}

Tüm verileri sentezleyerek nihai raporunu oluştur. Formatına uy.

--- AŞAMA 1: UZMAN ANALİZLERİ ---
{stage1_text}

--- AŞAMA 2: ÇAPRAZ DEĞERLENDİRMELER ---
{stage2_text}

--- UÇUŞ LOG VERİLERİ ---
{log_report[:4000]}
"""

    messages = [
        {"role": "system", "content": CHAIRMAN_PERSONA["system_prompt"]},
        {"role": "user", "content": chairman_prompt},
    ]

    response = await query_model(active_model, messages, timeout=240.0)

    if response is None:
        return {
            "persona_name": CHAIRMAN_PERSONA["name"],
            "persona_icon": CHAIRMAN_PERSONA["icon"],
            "response": "⚠️ Baş Mühendis sentez yapamadı. Lütfen tekrar deneyin.",
            "error": True,
        }

    return {
        "persona_name": CHAIRMAN_PERSONA["name"],
        "persona_title": CHAIRMAN_PERSONA["title"],
        "persona_icon": CHAIRMAN_PERSONA["icon"],
        "persona_color": CHAIRMAN_PERSONA["color"],
        "response": response.get("content", ""),
        "error": False,
    }


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------

async def run_uav_council(
    log_report: str,
    user_query: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the complete 3-stage UAV analysis council.

    Args:
        log_report: Structured text report from log parser
        user_query: Optional user question
        model: Optional model override

    Returns:
        Dict with stage1, stage2, stage3 results
    """
    # Stage 1
    stage1 = await stage1_expert_analyses(log_report, user_query, model)

    if not any(not r.get("error") for r in stage1):
        return {
            "stage1": stage1,
            "stage2": [],
            "stage3": {"error": True, "response": "Hiçbir uzman yanıt veremedi."},
        }

    # Stage 2
    stage2 = await stage2_cross_evaluation(log_report, stage1, user_query, model)

    # Stage 3
    stage3 = await stage3_chairman_synthesis(log_report, stage1, stage2, user_query, model)

    return {
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
    }


# ---------------------------------------------------------------------------
# Free-form question (single query to all personas)
# ---------------------------------------------------------------------------

async def ask_council_question(
    question: str,
    log_report: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ask a free-form question to the council.

    If log_report is provided, the question is contextualized with the log data.
    Otherwise, it's a general PX4/UAV question.
    """
    active_model = model or COUNCIL_MODEL

    # Stage 1: Get expert opinions
    if log_report:
        stage1 = await stage1_expert_analyses(log_report, question, active_model)
    else:
        # Without log data, just ask the question sequentially (using stagger or not depending on local)
        is_local = (active_model == "qwen3:8b")
        stagger_delay = 0.2 if is_local else 5.5

        stage1 = []
        persona_ids = get_persona_names()
        for i, pid in enumerate(persona_ids):
            if i > 0:
                await asyncio.sleep(stagger_delay)
            persona = PERSONAS[pid]
            resp = await _query_persona(pid, question, persona["system_prompt"], active_model)
            stage1.append({
                "persona_id": pid,
                "persona_name": persona["name"],
                "persona_title": persona["title"],
                "persona_icon": persona["icon"],
                "persona_color": persona["color"],
                "response": resp["response"],
                "error": resp.get("error", False),
            })

    # Stage 3: Chairman synthesis (skip Stage 2 for questions to save time/cost)
    stage3 = await stage3_chairman_synthesis(
        log_report or "Log verisi yüklenmedi.",
        stage1,
        [],  # No cross-evaluation for questions
        question,
        active_model,
    )

    return {
        "stage1": stage1,
        "stage2": [],
        "stage3": stage3,
    }


async def generate_conversation_title(user_query: str, model: Optional[str] = None) -> str:
    """Generate a short title for a conversation based on the first user message."""
    active_model = model or COUNCIL_MODEL
    title_prompt = """Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: """ + user_query + "\n\nTitle:"

    messages = [{"role": "user", "content": title_prompt}]

    response = await query_model(active_model, messages, timeout=30.0)

    if response is None:
        return "Yeni Analiz"

    title = response.get("content", "Yeni Analiz").strip().strip('"\'')
    if len(title) > 50:
        title = title[:47] + "..."

    return title
