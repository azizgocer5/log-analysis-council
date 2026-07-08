"""2-stage UAV Log Analysis LLM Council orchestration.

Stage 1: Each persona (3 experts) analyzes the flight log from their expertise
Stage 2 (Optional): Cross-evaluation of each other's analyses — currently skipped for speed
Stage 3: Chairman synthesizes final prioritized prescription list
"""

from typing import List, Dict, Any, Tuple, Optional, Callable, Awaitable
import asyncio
import json

from .openrouter import query_model
from .config import COUNCIL_MODEL, CHAIRMAN_MODEL
from .personas import PERSONAS, CHAIRMAN_PERSONA, get_persona_names
from .academic_kb import get_academic_context
from .vehicle_profile import build_profile_from_log, format_vehicle_context


def clean_control_characters(s: str) -> str:
    """Escapes literal newlines, tabs, and carriage returns inside double quoted string values."""
    in_string = False
    escaped = False
    result = []
    for char in s:
        if char == '"' and not escaped:
            in_string = not in_string
        if in_string:
            if char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            else:
                result.append(char)
        else:
            result.append(char)
        if char == '\\' and not escaped:
            escaped = True
        else:
            escaped = False
    return "".join(result)


def clean_trailing_commas(s: str) -> str:
    """Removes trailing commas inside JSON arrays/objects."""
    import re
    s = re.sub(r',\s*\]', ']', s)
    s = re.sub(r',\s*\}', '}', s)
    return s


def extract_json_array(text: str) -> List[Dict[str, Any]]:
    """Clean markdown backticks, prefixes, control characters, and parse text into a JSON array robustly."""
    text_clean = text.strip()
    
    # Try finding the array inside potential conversation wrapping
    start_idx = text_clean.find('[')
    end_idx = text_clean.rfind(']')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text_clean = text_clean[start_idx:end_idx+1]
        
    # Clean garbage prefix after opening bracket, e.g. [JSON ...
    first_brace = text_clean.find('{')
    if first_brace != -1 and first_brace > 1:
        garbage = text_clean[1:first_brace].strip()
        if garbage:
            text_clean = "[" + text_clean[first_brace:]
            
    # Escape literal control characters inside string values
    text_clean = clean_control_characters(text_clean)
    
    # Clean trailing commas
    text_clean = clean_trailing_commas(text_clean)
        
    try:
        parsed = json.loads(text_clean)
        if isinstance(parsed, list):
            return parsed
        raise ValueError("JSON is not a list")
    except Exception as e:
        # Fallback to standard cleaning of markdown blocks
        try:
            t = text.strip()
            if t.startswith("```json"):
                t = t[7:]
            elif t.startswith("```"):
                t = t[3:]
            if t.endswith("```"):
                t = t[:-3]
            t = t.strip()
            
            first_brace_t = t.find('{')
            if first_brace_t != -1 and first_brace_t > 1:
                garbage_t = t[1:first_brace_t].strip()
                if garbage_t:
                    t = "[" + t[first_brace_t:]
                    
            t = clean_control_characters(t)
            t = clean_trailing_commas(t)
            
            parsed = json.loads(t)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        raise e


async def _query_persona(
    persona_id: str,
    user_message: str,
    system_prompt: str,
    model: str = COUNCIL_MODEL,
) -> Dict[str, Any]:
    """Query a single persona with system prompt and user message (standard markdown query)."""
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


async def _query_persona_with_json(
    persona_id: str,
    user_message: str,
    system_prompt: str,
    model: str = COUNCIL_MODEL,
) -> Dict[str, Any]:
    """Query a single persona and ensure it returns a valid JSON list of recipes.
    If parsing fails, retries exactly once.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    response = await query_model(model, messages, timeout=180.0)
    raw_content = response.get("content", "") if response else ""
    
    try:
        recipes = extract_json_array(raw_content)
        return {
            "persona_id": persona_id,
            "recipes": recipes,
            "error": False,
        }
    except Exception as e:
        print(f"[JSON Parse Error] Persona {persona_id} failed on first attempt: {e}. Retrying once...")
        
        # Retry prompt reminding the model of JSON schema requirements
        retry_prompt = (
            "Önceki yanıtın geçerli bir JSON formatında değildi. Lütfen sadece belirtilen JSON şemasına uygun geçerli bir JSON listesi (Array) döndür.\n"
            "JSON dışında yanıtında hiçbir ek metin, giriş/çıkış açıklaması olmamalıdır.\n"
            "Örnek format:\n"
            "[\n"
            "  {\n"
            "    \"recete_id\": \"recete_1\",\n"
            "    \"parametre\": \"MC_ROLLRATE_P\",\n"
            "    \"mevcut_deger\": 0.15,\n"
            "    \"onerilen_deger\": 0.12,\n"
            "    \"degisim_yuzdesi\": -20.0,\n"
            "    \"kanit_topic\": \"vehicle_angular_velocity\",\n"
            "    \"kanit_zaman_damgasi\": 12.5,\n"
            "    \"guven_seviyesi\": \"orta\",\n"
            "    \"safety_critical\": false,\n"
            "    \"gerekce\": \"açıklama\"\n"
            "  }\n"
            "]"
        )
        
        retry_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": raw_content},
            {"role": "user", "content": retry_prompt}
        ]
        
        try:
            retry_response = await query_model(model, retry_messages, timeout=180.0)
            retry_raw = retry_response.get("content", "") if retry_response else ""
            recipes = extract_json_array(retry_raw)
            return {
                "persona_id": persona_id,
                "recipes": recipes,
                "error": False,
            }
        except Exception as retry_e:
            print(f"[JSON Parse Error] Persona {persona_id} failed on retry: {retry_e}")
            fallback_recipe = {
                "recete_id": "format_error",
                "parametre": "error",
                "mevcut_deger": None,
                "onerilen_deger": 0.0,
                "degisim_yuzdesi": 0.0,
                "kanit_topic": "N/A",
                "kanit_zaman_damgasi": 0.0,
                "guven_seviyesi": "dusuk",
                "safety_critical": False,
                "gerekce": f"JSON parsing failed after retry. Error: {retry_e}. Raw: {raw_content}"
            }
            return {
                "persona_id": persona_id,
                "recipes": [fallback_recipe],
                "error": True,
            }


def render_recipes_to_markdown(recipes: List[Dict[str, Any]]) -> str:
    """Render a list of structured JSON recipes to a beautiful markdown format."""
    if not recipes:
        return "Herhangi bir reçete önerilmedi."
        
    lines = []
    
    # Check if there are format errors
    has_format_error = any(r.get("recete_id") == "format_error" for r in recipes)
    if has_format_error:
        lines.append("> [!WARNING]")
        lines.append("> **Format Hatası:** Uzman çıktısı JSON şemasına uygun parse edilemedi.")
        lines.append("")
        
    for r in recipes:
        recete_id = r.get("recete_id", "N/A")
        parametre = r.get("parametre", "N/A")
        mevcut = r.get("mevcut_deger")
        mevcut_str = f"{mevcut}" if mevcut is not None else "N/A"
        
        onerilen = r.get("onerilen_deger")
        onerilen_str = f"{onerilen}" if onerilen is not None else "N/A"
        
        degisim = r.get("degisim_yuzdesi")
        if degisim is not None:
            try:
                degisim_str = f"{float(degisim):+.2f}%"
            except (ValueError, TypeError):
                degisim_str = f"{degisim}%"
        else:
            degisim_str = "N/A"
            
        topic = r.get("kanit_topic", "N/A")
        timestamp = r.get("kanit_zaman_damgasi", 0.0)
        guven = r.get("guven_seviyesi", "dusuk")
        safety = r.get("safety_critical", False)
        gerekce = r.get("gerekce", "N/A")
        
        # Visual highlights
        safety_badge = " ⚠️ [SAFETY CRITICAL]" if safety else ""
        zayif_badge = " 🔴 [ZAYIF KANIT]" if r.get("dogrulanamadi") else ""
        guven_color = "🟢 Yüksek" if guven == "yuksek" else "🟡 Orta" if guven == "orta" else "🔴 Düşük"
        
        lines.append(f"### Reçete: {recete_id}{safety_badge}{zayif_badge}")
        lines.append(f"- **Etkilenen Parametre/Bileşen:** `{parametre}`")
        lines.append(f"- **Mevcut Değer:** `{mevcut_str}` | **Önerilen Değer:** `{onerilen_str}` (Değişim: `{degisim_str}`)")
        lines.append(f"- **Kanıt Kaynağı:** `{topic}` (Zaman damgası: `{timestamp}s`)")
        lines.append(f"- **Güven Seviyesi:** {guven_color}")
        lines.append(f"- **Gerekçe:** {gerekce}")
        if r.get("dogrulanamadi"):
            val_err = r.get("validation_error", "Log verileriyle programatik olarak doğrulanamadı.")
            lines.append(f"- > **[ZAYIF KANIT UYARISI]:** {val_err}")
        lines.append("")
        
    return "\n".join(lines)


def render_chairman_report(
    recipes: List[Dict[str, Any]], 
    report_dict: Optional[Dict[str, Any]] = None, 
    web_search_context: Optional[str] = None
) -> str:
    """Render the final chairman synthesis report from the structured recipes list,
    enriching it with environmental weather conditions, fleet comparisons, and web search evidence.
    Flow ordered as: Final Recipes/Tables first, then Synthesis Analyses, then Bibliography/Web Search at the end.
    """
    if not recipes:
        return "# 👨‍✈️ COUNCIL NİHAİ RAPORU\n\nHerhangi bir reçete üretilmedi veya analiz sırasında hata oluştu."
        
    lines = []
    lines.append("# COUNCIL NİHAİ RAPORU")
    lines.append("")
    
    # =========================================================================
    # BÖLÜM 1: NİHAİ REÇETELER VE PARAMETRE DEĞİŞİKLİK TABLOLARI
    # =========================================================================
    lines.append("## 📋 ÖNCELİKLENDİRİLMİŞ NİHAİ REÇETE LİSTESİ")
    lines.append("Uçuş log analizleri ve uzman görüşlerinin senteziyle oluşturulan öncelikli parametre ve mekanik reçete önerileri aşağıdadır:")
    lines.append("")
    
    for r in recipes:
        recete_id = r.get("recete_id", "N/A")
        parametre = r.get("parametre", "N/A")
        mevcut = r.get("mevcut_deger")
        mevcut_str = f"{mevcut}" if mevcut is not None else "N/A"
        
        onerilen = r.get("onerilen_deger")
        onerilen_str = f"{onerilen}" if onerilen is not None else "N/A"
        
        degisim = r.get("degisim_yuzdesi")
        if degisim is not None:
            try:
                degisim_str = f"{float(degisim):+.2f}%"
            except (ValueError, TypeError):
                degisim_str = f"{degisim}%"
        else:
            degisim_str = "N/A"
            
        topic = r.get("kanit_topic", "N/A")
        timestamp = r.get("kanit_zaman_damgasi", 0.0)
        guven = r.get("guven_seviyesi", "dusuk")
        safety = r.get("safety_critical", False)
        gerekce = r.get("gerekce", "N/A")
        
        safety_badge = " ⚠️ [SAFETY CRITICAL]" if safety else ""
        zayif_badge = " 🔴 [ZAYIF KANIT]" if r.get("dogrulanamadi") else ""
        guven_color = "🟢 Yüksek" if guven == "yuksek" else "🟡 Orta" if guven == "orta" else "🔴 Düşük"
        
        lines.append(f"### Reçete: {recete_id}{safety_badge}{zayif_badge}")
        lines.append(f"- **Parametre:** `{parametre}`")
        lines.append(f"- **Değerler:** Mevcut: `{mevcut_str}` | Önerilen: `{onerilen_str}` (Değişim: `{degisim_str}`)")
        lines.append(f"- **Kanıt:** `{topic}` (t = `{timestamp}s`)")
        lines.append(f"- **Güven Seviyesi:** {guven_color}")
        lines.append(f"- **Gerekçe:** {gerekce}")
        if r.get("dogrulanamadi"):
            val_err = r.get("validation_error", "Log verileriyle programatik olarak doğrulanamadı.")
            lines.append(f"- > **[ZAYIF KANIT UYARISI]:** {val_err}")
        lines.append("")

    # Safety Critical Warnings Summary
    safety_recipes = [r for r in recipes if r.get("safety_critical")]
    if safety_recipes:
        lines.append("### ⚠️ İNSAN ONAYI GEREKLİ (SAFETY CRITICAL)")
        lines.append("Aşağıdaki reçeteler uçuş güvenliğini doğrudan etkileyebilecek niteliktedir ve uçuş öncesi **İnsan Onayı** gerektirmektedir:")
        for sr in safety_recipes:
            zayif_str = " [ZAYIF KANIT]" if sr.get("dogrulanamadi") else ""
            lines.append(f"- **{sr.get('recete_id', 'N/A')}** ({sr.get('parametre', 'N/A')}): {sr.get('gerekce', 'N/A')}{zayif_str}")
        lines.append("")

    # Table section
    lines.append("### PX4 PARAMETRE DEĞİŞİKLİK TABLOSU")
    lines.append("| Parametre | Mevcut | Önerilen | Gerekçe | Risk | Güven |")
    lines.append("|-----------|--------|----------|---------|------|-------|")
    for r in recipes:
        parametre = r.get("parametre", "N/A")
        mevcut = r.get("mevcut_deger")
        mevcut_str = f"{mevcut}" if mevcut is not None else "N/A"
        
        onerilen = r.get("onerilen_deger")
        onerilen_str = f"{onerilen}" if onerilen is not None else "N/A"
        
        guven = r.get("guven_seviyesi", "dusuk")
        guven_str = str(guven).upper() if guven is not None else "DUSUK"
        
        safety_str = "HIGH ⚠️" if r.get("safety_critical") else "MEDIUM"
        if r.get("dogrulanamadi"):
            safety_str += " (ZAYIF KANIT)"
            
        lines.append(f"| `{parametre}` | `{mevcut_str}` | `{onerilen_str}` | {r.get('gerekce', 'N/A')[:40]}... | {safety_str} | {guven_str} |")
    lines.append("")

    # Test Flight Plan
    lines.append("### SONRAKİ TEST UÇUŞU PLANI")
    lines.append("Önerilen parametre ve mekanik değişikliklerinin havada doğrulanması için aşağıdaki test prosedürleri uygulanmalıdır:")
    lines.append("1. **Güvenlik Kontrolü:** Safety Critical işaretli parametrelerin elle doğrulandığından emin olun.")
    lines.append("2. **Hover Testi:** İlk kalkıştan sonra 3-5 metre irtifada hover kararlılığını ve titreşimi izleyin.")
    lines.append("3. **Basamak Tepki Testi:** Roll/Pitch eksenlerinde küçük basamak (step) komutları vererek tracking başarımını ve overshoot durumunu test edin.")
    lines.append("4. **Log Analizi:** Uçuş sonrasında yeni logları RAG sistemine besleyerek iyileşmeyi doğrulayın.")
    lines.append("")

    # =========================================================================
    # BÖLÜM 2: NİHAİ ANALİZLER VE SENTEZLER
    # =========================================================================
    lines.append("---")
    lines.append("")
    lines.append("## 🔬 NİHAİ ANALİZLER VE SENTEZLER")
    lines.append("")
    lines.append("### GENEL DEĞERLENDİRME")
    lines.append(f"Uçuş log analizleri ve uzman görüşlerinin sentezi sonucunda toplam **{len(recipes)}** adet somut reçete belirlenmiştir.")
    lines.append("Bu reçeteler, drone güvenliği ve kontrol performansı önceliklendirilerek yukarıda listelenmiştir.")
    lines.append("")
    
    # 🌦️ Environmental & Weather Conditions
    if report_dict and "wind" in report_dict:
        wind = report_dict["wind"]
        if wind:
            lines.append("### 🌦️ ÇEVRESEL VE METEOROLOJİK KOŞULLAR")
            lines.append(f"- **Tahmini Rüzgar Hızı:** Ortalama `{wind.get('avg_wind_speed_m_s', 0.0)} m/s` (Maksimum Hamla: `{wind.get('max_wind_speed_m_s', 0.0)} m/s`)")
            lines.append(f"- **Hava Şiddeti Sınıfı:** {wind.get('wind_speed_status', 'Bilinmiyor')}")
            lines.append("- **Etki Analizi:** Rüzgarlı ve hamlalı havalar, drone'un aerodinamik sürüklenmesini artırarak kontrol döngüleri (PID) ve motor itki dağılımı (motor balance) üzerinde doğrudan bozucu etki yaratır. Reçeteler uygulanırken bu çevre koşulları mutlaka göz önünde bulundurulmalıdır.")
            lines.append("")

    # 📋 Similar Vehicles Local Fleet comparison
    if report_dict:
        from .log_parser import get_similar_vehicles_markdown
        try:
            similar_md = get_similar_vehicles_markdown(report_dict)
            if similar_md and ("|" in similar_md or "Ağırlık" in similar_md):
                lines.append("### 📋 FİLO REFERANS BAZINDA BENZER ARAÇ ANALİZLERİ")
                lines.append("Veritabanımızdaki diğer uçuş loglarından, benzer ağırlık ve rotor konfigürasyonuna sahip olan araçların PID ve başarım karşılaştırması aşağıdadır:")
                lines.append("")
                lines.append(similar_md)
                lines.append("")
        except Exception as e:
            print(f"[Council] Error generating similar vehicles md for report: {e}")

    # =========================================================================
    # BÖLÜM 3: BİBLİYOGRAFYA VE WEB ARAŞTIRMA KANITLARI (En sonda)
    # =========================================================================
    if web_search_context:
        lines.append("---")
        lines.append("")
        lines.append("## 🌐 BİBLİYOGRAFYA VE WEB ARAŞTIRMA KANITLARI")
        lines.append("Gemini Google Search Grounding üzerinden yapılan sorgularla elde edilen güncel literatür ve resmi otopilot dokümantasyonu referans verileri:")
        lines.append("")
        clean_context = web_search_context.replace("### ", "#### ")
        lines.append(clean_context)
        lines.append("")
        
    return "\n".join(lines)


def retrieve_rag_context(user_query: Optional[str], log_report: str) -> str:
    """Retrieve relevant technical document chunks based on user query and log anomalies."""
    try:
        from .vector_db import SimpleVectorDB
        db = SimpleVectorDB()
        
        # Build search query by combining user query and detected log anomalies
        search_terms = []
        if user_query:
            search_terms.append(user_query)
            
        # Detect basic log anomalies to enrich retrieval
        log_lower = log_report.lower()
        if "clip" in log_lower or "clipping" in log_lower:
            search_terms.append("IMU clipping akselerometre vibrasyon")
        if "imbalance" in log_lower or "dengesiz" in log_lower or "motor" in log_lower:
            search_terms.append("motor dengesizliği spread ağırlık merkezi CoG")
        if "innovation" in log_lower or "ekf" in log_lower or "compass" in log_lower or "pusula" in log_lower:
            search_terms.append("EKF innovation test ratio pusula manyetik")
        if "failsafe" in log_lower or "quadchute" in log_lower or "transition" in log_lower or "geçi" in log_lower:
            search_terms.append("quadchute transition geçiş hava hızı stall")
            
        query = " ".join(search_terms).strip()
        if not query:
            query = "vibrasyon motor dengesizliği EKF pusula VTOL" # fallback general query
            
        results = db.search(query, top_k=2)
        if not results:
            return ""
            
        rag_lines = [
            "\n## RAG TEKNİK DOKÜMANTASYON REFERANSI (Mekanik arıza teşhisi için bu teknik sınırları ve eşleşmeleri referans al)",
            "Aşağıdaki teknik bilgi tabanı verilerini log analizindeki sapmaları açıklamak için kullan:"
        ]
        for r in results:
            rag_lines.append(f"\n--- (Kaynak: {r['metadata'].get('source', 'Bilinmeyen Kılavuz')}) ---\n{r['text']}")
            
        return "\n".join(rag_lines)
    except Exception as e:
        print(f"[RAG] Retrieval warning: {e}")
        return ""


# ---------------------------------------------------------------------------
# Stage 1: Individual Expert Analyses
# ---------------------------------------------------------------------------

async def stage1_expert_analyses(
    log_report: str,
    user_query: Optional[str] = None,
    model: Optional[str] = None,
    on_progress: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    persona_dataset: Optional[Dict[str, Any]] = None,
    report_dict: Optional[Dict[str, Any]] = None,
    history: Optional[str] = None,
    web_search_context: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Stage 1: Each persona analyzes the flight log independently.

    Args:
        log_report: Structured text report from log_parser
        user_query: Optional user question to focus the analysis
        model: Model identifier override
        on_progress: Optional progress callback function
        persona_dataset: Optional persona-specific parsed data dictionary
        history: Optional previous conversation history
        web_search_context: Optional context retrieved from Gemini Google Search

    Returns:
        List of dicts with persona_id, persona info, and response
    """
    active_model = model or COUNCIL_MODEL
    is_local = (active_model == "qwen3:8b")
    stagger_delay = 0.2 if is_local else 5.5

    persona_ids = get_persona_names()
    
    # Retrieve RAG context once for this run
    rag_context = retrieve_rag_context(user_query, log_report)

    async def run_single_persona(pid: str) -> Dict[str, Any]:
        persona = PERSONAS[pid]
        if on_progress:
            await on_progress("stage1_persona_start", {
                "persona_id": pid,
                "persona_name": persona["name"],
                "persona_title": persona["title"],
                "persona_icon": persona["icon"],
                "persona_color": persona["color"],
            })

        # Fetch academic context and dynamic vehicle profile overrides
        academic_context = get_academic_context(pid)
        
        vehicle_context_override = ""
        if report_dict:
            try:
                profile = build_profile_from_log(report_dict)
                vehicle_context_override = format_vehicle_context(profile)
            except Exception as e:
                print(f"[Council] Error building vehicle profile: {e}")

        # Assemble prompt sections
        academic_section = f"\n## AKADEMİK VE TEKNİK REFERANS BİLGİLERİ\n{academic_context}\n"
        web_section = f"\n## WEB ARAŞTIRMA VE BENZER ARAÇ ANALİZLERİ\n{web_search_context}\n" if web_search_context else ""
        vehicle_section = f"\n{vehicle_context_override}\n" if vehicle_context_override else ""
        history_section = f"\n{history}\n" if history else ""

        user_message_parts = []
        if persona_dataset:
            from .log_parser import format_context_block
            context_block = format_context_block(pid, persona_dataset)
            user_message_parts.append(context_block)
        else:
            user_message_parts.append("Aşağıda bir VTOL drone uçuş logundaki analiz verilerini bulacaksın.\n")
            
        user_message_parts.append(vehicle_section)
        user_message_parts.append(rag_context)
        user_message_parts.append(web_section)
        user_message_parts.append(academic_section)
        user_message_parts.append(history_section)
        
        if user_query:
            user_message_parts.append(f"Kullanıcının son sorusu: {user_query}\n")
            
        user_message_parts.append("""## ZORUNLU ÇIKTI BEKLENTİSİ
1. Yukarıdaki verileri, konuşma geçmişini, RAG teknik kılavuzlarını, akademik referansları ve web arama sonuçlarını referans alarak DEĞERLENDİR.
2. Her bulgu için KESİN bir yorum yap (iyi/kötü/kabul edilebilir).
3. EN AZ 1, en fazla 5 somut REÇETE yaz (reçete formatına kesinlikle uy).
4. Her reçetede mevcut değer ve önerilen değerleri sayısal/kesin olarak belirt.
5. Kanıt alanını asla boş bırakma ve spekülatif ifadelerden kaçın.
6. Reçete gerekçelerinde ve bulgularda akademik/teknik kaynaklara atıfta bulun (örn. [Ref-1] veya [Web-1]).
""")

        if not persona_dataset:
            user_message_parts.append(f"\n--- UÇUŞ LOG VERİLERİ ---\n{log_report}")

        user_message = "\n".join(user_message_parts)

        resp = await _query_persona_with_json(pid, user_message, persona["system_prompt"], active_model)
        
        if report_dict:
            from .validator import validate_recipe, load_safety_critical_params
            sc_list = load_safety_critical_params()
            validated_recipes = []
            for r in resp.get("recipes", []):
                val_r = validate_recipe(r, report_dict, sc_list)
                validated_recipes.append(val_r)
            resp["recipes"] = validated_recipes

        rendered_md = render_recipes_to_markdown(resp["recipes"])
        
        result = {
            "persona_id": pid,
            "persona_name": persona["name"],
            "persona_title": persona["title"],
            "persona_icon": persona["icon"],
            "persona_color": persona["color"],
            "response": rendered_md,
            "recipes": resp["recipes"],
            "error": resp.get("error", False),
        }
        
        if on_progress:
            await on_progress("stage1_persona_complete", {
                "persona_id": pid,
                "data": result,
            })
        return result

    if is_local:
        # Sequential execution with stagger delay to prevent overloading local models
        results = []
        for i, pid in enumerate(persona_ids):
            if i > 0:
                print(f"Staggering Stage 1 expert query for {pid}...")
                await asyncio.sleep(stagger_delay)
            res = await run_single_persona(pid)
            results.append(res)
    else:
        # Parallel execution for cloud models to drastically reduce wait time
        tasks = [run_single_persona(pid) for pid in persona_ids]
        results = await asyncio.gather(*tasks)

    return results


# ---------------------------------------------------------------------------
# Stage 2: Cross-Evaluation
# ---------------------------------------------------------------------------

async def stage2_cross_evaluation(
    log_report: str,
    stage1_results: List[Dict[str, Any]],
    user_query: Optional[str] = None,
    model: Optional[str] = None,
    on_progress: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    persona_dataset: Optional[Dict[str, Any]] = None,
    report_dict: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Stage 2: Each persona evaluates the others' analyses.

    Args:
        log_report: Original log report for reference
        stage1_results: Results from Stage 1
        user_query: Optional original user query
        model: Model identifier override
        on_progress: Optional progress callback function
        persona_dataset: Optional persona-specific parsed data dictionary

    Returns:
        List of cross-evaluation results
    """
    active_model = model or COUNCIL_MODEL
    is_local = (active_model == "qwen3:8b")
    stagger_delay = 0.2 if is_local else 5.5

    rag_context = retrieve_rag_context(user_query, log_report)

    # Build the compiled analyses text
    analyses_text = "\n\n".join([
        f"### {r['persona_icon']} {r['persona_name']} ({r['persona_title']}):\n{r['response']}"
        for r in stage1_results
        if not r.get("error")
    ])

    eval_prompt_template = """Aşağıda 3 uzmanın bir VTOL drone uçuş loguna dair analizlerini bulacaksın.
{query_section}
{rag_section}
Her uzmanın analizini kendi uzmanlık alanın perspektifinden titizlikle değerlendir ve aşağıdaki kurallara göre cevap ver:

1. **ONAYLADIĞIN reçeteler:** Hangi reçetelere katılıyorsun? Her biri için kendi uzmanlık alanındaki verilerle/referanslarla doğruluğu kanıtla.
2. **İTİRAZ ETTİĞİN reçeteler:** Hangi öneriler yanlış, riskli veya yetersiz gerekçelendirilmiş? Somut veri ve referans limitleriyle itiraz et, gerekirse ALTERNATİF reçete öner.
3. **EKSİK GÖRDÜĞÜN reçeteler:** Diğer uzmanlar nerede sorumluluk almaktan kaçınmış, muğlak konuşmuş veya reçete yazmamış? O boşlukları doldur ve kendi alanından KESİN reçeteler ekle.
4. **KANITSIZ/ZAYIF bulgular:** Hangi uzmanlar somut bir telemetry verisi veya log kaydı göstermeden genel/tahmini iddialarda bulunmuş? Bunları açıkça deşifre et ve güvenilirliğini [Düşük] olarak işaretle.
5. **ÖNCELİKLENDİRME:** En kritik gördüğün ilk 3 reçeteyi kesin öncelik sabitlemesiyle sırala ve gerekçelendir.

--- UZMAN ANALİZLERİ ---
{analyses}

--- REFERANS: UÇUŞ LOG VERİLERİ (ÖZET) ---
{log_summary}
"""

    query_section = f"\nKullanıcının orijinal sorusu: {user_query}\n" if user_query else ""

    # Shorten log report for stage 2 (use first 2000 chars as summary)
    log_summary = log_report[:3000] + "\n... [devamı kısaltıldı]" if len(log_report) > 3000 else log_report

    persona_ids = get_persona_names()

    async def run_single_persona_eval(pid: str) -> Dict[str, Any]:
        persona = PERSONAS[pid]
        if on_progress:
            await on_progress("stage2_persona_start", {
                "persona_id": pid,
                "persona_name": persona["name"],
                "persona_title": persona["title"],
                "persona_icon": persona["icon"],
                "persona_color": persona["color"],
            })
        
        # Grounding: use persona specific context block if available
        if persona_dataset:
            from .log_parser import format_context_block
            local_summary = format_context_block(pid, persona_dataset)
        else:
            local_summary = log_summary

        user_message = eval_prompt_template.format(
            query_section=query_section,
            rag_section=f"\n{rag_context}\n" if rag_context else "",
            analyses=analyses_text,
            log_summary=local_summary,
        )
        resp = await _query_persona_with_json(pid, user_message, persona["system_prompt"], active_model)
        
        if report_dict:
            from .validator import validate_recipe, load_safety_critical_params
            sc_list = load_safety_critical_params()
            validated_recipes = []
            for r in resp.get("recipes", []):
                val_r = validate_recipe(r, report_dict, sc_list)
                validated_recipes.append(val_r)
            resp["recipes"] = validated_recipes

        rendered_md = render_recipes_to_markdown(resp["recipes"])
        
        result = {
            "persona_id": pid,
            "persona_name": persona["name"],
            "persona_title": persona["title"],
            "persona_icon": persona["icon"],
            "persona_color": persona["color"],
            "evaluation": rendered_md,
            "recipes": resp["recipes"],
            "error": resp.get("error", False),
        }
        
        if on_progress:
            await on_progress("stage2_persona_complete", {
                "persona_id": pid,
                "data": result,
            })
        return result

    if is_local:
        # Sequential execution with stagger delay to prevent overloading local models
        results = []
        for i, pid in enumerate(persona_ids):
            if i > 0:
                print(f"Staggering Stage 2 expert query for {pid}...")
                await asyncio.sleep(stagger_delay)
            res = await run_single_persona_eval(pid)
            results.append(res)
    else:
        # Parallel execution for cloud models to drastically reduce wait time
        tasks = [run_single_persona_eval(pid) for pid in persona_ids]
        results = await asyncio.gather(*tasks)

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
    persona_dataset: Optional[Dict[str, Any]] = None,
    report_dict: Optional[Dict[str, Any]] = None,
    history: Optional[str] = None,
    web_search_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes all analyses into final prescription.

    Args:
        log_report: Original log report
        stage1_results: Individual expert analyses
        stage2_results: Cross-evaluations
        user_query: Optional original user query
        model: Model identifier override
        persona_dataset: Optional persona-specific parsed data dictionary
        history: Optional previous conversation history
        web_search_context: Optional context retrieved from Gemini Google Search

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

    # Grounding: use the structured general context for the chairman reference instead of truncated raw report
    if persona_dataset:
        import json
        genel_info = json.dumps(persona_dataset.get("genel", {}), ensure_ascii=False, indent=2)
        flight_data = f"### Genel Uçuş Bilgisi (Sadece Bu Değerleri Kullan)\n```json\n{genel_info}\n```"
    else:
        flight_data = log_report[:4000]

    history_section = f"\n{history}\n" if history else ""

    # Fetch academic context for the chairman
    academic_context = get_academic_context("chairman")
    
    web_section = f"\n--- WEB ARAŞTIRMA VE LİTERATÜR BAZLI REFERANSLAR ---\n{web_search_context}\n" if web_search_context else ""
    academic_section = f"\n--- AKADEMİK VE TEKNİK REFERANS BİLGİLERİ ---\n{academic_context}\n"

    chairman_prompt = f"""Sen UAV Log Analysis Council'ın Baş Mühendisisin. 3 uzman bir VTOL drone'un uçuş loglarını analiz etti.

Council Yapısı:
1. Kontrol Mühendisi Deniz — PID Tuning & Kontrol Sistemleri (rate/attitude kazançları)
2. Dr. Güvenlik — EKF, Sensör Füzyonu & Uçuş Güvenliği (EKF gates, failsafe, batarya)
3. Saha Mühendisi Kemal — Vibrasyon, Mekanik & Elektronik Teşhis (notch filter, CoG, motor)

{history_section}
{f"Kullanıcının son sorusu: {user_query}" if user_query else "Görev: Kapsamlı uçuş logu analizi ve PID tuning reçetesi"}

Tüm verileri, konuşma geçmişini, akademik referansları ve web arama sonuçlarını sentezleyerek nihai raporunu oluştur. Formatına uy.

{academic_section}
{web_section}

--- AŞAMA 1: UZMAN ANALİZLERİ ---
{stage1_text}

--- AŞAMA 2: ÇAPRAZ DEĞERLENDİRMELER ---
{stage2_text}

--- REFERANS UÇUŞ LOG VERİLERİ ---
{flight_data}
"""

    resp = await _query_persona_with_json(
        "chairman",
        chairman_prompt,
        CHAIRMAN_PERSONA["system_prompt"],
        active_model
    )
    
    if report_dict:
        from .validator import validate_recipe, load_safety_critical_params
        sc_list = load_safety_critical_params()
        validated_recipes = []
        for r in resp.get("recipes", []):
            val_r = validate_recipe(r, report_dict, sc_list)
            validated_recipes.append(val_r)
        resp["recipes"] = validated_recipes

    rendered_report = render_chairman_report(resp["recipes"], report_dict, web_search_context)

    return {
        "persona_name": CHAIRMAN_PERSONA["name"],
        "persona_title": CHAIRMAN_PERSONA["title"],
        "persona_icon": CHAIRMAN_PERSONA["icon"],
        "persona_color": CHAIRMAN_PERSONA["color"],
        "response": rendered_report,
        "recipes": resp["recipes"],
        "error": resp.get("error", False),
    }


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------

async def run_uav_council(
    log_report: str,
    user_query: Optional[str] = None,
    model: Optional[str] = None,
    persona_dataset: Optional[Dict[str, Any]] = None,
    report_dict: Optional[Dict[str, Any]] = None,
    history: Optional[str] = None,
    web_search_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the complete 3-stage UAV analysis council.

    Args:
        log_report: Structured text report from log parser
        user_query: Optional user question
        model: Optional model override
        persona_dataset: Optional persona-specific parsed data dictionary
        report_dict: Optional raw parsed log report dictionary for verification
        history: Optional previous conversation history
        web_search_context: Optional context retrieved from Gemini Google Search

    Returns:
        Dict with stage1, stage2, stage3 results
    """
    # Stage 1
    stage1 = await stage1_expert_analyses(
        log_report, user_query, model, persona_dataset=persona_dataset, report_dict=report_dict, history=history, web_search_context=web_search_context
    )

    if not any(not r.get("error") for r in stage1):
        return {
            "stage1": stage1,
            "stage2": [],
            "stage3": {"error": True, "response": "Hiçbir uzman yanıt veremedi."},
        }

    # Stage 2
    stage2 = await stage2_cross_evaluation(log_report, stage1, user_query, model, persona_dataset=persona_dataset, report_dict=report_dict)

    # Stage 3
    stage3 = await stage3_chairman_synthesis(
        log_report, stage1, stage2, user_query, model, persona_dataset=persona_dataset, report_dict=report_dict, history=history, web_search_context=web_search_context
    )

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
    on_progress: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
    persona_dataset: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Ask a free-form question to the council.

    If log_report is provided, the question is contextualized with the log data.
    Otherwise, it's a general PX4/UAV question.
    """
    active_model = model or COUNCIL_MODEL

    # Stage 1: Get expert opinions
    if log_report or persona_dataset:
        stage1 = await stage1_expert_analyses(
            log_report or "", question, active_model, on_progress=on_progress, persona_dataset=persona_dataset
        )
    else:
        # Without log data, run with progress support and parallel/sequential choice
        is_local = (active_model == "qwen3:8b")
        stagger_delay = 0.2 if is_local else 5.5
        persona_ids = get_persona_names()

        async def run_single_persona_question(pid: str) -> Dict[str, Any]:
            persona = PERSONAS[pid]
            if on_progress:
                await on_progress("stage1_persona_start", {
                    "persona_id": pid,
                    "persona_name": persona["name"],
                    "persona_title": persona["title"],
                    "persona_icon": persona["icon"],
                    "persona_color": persona["color"],
                })
            
            resp = await _query_persona(pid, question, persona["system_prompt"], active_model)
            result = {
                "persona_id": pid,
                "persona_name": persona["name"],
                "persona_title": persona["title"],
                "persona_icon": persona["icon"],
                "persona_color": persona["color"],
                "response": resp["response"],
                "error": resp.get("error", False),
            }
            if on_progress:
                await on_progress("stage1_persona_complete", {
                    "persona_id": pid,
                    "data": result,
                })
            return result

        if is_local:
            stage1 = []
            for i, pid in enumerate(persona_ids):
                if i > 0:
                    await asyncio.sleep(stagger_delay)
                res = await run_single_persona_question(pid)
                stage1.append(res)
        else:
            tasks = [run_single_persona_question(pid) for pid in persona_ids]
            stage1 = await asyncio.gather(*tasks)

    # Stage 3: Chairman synthesis (skip Stage 2 for questions to save time/cost)
    stage3 = await stage3_chairman_synthesis(
        log_report or "Log verisi yüklenmedi.",
        stage1,
        [],  # No cross-evaluation for questions
        question,
        active_model,
        persona_dataset=persona_dataset,
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
