"""
V2.2 Searcher: intitle-based with safe keywords only.

Bing Chinese tokenizer limitation: for company names containing common
characters (e.g. 米哈游), Bing splits into sub-words when combined with
certain keywords (评价, 加班, 面试). Only "safe" keywords work: 公司, 招聘,
工资, 待遇, 融资, 上市, 估值, 裁员.

Strategy:
- Use intitle: with safe keywords for overview/hiring
- Use site: for culture (maimai.cn works)
- Use intitle: with safe keywords + let fallback/LLM extract dimension info
"""
import requests
from bs4 import BeautifulSoup
import time
import os
import certifi
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

_cache: dict = {}
CACHE_TTL = 86400


def cache_key(company_name: str) -> str:
    return hashlib.md5(company_name.strip().lower().encode()).hexdigest()


def cache_get(company_name: str):
    key = cache_key(company_name)
    if key in _cache:
        entry = _cache[key]
        if time.time() - entry["ts"] < CACHE_TTL:
            return entry["data"]
        del _cache[key]
    return None


def cache_set(company_name: str, data):
    _cache[cache_key(company_name)] = {"ts": time.time(), "data": data}


# ── Query groups (safe keywords only) ──────────────
# All queries use intitle: or site: with no extra keywords
# to avoid Bing's Chinese tokenizer from splitting company names.
QUERY_GROUPS = {
    "company_overview": [
        "intitle:{company} 公司",
        "intitle:{company} 融资 OR 上市 OR 估值 OR 裁员",
    ],
    "salary": [
        "intitle:{company} 工资 OR 待遇 OR 薪资",
    ],
    "culture": [
        "site:maimai.cn {company}",
    ],
    "interview": [
        "intitle:{company} 面试 OR 面经 OR 笔试",
    ],
    "hiring": [
        "intitle:{company} 招聘",
        "intitle:{company} 校招 OR 社招",
    ],
}


def search_web(query: str, num_results: int = 5, timeout: int = 10) -> list:
    """Search Bing. Returns list of {title, snippet, link}."""
    results = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "setmkt": "zh-CN", "count": num_results},
            headers=headers,
            timeout=timeout,
            verify=certifi.where(),
        )
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for li in soup.select("li.b_algo")[:num_results]:
            title_el = li.select_one("h2 a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            snippet_el = li.select_one(".b_caption p") or li.select_one("p")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            if title and href:
                results.append({"title": title, "snippet": snippet, "link": href})
    except Exception as e:
        print(f"[Search] {query[:55]:<55} → {e}")
    return results


def multi_query_search(company_name: str, delay: float = 0.15) -> dict:
    """Parallel search with staggered workers to avoid rate limits."""
    cached = cache_get(company_name)
    if cached is not None:
        print(f"[Search] ✓ Cache HIT: {company_name}")
        return cached

    print(f"[Search] → {company_name}")
    start = time.time()

    all_queries: list[tuple[str, str]] = []
    for dim, templates in QUERY_GROUPS.items():
        for tpl in templates:
            all_queries.append((dim, tpl.format(company=company_name)))

    all_results = []
    seen_urls = set()

    def _search_one(dim: str, query: str, stagger: float = 0):
        if stagger:
            time.sleep(stagger)
        results = []
        for r in search_web(query):
            url = r.get("link", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                r["dimension"] = dim
                results.append(r)
        return results

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for i, (dim, q) in enumerate(all_queries):
            futures[executor.submit(_search_one, dim, q, (i % 4) * delay)] = (dim, q)

        for future in as_completed(futures):
            try:
                batch = future.result(timeout=15)
                all_results.extend(batch)
            except Exception as e:
                dim, q = futures[future]
                print(f"[Search] Failed: [{dim}] {q[:50]} — {e}")

    priority = {"company_overview": 0, "salary": 1, "culture": 2, "interview": 3, "hiring": 4}
    all_results.sort(key=lambda r: priority.get(r.get("dimension", ""), 99))

    elapsed = time.time() - start
    result = {
        "company": company_name,
        "results": all_results,
        "count": len(all_results),
        "search_time": round(elapsed, 2),
    }

    if len(all_results) >= 3:
        cache_set(company_name, result)

    types = {}
    for r in all_results:
        d = r.get("dimension", "?")
        types[d] = types.get(d, 0) + 1
    print(f"[Search] ✓ {company_name}: {len(all_results)} results ({types}) in {elapsed:.1f}s")

    return result


def fetch_page_content(url: str, timeout: int = 8) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [ln for ln in text.split("\n") if len(ln) > 20]
        return "\n".join(lines[:80])
    except Exception:
        return ""
