"""
V3 App: DeepSeek web_search — no Bing scraping needed.
"""
import os, sys, json, time

for k in list(os.environ.keys()):
    if 'proxy' in k.lower():
        del os.environ[k]

sys.stdout.reconfigure(encoding="utf-8")

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from analyzer import analyze_company, format_analysis_html

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "v3-secret")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """V3: 5 parallel DeepSeek calls with web_search."""
    data = request.get_json()
    company_name = (data.get("company", "") or "").strip()
    if not company_name:
        return jsonify({"error": "请输入企业名称"}), 400

    t0 = time.time()
    try:
        print(f"\n{'='*60}")
        print(f"[API] 🔍 {company_name}")

        analysis_data = analyze_company(company_name)
        analysis_html = format_analysis_html(analysis_data)

        total_time = round(time.time() - t0, 2)
        print(f"[API] ✅ {company_name} done in {total_time}s")

        return jsonify({
            "company": company_name,
            "total_time": total_time,
            "model": analysis_data.get("model", "unknown"),
            "analysis": analysis_data.get("analysis", {}),
            "analysis_html": analysis_html,
            "errors": analysis_data.get("errors", []),
            "note": analysis_data.get("note", ""),
        })

    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        import traceback, sys
        err_detail = traceback.format_exc()
        sys.stderr.write(f"[API] ❌ Error after {elapsed}s: {e}\n{err_detail}\n")
        sys.stderr.flush()
        # Never return HTML — always JSON even in debug mode
        return jsonify({"error": f"分析失败：{str(e)}"}), 500


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "3.0"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    print(f"[App] V3 (web_search) starting on :{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
