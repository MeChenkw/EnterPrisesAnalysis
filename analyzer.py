"""
V3 Analyzer: DeepSeek web_search instead of Bing scraping.
Each dimension is a self-contained LLM call with web search enabled.
"""
import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]

# Load .env for standalone use
from dotenv import load_dotenv
load_dotenv()

sys.stdout.reconfigure(encoding="utf-8")

# ═══════════════════════════════════════════════════
#  V3 Self-contained prompts (model searches the web)
# ═══════════════════════════════════════════════════

PROMPT_OVERVIEW = """请先搜索网络，然后以求职者视角分析"{company}"。

需要搜索并回答：
- 公司基本信息：做什么的、多大规模、成立多久、在哪
- 融资/上市状态、估值
- 近期重大事件（融资、裁员、新业务等）
- ⚠️ 风险信号（经营异常、司法纠纷、负面新闻）
- 一句话判断：这家公司稳不稳

输出 JSON：
{{
  "name": "公司全称",
  "tags": ["标签"],
  "summary": "一句话总结（≤60字）",
  "details": ["要点"],
  "risk_flags": [],
  "risk_level": "low/medium/high",
  "data_quality": "sufficient/limited/insufficient",
  "sources": ["来源"]
}}
只输出 JSON。不确定就说不知道。"""

PROMPT_SALARY = """请先搜索网络，然后分析在"{company}"的薪资待遇。

搜索以下信息：
- 具体岗位的薪资区间（注明来源平台）
- 与同城市同行业的对比
- 福利情况（公积金、补贴、年终奖等）
- 应届生和社招分别什么水平

输出 JSON：
{{
  "summary": "薪资水平总结（≤60字）",
  "roles": [{{"role": "岗位名", "range": "薪资区间", "source": "来源平台"}}],
  "market_compare": "与市场对比",
  "details": ["要点"],
  "data_quality": "sufficient/limited/insufficient",
  "sources": ["来源"]
}}
只输出 JSON。没有数据就诚实说。"""

PROMPT_CULTURE = """请先搜索网络，然后分析在"{company}"工作的真实体验。

搜索以下信息：
- 加班情况、工作强度
- 管理风格、团队氛围
- 员工真实口碑（正面和负面都要，注明来源平台如脉脉/知乎/看准）
- 福利、晋升机制

输出 JSON：
{{
  "summary": "工作体验总结（≤60字）",
  "sentiment": "positive/mixed/negative/unknown",
  "keywords": ["关键词"],
  "positive": ["正面评价"],
  "negative": ["负面评价"],
  "details": ["要点"],
  "data_quality": "sufficient/limited/insufficient",
  "sources": ["来源"]
}}
只输出 JSON。如实反映，不美化。"""

PROMPT_INTERVIEW = """请先搜索网络，然后汇总"{company}"的面试经验。

搜索以下信息：
- 面试流程（几轮、什么形式）
- 常见考点/题型（具体题目）
- 难度感受和通过率
- 面试者建议和注意事项

输出 JSON：
{{
  "summary": "面试情况总结（≤60字）",
  "difficulty": "easy/medium/hard/unknown",
  "process": ["第1轮: ..."],
  "common_questions": ["常见题"],
  "tips": ["建议"],
  "details": ["要点"],
  "data_quality": "sufficient/limited/insufficient",
  "sources": ["来源"]
}}
只输出 JSON。"""

PROMPT_HIRING = """请先搜索网络，然后分析"{company}"当前的招聘态势。

搜索以下信息：
- 近期在招岗位（具体名称和数量）
- 招聘趋势（扩张/稳定/收缩）
- 校招和社招情况
- 热门方向

输出 JSON：
{{
  "summary": "招聘态势总结（≤60字）",
  "trend": "expanding/stable/shrinking/unknown",
  "openings_estimate": "大致数量",
  "hot_roles": ["热门岗位"],
  "details": ["要点"],
  "data_quality": "sufficient/limited/insufficient",
  "sources": ["来源"]
}}
只输出 JSON。"""

DIMENSIONS = {
    "company_overview": {"name": "公司速览", "prompt": PROMPT_OVERVIEW, "icon": "⚡"},
    "salary": {"name": "薪资待遇", "prompt": PROMPT_SALARY, "icon": "💰"},
    "culture": {"name": "工作文化与口碑", "prompt": PROMPT_CULTURE, "icon": "🏢"},
    "interview": {"name": "面试经验", "prompt": PROMPT_INTERVIEW, "icon": "📝"},
    "hiring": {"name": "招聘动态", "prompt": PROMPT_HIRING, "icon": "📈"},
}


def _call_llm(prompt_text: str, api_key: str, model: str, base_url: str) -> dict:
    """Call DeepSeek API with web_search enabled. Retries on 503."""
    import requests

    for attempt in range(3):
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是求职顾问。先搜索网络，再基于搜索结果回答。只输出要求的JSON格式。"},
                    {"role": "user", "content": prompt_text},
                ],
                "temperature": 0.3,
                "enable_search": True,
            },
            timeout=60,
        )
        if resp.status_code == 503:
            wait = 2 ** attempt
            print(f"[LLM] 503, retry in {wait}s (attempt {attempt+1}/3)")
            import time as _time
            _time.sleep(wait)
            continue
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(content)

    raise Exception("DeepSeek API returned 503 after 3 retries")


def _extract_json(text: str) -> dict:
    """Extract JSON from model response, handling markdown code blocks."""
    import re
    # Try to find JSON in ```json ... ``` blocks
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        text = m.group(1)
    # Find first { ... } block
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return {"summary": text[:200], "data_quality": "insufficient", "details": [], "sources": []}


def analyze_company(
    company_name: str,
    api_key: str = None,
    model: str = None,
    base_url: str = None,
) -> dict:
    """V3: 5 parallel DeepSeek calls with web_search, no Bing scraping needed."""
    api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    model = model or os.getenv("OPENAI_MODEL", "deepseek-chat")
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

    if not api_key:
        return {
            "analysis": {},
            "model": "none",
            "analysis_time": 0,
            "note": "未配置 API 密钥。在 .env 中设置 OPENAI_API_KEY。",
        }

    # ── Sequential LLM calls (avoid rate limits on web_search) ──
    start = time.time()
    analysis = {}
    errors = []
    dim_order = ["company_overview", "salary", "culture", "interview", "hiring"]

    for dim_key in dim_order:
        prompt = DIMENSIONS[dim_key]["prompt"].format(company=company_name)
        try:
            result = _call_llm(prompt, api_key, model, base_url)
            analysis[dim_key] = result
            # Small delay to avoid rate limits
            time.sleep(0.5)
        except Exception as e:
            print(f"[Analyzer] '{dim_key}' error: {e}")
            analysis[dim_key] = {
                "summary": f"分析失败",
                "data_quality": "insufficient",
                "details": [],
                "sources": [],
            }
            errors.append(dim_key)

    elapsed = time.time() - start
    print(f"[Analyzer] ✓ {company_name}: 5 dims in {elapsed:.1f}s"
          + (f" (errors: {errors})" if errors else ""))

    return {
        "analysis": analysis,
        "model": model,
        "analysis_time": round(elapsed, 2),
        "errors": errors,
    }


# ═══════════════════════════════════════════════════
#  HTML Formatting (unchanged)
# ═══════════════════════════════════════════════════

def format_analysis_html(analysis_data: dict) -> str:
    if not analysis_data or "analysis" not in analysis_data:
        return "<p class='error-msg'>无法生成分析报告</p>"

    a = analysis_data["analysis"]
    html_parts = [_render_overview_card(a.get("company_overview", {}))]
    html_parts.append('<div class="analysis-grid">')
    for dim_key in ["salary", "culture", "interview", "hiring"]:
        dim = DIMENSIONS[dim_key]
        data = a.get(dim_key, {})
        html_parts.append(_render_card(dim_key, dim["icon"], dim["name"], data))
    html_parts.append("</div>")
    return "\n".join(html_parts)


def _render_overview_card(data: dict) -> str:
    name = _e(data.get("name", ""))
    summary = _e(data.get("summary", ""))
    tags = data.get("tags", [])
    risk_level = data.get("risk_level", "low")
    risk_flags = data.get("risk_flags", [])
    details = data.get("details", [])
    data_quality = data.get("data_quality", "limited")
    sources = data.get("sources", [])

    risk_class = {"low": "risk-low", "medium": "risk-medium", "high": "risk-high"}.get(risk_level, "risk-low")
    risk_label = {"low": "✅ 低风险", "medium": "⚠️ 注意", "high": "🚨 高风险"}.get(risk_level, "✅ 低风险")

    tags_html = " ".join(f'<span class="tag">{_e(t)}</span>' for t in tags)
    flags_html = " ".join(f'<span class="risk-flag">{_e(f)}</span>' for f in risk_flags)
    details_html = "".join(f"<li>{_e(d)}</li>" for d in details)
    quality_note = ""
    if data_quality in ("limited", "insufficient"):
        quality_note = '<span class="quality-note">' + ("⚠️ 信息有限" if data_quality == "limited" else "⚠️ 信息不足") + "</span>"

    return f"""
<div class="overview-card {risk_class}">
  <div class="overview-header">
    <h2>⚡ {name or "公司速览"}</h2>
    <span class="risk-badge">{risk_label}</span>
    {quality_note}
  </div>
  <p class="overview-summary">{summary}</p>
  {('<div class="tags">' + tags_html + '</div>') if tags else ''}
  {('<div class="risk-flags">' + flags_html + '</div>') if risk_flags else ''}
  {('<ul class="card-list">' + details_html + '</ul>') if details else ''}
  {_render_sources(sources)}
</div>"""


def _render_card(dim_key: str, icon: str, title: str, data: dict) -> str:
    summary = _e(data.get("summary", ""))
    details = data.get("details", [])
    data_quality = data.get("data_quality", "limited")
    sources = data.get("sources", [])

    extra_html = ""
    if dim_key == "salary":
        roles = data.get("roles", [])
        if roles:
            rows = "".join(
                f'<tr><td>{_e(r.get("role",""))}</td><td>{_e(r.get("range",""))}</td><td class="src-tag">{_e(r.get("source",""))}</td></tr>'
                for r in roles
            )
            extra_html += (
                '<table class="salary-table"><thead><tr><th>岗位</th><th>薪资范围</th><th>来源</th></tr></thead>'
                f'<tbody>{rows}</tbody></table>'
            )
        mc = _e(data.get("market_compare", ""))
        if mc:
            extra_html += f'<p class="market-compare">📊 {mc}</p>'
    elif dim_key == "culture":
        sentiment = data.get("sentiment", "unknown")
        sent_label = {"positive": "🟢 正面", "mixed": "🟡 褒贬不一", "negative": "🔴 负面", "unknown": "⚪ 信息不足"}.get(sentiment, "⚪ 信息不足")
        extra_html += f'<p class="sentiment">{sent_label}</p>'
        keywords = data.get("keywords", [])
        if keywords:
            extra_html += "<div class='keywords'>" + " ".join(f'<span class="kw">{_e(k)}</span>' for k in keywords) + "</div>"
        pos = data.get("positive", [])
        neg = data.get("negative", [])
        if pos:
            extra_html += '<div class="pros-cons pro">👍 ' + "；".join(_e(p) for p in pos) + "</div>"
        if neg:
            extra_html += '<div class="pros-cons con">👎 ' + "；".join(_e(n) for n in neg) + "</div>"
    elif dim_key == "interview":
        difficulty = data.get("difficulty", "unknown")
        diff_label = {"easy": "🟢 容易", "medium": "🟡 中等", "hard": "🔴 困难", "unknown": "⚪ 未知"}.get(difficulty, "⚪ 未知")
        extra_html += f'<p class="difficulty">难度：{diff_label}</p>'
        process = data.get("process", [])
        if process:
            extra_html += '<div class="interview-process"><strong>面试流程：</strong><ol>' + "".join(f"<li>{_e(s)}</li>" for s in process) + "</ol></div>"
        questions = data.get("common_questions", [])
        if questions:
            extra_html += '<div class="job-tips"><strong>❓ 常见题：</strong><ul>' + "".join(f"<li>{_e(q)}</li>" for q in questions[:5]) + "</ul></div>"
        tips = data.get("tips", [])
        if tips:
            extra_html += '<div class="job-tips"><strong>💡 建议：</strong><ul>' + "".join(f"<li>{_e(t)}</li>" for t in tips) + "</ul></div>"
    elif dim_key == "hiring":
        trend = data.get("trend", "unknown")
        trend_label = {"expanding": "📈 扩张中", "stable": "➡️ 稳定", "shrinking": "📉 收缩中", "unknown": "⚪ 未知"}.get(trend, "⚪ 未知")
        extra_html += f'<p class="trend">{trend_label}</p>'
        openings = _e(data.get("openings_estimate", ""))
        if openings:
            extra_html += f'<p class="openings">在招岗位：{openings}</p>'
        hot_roles = data.get("hot_roles", [])
        if hot_roles:
            extra_html += "<div class='hot-roles'>" + " ".join(f'<span class="role-tag">{_e(r)}</span>' for r in hot_roles) + "</div>"

    details_html = "".join(f"<li>{_e(d)}</li>" for d in details)
    quality_note = ""
    if data_quality in ("limited", "insufficient"):
        quality_note = '<span class="quality-note">' + ("⚠️ 信息有限" if data_quality == "limited" else "⚠️ 信息不足") + "</span>"

    return f"""
<div class="analysis-card">
  <div class="card-header">
    <h3>{icon} {title}</h3>
    {quality_note}
  </div>
  <p class="card-summary">{summary}</p>
  {extra_html}
  {('<ul class="card-list">' + details_html + '</ul>') if details else ''}
  {_render_sources(sources)}
</div>"""


def _render_sources(sources: list) -> str:
    if not sources:
        return '<div class="sources-inline">📎 无具体来源</div>'
    items = " · ".join(_e(s[:60]) for s in sources[:3])
    return f'<div class="sources-inline">📎 信源：{items}</div>'


def _e(text) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
