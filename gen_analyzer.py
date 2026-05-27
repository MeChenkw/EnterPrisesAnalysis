import os, sys, json
sys.stdout.reconfigure(encoding="utf-8")

ANALYSIS_SYSTEM_PROMPT = """你是一位资深商业分析师与企业调研专家。你的任务是根据搜索到的互联网信息，对企业进行全面、客观、结构化的分析。

请从以下5个维度进行分析，每个维度用2-4个要点概括：

## 1. 业务范围（Business Scope）
- 公司主营业务、所属行业
- 商业模式与核心价值
- 企业规模、成立时间、总部地点等基本信息

## 2. 主要客户（Main Customers）
- 目标客户群体（B端/C端）
- 典型客户案例或合作方
- 客户分布（行业/地域）

## 3. 核心产品与竞品（Core Products & Competitors）
- 核心产品/服务名称与特点
- 主要竞争对手
- 竞争优势与差异化

## 4. 近3年经营情况（Recent 3 Years Operations）
- 营收趋势、利润情况（如有数据）
- 重大发展事件（融资、上市、并购、战略调整等）
- 市场表现与行业地位变化
- 如果公开数据有限，请基于搜索到的线索进行合理推断并注明

## 5. 员工评价与应聘建议（Employee Reviews & Job Advice）
- 员工口碑（工作氛围、管理风格）
- 薪资福利水平
- 职业发展空间
- 应聘注意事项（面试风格、文化匹配等）

请以JSON格式输出，严格按照以下结构：
{
  "business_scope": {"summary": "...", "details": ["...", "..."]},
  "main_customers": {"summary": "...", "details": ["...", "..."]},
  "core_products": {"summary": "...", "details": ["...", "..."], "competitors": ["...", "..."]},
  "recent_operations": {"summary": "...", "details": ["...", "..."]},
  "employee_reviews": {"summary": "...", "details": ["...", "..."], "job_tips": ["...", "..."]},
  "overall_assessment": "..."
}

注意：
- 只输出合法的JSON，不要包含其他文字
- 如果某个维度的信息不足，请如实说明信息有限并给出合理推断
- 每个details列表至少包含2-3条
- 使用中文回答
"""

def analyze_company(company_name, search_results, api_key=None, model=None, base_url=None):
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        return _fallback_analysis(company_name, search_results)

    context = _build_context(company_name, search_results)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        content = resp.choices[0].message.content
        parsed = json.loads(content)
        return {"analysis": parsed, "model": model, "structured": True}
    except Exception as e:
        print(f"[Analyzer] AI analysis error: {e}")
        return _fallback_analysis(company_name, search_results)


def _build_context(company_name, search_results):
    lines = [f"请对以下公司进行全面分析：{company_name}\n"]
    lines.append("=== 搜索结果 ===\n")
    for i, r in enumerate(search_results, 1):
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        query_type = r.get("query_type", "general")
        lines.append(f"[{i}] ({query_type}) {title}")
        if snippet:
            lines.append(f"    摘要: {snippet[:300]}")
        lines.append("")
    return "\n".join(lines)


def _fallback_analysis(company_name, search_results):
    overviews, products_list, customers, financials, employees = [], [], [], [], []
    for r in search_results:
        qt = r.get("query_type", "")
        t = r.get("title", "") + " " + r.get("snippet", "")
        if qt == "overview":
            overviews.append(t[:200])
        elif qt == "products":
            products_list.append(t[:200])
        elif qt == "customers":
            customers.append(t[:200])
        elif qt == "financial":
            financials.append(t[:200])
        elif qt == "employee":
            employees.append(t[:200])
        else:
            overviews.append(t[:200])

    return {
        "analysis": {
            "business_scope": {"summary": f"基于搜索到的{len(overviews)}条摘要信息", "details": overviews[:3]},
            "main_customers": {"summary": "以下为搜索到的相关信息", "details": customers[:3] if customers else ["信息有限，建议进一步搜索"]},
            "core_products": {"summary": "搜索到的产品与竞品信息", "details": products_list[:3] if products_list else ["信息有限"], "competitors": []},
            "recent_operations": {"summary": "近况相关信息", "details": financials[:3] if financials else ["信息有限"]},
            "employee_reviews": {"summary": "员工评价相关信息", "details": employees[:3] if employees else ["信息有限"], "job_tips": ["建议查阅招聘网站获取更多信息"]},
            "overall_assessment": f"{company_name}的分析基于搜索结果摘要，如需更深入的分析请配置OPENAI_API_KEY。"
        },
        "model": "rule-based-fallback",
        "structured": True,
        "note": "未配置API密钥，使用规则提取作为后备方案"
    }


def format_analysis_html(analysis_data):
    if not analysis_data or "analysis" not in analysis_data:
        return "<p>无法生成分析结果</p>"
    a = analysis_data["analysis"]
    sections = {
        "business_scope": ("业务范围", "briefcase"),
        "main_customers": ("主要客户", "people"),
        "core_products": ("核心产品与竞品分析", "cube"),
        "recent_operations": ("近3年经营情况", "chart"),
        "employee_reviews": ("员工评价与应聘建议", "star"),
    }
    html = ""
    for key, (title, icon_name) in sections.items():
        section = a.get(key, {})
        if not section:
            continue
        summary = section.get("summary", "")
        details = section.get("details", [])
        html += f"<div class='analysis-card'>"
        html += f"<div class='card-header'><h3>{_e(title)}</h3></div>"
        if summary:
            html += f"<p class='card-summary'>{_e(summary)}</p>"
        if details:
            html += "<ul class='card-list'>"
            for d in details:
                html += f"<li>{_e(d)}</li>"
            html += "</ul>"
        if key == "core_products" and section.get("competitors"):
            comp_list = ", ".join(section["competitors"])
            html += f"<div class='competitors'><strong>主要竞争对手：</strong>{_e(comp_list)}</div>"
        if key == "employee_reviews" and section.get("job_tips"):
            html += "<div class='job-tips'><strong>应聘建议：</strong><ul>"
            for tip in section["job_tips"]:
                html += f"<li>{_e(tip)}</li>"
            html += "</ul></div>"
        html += "</div>"
    overall = a.get("overall_assessment", "")
    if overall:
        html += f"<div class='analysis-card overall'><div class='card-header'><h3>综合评价</h3></div><p class='card-summary'>{_e(overall)}</p></div>"
    return html


def _e(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

