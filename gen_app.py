import os, sys, json, time
sys.stdout.reconfigure(encoding="utf-8")

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from searcher import multi_query_search, search_web, fetch_page_content
from analyzer import analyze_company, format_analysis_html

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json()
    company_name = data.get("company", "").strip()
    if not company_name:
        return jsonify({"error": "请输入企业名称"}), 400

    try:
        # Step 1: Search
        print(f"[API] Searching for: {company_name}")
        search_results = multi_query_search(company_name)

        if not search_results:
            return jsonify({"error": f"未找到关于「{company_name}」的相关信息，请尝试其他企业名称"}), 404

        # Step 2: Fetch detailed content for top results
        print(f"[API] Fetching detailed content...")
        for r in search_results[:5]:
            if r.get("link"):
                content = fetch_page_content(r["link"])
                if content:
                    r["page_content"] = content[:2000]

        # Step 3: Analyze
        print(f"[API] Analyzing...")
        analysis = analyze_company(company_name, search_results)

        # Step 4: Format HTML
        analysis_html = format_analysis_html(analysis)

        result = {
            "company": company_name,
            "search_results": [
                {"title": r["title"], "snippet": r.get("snippet", ""), "link": r.get("link", ""), "query_type": r.get("query_type", "")}
                for r in search_results[:15]
            ],
            "analysis": analysis.get("analysis", {}),
            "analysis_html": analysis_html,
            "model": analysis.get("model", "unknown"),
            "search_count": len(search_results),
            "structured": analysis.get("structured", False)
        }

        return jsonify(result)

    except Exception as e:
        print(f"[API] Error: {e}")
        return jsonify({"error": f"分析过程发生错误：{str(e)}"}), 500


@app.route("/api/search_status", methods=["POST"])
def api_search_status():
    """Simple search-only endpoint for progress display."""
    data = request.get_json()
    company_name = data.get("company", "").strip()
    if not company_name:
        return jsonify({"error": "请输入企业名称"}), 400

    results = multi_query_search(company_name)
    return jsonify({
        "company": company_name,
        "count": len(results),
        "results": results[:20]
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    print(f"[App] Starting server on port {port}, debug={debug}")
    app.run(host="0.0.0.0", port=port, debug=debug)
