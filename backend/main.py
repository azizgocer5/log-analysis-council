"""FastAPI backend for UAV Log Analysis LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
import uuid
import json
import asyncio
import traceback
import os

from . import storage
from .config import LOG_DIR
from .log_parser import discover_logs, parse_single_log, generate_text_report, generate_multi_log_comparison
from .log_cache import get_cached, set_cached, is_cached, get_cache_stats
from .council import (
    run_uav_council,
    stage1_expert_analyses,
    stage2_cross_evaluation,
    stage3_chairman_synthesis,
    ask_council_question,
    generate_conversation_title,
)
from .personas import get_persona_info_for_frontend, get_all_personas, get_chairman
from .web_search import search_similar_vehicles, search_academic_references
from .vehicle_profile import build_profile_from_log, extract_anomalies_for_search

app = FastAPI(title="UAV Log Analysis Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def enrich_report_with_wind(report: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures that the report contains wind/weather data.
    
    Wind data is NOT fabricated — if it's not measured in the log, the
    report will indicate 'data unavailable' so LLMs don't cite fake numbers.
    Only legacy demo log filenames get demo values for backward compatibility.
    """
    if "wind" not in report or not report["wind"]:
        filename = report.get("summary", {}).get("file", "").lower()
        filepath = report.get("filepath", "").lower()

        # Only provide demo wind data for the named example/demo log files
        if "flight_01_motor_failure" in filename or "flight_01_motor_failure" in filepath:
            report["wind"] = {
                "avg_wind_speed_m_s": 4.5,
                "max_wind_speed_m_s": 8.2,
                "wind_speed_status": "Orta Rüzgar (Demo verisi — gerçek ölçüm logda yok)",
                "is_estimated": True,
            }
        elif "flight_02_sensor_anomaly" in filename or "flight_02_sensor_anomaly" in filepath:
            report["wind"] = {
                "avg_wind_speed_m_s": 6.8,
                "max_wind_speed_m_s": 11.5,
                "wind_speed_status": "Kuvvetli Rüzgar (Demo verisi — gerçek ölçüm logda yok)",
                "is_estimated": True,
            }
        elif "flight_03_normal" in filename or "flight_03_normal" in filepath:
            report["wind"] = {
                "avg_wind_speed_m_s": 1.2,
                "max_wind_speed_m_s": 2.5,
                "wind_speed_status": "Hafif Rüzgar (Demo verisi — gerçek ölçüm logda yok)",
                "is_estimated": True,
            }
        else:
            # Real log: do NOT invent wind data
            report["wind"] = {
                "avg_wind_speed_m_s": None,
                "max_wind_speed_m_s": None,
                "wind_speed_status": "Hava durumu verisi bu logda ölçülmemiş — rüzgar etkisi bilinmiyor.",
                "is_estimated": False,
            }

        # Sync into persona_dataset genel dictionary if present
        if "persona_dataset" in report and "genel" in report["persona_dataset"]:
            report["persona_dataset"]["genel"]["wind"] = report["wind"]

    return report


async def perform_web_search_flow(reports: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """Helper to execute the web search phase and return both context and structured results."""
    web_search_context = ""
    web_search_data = {
        "answer_vehicles": "",
        "answer_academic": "",
        "sources": [],
        "queries": []
    }
    
    if not reports:
        return web_search_context, web_search_data
        
    try:
        profile = build_profile_from_log(reports[0])
        anomalies = extract_anomalies_for_search(reports[0])
        
        # Run search tasks sequentially with a stagger delay to stay under the 5 RPM free tier limits
        similar_vehicles_res = await search_similar_vehicles(reports[0].get("pid_parameters", {}))
        
        print("[Main] Staggering next search query to respect Gemini free-tier RPM limit...")
        await asyncio.sleep(12.5)
        
        academic_res = await search_academic_references(anomalies)
        
        # Check for exceptions
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or ""
        def _mask(msg: str) -> str:
            return msg.replace(api_key, "***REDACTED***") if api_key else msg
        if isinstance(similar_vehicles_res, Exception):
            print(f"[Main] Error in similar vehicles search: {_mask(str(similar_vehicles_res))}")
            similar_vehicles_res = {"answer": "Web arama sonucu alınamadı (hata). Fallback referans verileri kullanılıyor.", "sources": [], "queries": []}
        if isinstance(academic_res, Exception):
            print(f"[Main] Error in academic search: {_mask(str(academic_res))}")
            academic_res = {"answer": "Akademik arama sonucu alınamadı (hata). Fallback referans verileri kullanılıyor.", "sources": [], "queries": []}
            
        # Format web search context
        web_search_context = (
            f"### Benzer Araçların PID ve Ayar Analizleri (Google Search)\n"
            f"{similar_vehicles_res.get('answer', '')}\n\n"
            f"### Akademik ve Teorik Çözüm Referansları (Google Search)\n"
            f"{academic_res.get('answer', '')}\n"
        )
        
        # Combine sources and queries
        combined_sources = similar_vehicles_res.get("sources", []) + academic_res.get("sources", [])
        combined_queries = similar_vehicles_res.get("queries", []) + academic_res.get("queries", [])
        
        # De-duplicate sources by URL
        seen_urls = set()
        unique_sources = []
        for s in combined_sources:
            url = s.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(s)
                
        web_search_data = {
            "answer_vehicles": similar_vehicles_res.get("answer", ""),
            "answer_academic": academic_res.get("answer", ""),
            "sources": unique_sources,
            "queries": combined_queries
        }
    except Exception as e:
        print(f"[Main] Web search flow failed: {e}")
        traceback.print_exc()
        
    return web_search_context, web_search_data


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """Request to analyze one or more log files."""
    log_ids: List[str]
    user_query: Optional[str] = None
    model: Optional[str] = "qwen3:8b"


class AskQuestionRequest(BaseModel):
    """Request to ask a free-form question."""
    question: str
    log_ids: Optional[List[str]] = None
    model: Optional[str] = "qwen3:8b"


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    log_ids: Optional[List[str]] = None
    model: Optional[str] = "qwen3:8b"


# ---------------------------------------------------------------------------
# Health & Info Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "UAV Log Analysis Council API"}


@app.get("/api/personas")
async def list_personas():
    """Get all available council personas."""
    personas = get_persona_info_for_frontend()
    chairman = get_chairman()
    return {
        "personas": personas,
        "chairman": {
            "name": chairman["name"],
            "title": chairman["title"],
            "icon": chairman["icon"],
            "color": chairman["color"],
        },
    }


# ---------------------------------------------------------------------------
# Log Management Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/logs")
async def list_logs():
    """List all available ULog files."""
    logs = discover_logs(LOG_DIR)

    # Add cache status to each log
    for log in logs:
        log["cached"] = is_cached(log["path"])

    # Group by session
    sessions = {}
    for log in logs:
        session = log["session"]
        if session not in sessions:
            sessions[session] = []
        sessions[session].append(log)

    return {
        "logs": logs,
        "sessions": sessions,
        "total_count": len(logs),
        "log_dir": LOG_DIR,
    }


@app.get("/api/logs/{log_id}/summary")
async def get_log_summary(log_id: str):
    """Get a quick summary of a specific log file."""
    logs = discover_logs(LOG_DIR)
    log_entry = next((l for l in logs if l["id"] == log_id), None)

    if log_entry is None:
        raise HTTPException(status_code=404, detail=f"Log not found: {log_id}")

    # Check cache
    cached = get_cached(log_entry["path"])
    if cached:
        cached = enrich_report_with_wind(cached)
        return {
            "log": log_entry,
            "summary": cached.get("summary", {}),
            "pid_parameters": cached.get("pid_parameters", {}),
            "from_cache": True,
        }

    # Parse the log
    try:
        report = parse_single_log(log_entry["path"])
        report = enrich_report_with_wind(report)
        set_cached(log_entry["path"], report)
        return {
            "log": log_entry,
            "summary": report.get("summary", {}),
            "pid_parameters": report.get("pid_parameters", {}),
            "from_cache": False,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing log: {str(e)}")


@app.get("/api/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    return get_cache_stats()


# ---------------------------------------------------------------------------
# Analysis Endpoints (Streaming)
# ---------------------------------------------------------------------------

@app.post("/api/analyze/stream")
async def analyze_stream(request: AnalyzeRequest):
    """
    Analyze selected log files using the full council pipeline.
    Returns Server-Sent Events as each stage progresses.
    """
    # Resolve log paths
    all_logs = discover_logs(LOG_DIR)
    selected_logs = [l for l in all_logs if l["id"] in request.log_ids]

    if not selected_logs:
        raise HTTPException(status_code=404, detail="No valid logs found for the given IDs")

    async def event_generator():
        try:
            # Phase 1: Parse logs (with progress)
            yield _sse("parsing_start", {"total": len(selected_logs)})

            reports = []
            for i, log_entry in enumerate(selected_logs):
                yield _sse("parsing_progress", {
                    "current": i + 1,
                    "total": len(selected_logs),
                    "filename": log_entry["filename"],
                    "from_cache": is_cached(log_entry["path"]),
                })

                # Check cache
                cached = get_cached(log_entry["path"])
                if cached:
                    cached = enrich_report_with_wind(cached)

                if cached and "persona_dataset" in cached:
                    reports.append(cached)
                else:
                    try:
                        report = parse_single_log(log_entry["path"])
                        report = enrich_report_with_wind(report)
                        set_cached(log_entry["path"], report)
                        reports.append(report)
                    except Exception as e:
                        if cached:
                            reports.append(cached) # fallback
                        else:
                            yield _sse("parsing_error", {
                                "filename": log_entry["filename"],
                                "error": str(e),
                            })

            yield _sse("parsing_complete", {"parsed": len(reports)})

            if not reports:
                yield _sse("error", {"message": "No logs could be parsed"})
                return

            # Extract persona dataset if single log is analyzed
            persona_dataset = reports[0].get("persona_dataset") if len(reports) == 1 else None

            # Generate text report for LLM
            if len(reports) == 1:
                text_report = generate_text_report(reports[0])
            else:
                # Multi-log comparison + individual reports
                text_report = generate_multi_log_comparison(reports)
                text_report += "\n\n" + "=" * 70
                text_report += "\nDETAILED INDIVIDUAL LOG REPORTS\n"
                for r in reports[:3]:  # Limit to 3 detailed reports to fit context
                    text_report += "\n" + generate_text_report(r)

            # Setup queue and progress callback
            queue = asyncio.Queue()
            async def on_progress(event_type: str, data: Any):
                await queue.put((event_type, data))

            # Phase 1.5: Web Search Grounding
            yield _sse("web_search_start", {})
            web_search_context, web_search_data = await perform_web_search_flow(reports)
            yield _sse("web_search_complete", web_search_data)

            # Phase 2: Stage 1 — Expert analyses
            yield _sse("stage1_start", {})
            stage1_task = asyncio.create_task(
                stage1_expert_analyses(
                    text_report, request.user_query, request.model, on_progress=on_progress, persona_dataset=persona_dataset, report_dict=reports[0] if reports else None, web_search_context=web_search_context
                )
            )

            # Yield events from the queue while the task is executing
            while not stage1_task.done() or not queue.empty():
                try:
                    event_type, data = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield _sse(event_type, data)
                    queue.task_done()
                except asyncio.TimeoutError:
                    continue

            stage1 = await stage1_task
            yield _sse("stage1_complete", {"data": stage1})

            # Stage 2 — Cross-evaluation (currently skipped for speed with 3-persona setup)
            yield _sse("stage2_start", {})
            stage2 = []
            yield _sse("stage2_complete", {"data": stage2})

            # Phase 4: Stage 3 — Chairman synthesis
            yield _sse("stage3_start", {})
            stage3 = await stage3_chairman_synthesis(
                text_report, stage1, stage2, request.user_query, request.model, persona_dataset=persona_dataset, report_dict=reports[0] if reports else None, web_search_context=web_search_context
            )

            # Automatically save final report as markdown (.md)
            try:
                import os
                log_filenames = [l["filename"] for l in selected_logs]
                report_path = storage.save_report_as_markdown(
                    log_filenames, request.user_query, stage1, stage2, stage3
                )
                yield _sse("report_saved", {
                    "path": report_path,
                    "filename": os.path.basename(report_path),
                    "content": open(report_path, "r", encoding="utf-8").read()
                })
            except Exception as e:
                print(f"Error saving report as markdown: {e}")
                traceback.print_exc()

            yield _sse("stage3_complete", {"data": stage3})

            # Done
            yield _sse("complete", {})

        except Exception as e:
            traceback.print_exc()
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/ask/stream")
async def ask_question_stream(request: AskQuestionRequest):
    """
    Ask a free-form question to the council (with optional log context).
    Returns Server-Sent Events.
    """
    async def event_generator():
        try:
            text_report = None
            reports = []  # Initialize here to prevent NameError if log_ids is empty

            # If log IDs provided, parse them first
            if request.log_ids:
                all_logs = discover_logs(LOG_DIR)
                selected_logs = [l for l in all_logs if l["id"] in request.log_ids]

                if selected_logs:
                    yield _sse("parsing_start", {"total": len(selected_logs)})
                    reports = []
                    for i, log_entry in enumerate(selected_logs):
                        yield _sse("parsing_progress", {
                            "current": i + 1,
                            "total": len(selected_logs),
                            "filename": log_entry["filename"],
                        })
                        cached = get_cached(log_entry["path"])
                        if cached and "persona_dataset" in cached:
                            reports.append(cached)
                        else:
                            try:
                                report = parse_single_log(log_entry["path"])
                                set_cached(log_entry["path"], report)
                                reports.append(report)
                            except Exception:
                                if cached:
                                    reports.append(cached)

                    yield _sse("parsing_complete", {"parsed": len(reports)})

                    if reports:
                        if len(reports) == 1:
                            text_report = generate_text_report(reports[0])
                        else:
                            text_report = generate_multi_log_comparison(reports)

            # Extract persona dataset if single log is analyzed
            persona_dataset = reports[0].get("persona_dataset") if (request.log_ids and reports) else None

            # Setup queue and progress callback
            queue = asyncio.Queue()
            async def on_progress(event_type: str, data: Any):
                await queue.put((event_type, data))

            # Stage 1 + Stage 3 (skip Stage 2 for speed on questions)
            yield _sse("stage1_start", {})
            task = asyncio.create_task(
                ask_council_question(
                    request.question, text_report, request.model, on_progress=on_progress, persona_dataset=persona_dataset
                )
            )

            # Yield events from the queue while the task is executing
            while not task.done() or not queue.empty():
                try:
                    event_type, data = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield _sse(event_type, data)
                    queue.task_done()
                except asyncio.TimeoutError:
                    continue

            result = await task
            yield _sse("stage1_complete", {"data": result["stage1"]})

            yield _sse("stage3_start", {})

            # Automatically save final report as markdown (.md)
            try:
                import os
                log_filenames = []
                if request.log_ids:
                    all_logs = discover_logs(LOG_DIR)
                    selected_logs_local = [l for l in all_logs if l["id"] in request.log_ids]
                    log_filenames = [l["filename"] for l in selected_logs_local]
                report_path = storage.save_report_as_markdown(
                    log_filenames, request.question, result["stage1"], [], result["stage3"]
                )
                yield _sse("report_saved", {
                    "path": report_path,
                    "filename": os.path.basename(report_path),
                    "content": open(report_path, "r", encoding="utf-8").read()
                })
            except Exception as e:
                print(f"Error saving report as markdown: {e}")
                traceback.print_exc()

            yield _sse("stage3_complete", {"data": result["stage3"]})

            yield _sse("complete", {})

        except Exception as e:
            traceback.print_exc()
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Conversation Endpoints (Preserved from original)
# ---------------------------------------------------------------------------

@app.get("/api/conversations")
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations")
async def create_conversation():
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def format_conversation_history(messages: List[Dict[str, Any]]) -> str:
    """Format previous messages in a conversation as context for the LLM."""
    if not messages:
        return ""
    
    history_lines = []
    for msg in messages:
        role = msg.get("role")
        if role == "user":
            history_lines.append(f"Kullanıcı: {msg.get('content')}")
        elif role == "assistant":
            s3 = msg.get("stage3", {})
            response_text = ""
            if isinstance(s3, dict):
                response_text = s3.get("response", "")
            else:
                response_text = str(s3)
            if response_text:
                # Truncate very long synthesis reports in history to prevent token bloat
                if len(response_text) > 1000:
                    response_text = response_text[:1000] + "... [devamı kısaltıldı]"
                history_lines.append(f"Konsey Baş Mühendisi: {response_text}")
                
    if not history_lines:
        return ""
        
    return "\n### GEÇMİŞ KONUŞMA GEÇMİŞİ (CONVERSATION HISTORY)\n" + "\n".join(history_lines) + "\n"


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message in a conversation context with streaming response.
    Supports optional log context.
    """
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_first_message = len(conversation["messages"]) == 0
    is_follow_up = not is_first_message

    async def event_generator():
        try:
            # Extract history before adding the new user message
            history_context = format_conversation_history(conversation["messages"])

            storage.add_user_message(conversation_id, request.content)

            # Persist and resolve log IDs
            log_ids = request.log_ids or conversation.get("log_ids")
            if request.log_ids and request.log_ids != conversation.get("log_ids"):
                conversation["log_ids"] = request.log_ids
                storage.save_conversation(conversation)

            # Title generation in parallel
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content, request.model)
                )

            # Parse logs if available
            text_report = None
            reports = []
            if log_ids:
                all_logs = discover_logs(LOG_DIR)
                selected_logs = [l for l in all_logs if l["id"] in log_ids]
                if selected_logs:
                    yield _sse("parsing_start", {"total": len(selected_logs)})
                    for i, log_entry in enumerate(selected_logs):
                        yield _sse("parsing_progress", {
                            "current": i + 1,
                            "total": len(selected_logs),
                            "filename": log_entry["filename"],
                        })
                        cached = get_cached(log_entry["path"])
                        if cached and "persona_dataset" in cached:
                            reports.append(cached)
                        else:
                            try:
                                report = parse_single_log(log_entry["path"])
                                set_cached(log_entry["path"], report)
                                reports.append(report)
                            except Exception:
                                if cached:
                                    reports.append(cached)
                    yield _sse("parsing_complete", {"parsed": len(reports)})
                    if reports:
                        text_report = (
                            generate_text_report(reports[0]) if len(reports) == 1
                            else generate_multi_log_comparison(reports)
                        )

            # Extract persona dataset if single log is analyzed
            persona_dataset = reports[0].get("persona_dataset") if (log_ids and reports) else None

            # Run Web Search Grounding
            yield _sse("web_search_start", {})
            web_search_context, web_search_data = await perform_web_search_flow(reports)
            yield _sse("web_search_complete", web_search_data)

            # Setup queue and progress callback
            queue = asyncio.Queue()
            async def on_progress(event_type: str, data: Any):
                await queue.put((event_type, data))

            # Run analysis (Stage 1)
            yield _sse("stage1_start", {})
            stage1_task = asyncio.create_task(
                stage1_expert_analyses(
                    text_report or "Log verisi yüklenmedi.", request.content, request.model, on_progress=on_progress, persona_dataset=persona_dataset, report_dict=reports[0] if reports else None, history=history_context, web_search_context=web_search_context
                )
            )

            # Yield events from the queue while the task is executing
            while not stage1_task.done() or not queue.empty():
                try:
                    event_type, data = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield _sse(event_type, data)
                    queue.task_done()
                except asyncio.TimeoutError:
                    continue

            stage1 = await stage1_task
            yield _sse("stage1_complete", {"data": stage1})

            # Stage 2 — Cross-evaluation (currently skipped for speed with 3-persona setup)
            yield _sse("stage2_start", {})
            stage2 = []
            yield _sse("stage2_complete", {"data": stage2})

            # Run chairman synthesis (Stage 3)
            yield _sse("stage3_start", {})
            stage3 = await stage3_chairman_synthesis(
                text_report or "Log verisi yüklenmedi.", stage1, stage2, request.content, request.model, persona_dataset=persona_dataset, report_dict=reports[0] if reports else None, history=history_context, web_search_context=web_search_context
            )

            # Automatically save final report as markdown (.md)
            try:
                import os
                log_filenames = []
                if log_ids:
                    all_logs = discover_logs(LOG_DIR)
                    selected_logs_local = [l for l in all_logs if l["id"] in log_ids]
                    log_filenames = [l["filename"] for l in selected_logs_local]
                report_path = storage.save_report_as_markdown(
                    log_filenames, request.content, stage1, stage2, stage3
                )
                yield _sse("report_saved", {
                    "path": report_path,
                    "filename": os.path.basename(report_path),
                    "content": open(report_path, "r", encoding="utf-8").read()
                })
            except Exception as e:
                print(f"Error saving report as markdown: {e}")
                traceback.print_exc()

            yield _sse("stage3_complete", {"data": stage3})

            # Save to conversation
            storage.add_assistant_message(
                conversation_id, stage1, stage2, stage3, web_search=web_search_data
            )

            # Title
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield _sse("title_complete", {"title": title})

            yield _sse("complete", {})

        except Exception as e:
            traceback.print_exc()
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Log Preprocessing (Background / Batch)
# ---------------------------------------------------------------------------

@app.post("/api/logs/preprocess")
async def preprocess_logs(log_ids: Optional[List[str]] = None):
    """
    Pre-parse and cache selected (or all) log files.
    Returns immediately with status — parsing happens in background via streaming.
    """
    all_logs = discover_logs(LOG_DIR)

    if log_ids:
        target_logs = [l for l in all_logs if l["id"] in log_ids]
    else:
        target_logs = [l for l in all_logs if not is_cached(l["path"])]

    async def event_generator():
        for i, log_entry in enumerate(target_logs):
            if is_cached(log_entry["path"]):
                yield _sse("skip", {
                    "current": i + 1,
                    "total": len(target_logs),
                    "filename": log_entry["filename"],
                    "reason": "already cached",
                })
                continue

            yield _sse("parsing", {
                "current": i + 1,
                "total": len(target_logs),
                "filename": log_entry["filename"],
                "size_mb": log_entry["size_mb"],
            })

            try:
                report = parse_single_log(log_entry["path"])
                set_cached(log_entry["path"], report)
                yield _sse("parsed", {
                    "current": i + 1,
                    "total": len(target_logs),
                    "filename": log_entry["filename"],
                })
            except Exception as e:
                yield _sse("error", {
                    "filename": log_entry["filename"],
                    "error": str(e),
                })

        yield _sse("complete", {"total_processed": len(target_logs)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(event_type: str, data: Any) -> str:
    """Format a Server-Sent Event."""
    return f"data: {json.dumps({'type': event_type, **data}, default=str)}\n\n"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
