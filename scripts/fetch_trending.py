"""Fetch GitHub daily trending, filter AI-related repos, generate a Top-10 markdown report.

Stdlib only (urllib + re) — no third-party dependencies.
"""
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from html import unescape

CST = timezone(timedelta(hours=8))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
TRENDING_URL = "https://github.com/trending?since=daily"

WORD_KEYWORDS = ["ai", "llm", "llms", "ml", "nlp", "gpt", "rag", "mcp", "agi", "ocr", "asr", "tts"]
PHRASE_KEYWORDS = [
    "agent", "agentic", "machine learning", "deep learning", "neural",
    "diffusion", "transformer", "chatbot", "copilot", "claude", "gemini", "openai",
    "anthropic", "embedding", "inference", "fine-tun", "prompt", "langchain",
    "llama", "mistral", "generative", "computer-use", "multimodal", "large language",
    "language model", "foundation model", "stable diffusion", "knowledge graph",
    "quantiz", "autogen", "vector search", "vision", "robot",
]


def is_ai_related(text: str):
    t = text.lower()
    hits = []
    for kw in WORD_KEYWORDS:
        if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", t):
            hits.append(kw)
    for kw in PHRASE_KEYWORDS:
        if kw in t:
            hits.append(kw)
    return hits


def strip_tags(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_trending(html: str):
    repos = []
    # trending 页每个仓库是一个 <article class="Box-row"> ... </article>
    chunks = re.split(r'<article\s+class="Box-row"', html)[1:]
    for chunk in chunks:
        m_name = re.search(r'<h2[^>]*>\s*(?:<[^a][^>]*>\s*)*<a[^>]*href="/([^"]+)"', chunk)
        if not m_name:
            m_name = re.search(r'<a[^>]*href="/([^"]+?)"[^>]*data-view-component', chunk)
        if not m_name:
            continue
        full_name = m_name.group(1).strip("/")

        m_desc = re.search(r'<p\s+class="col-9[^"]*"[^>]*>(.*?)</p>', chunk, re.S)
        desc = strip_tags(m_desc.group(1)) if m_desc else ""

        m_lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', chunk)
        lang = m_lang.group(1).strip() if m_lang else ""

        m_stars = re.search(r'href="/[^"]+/stargazers"[^>]*>(.*?)</a>', chunk, re.S)
        stars = re.sub(r"\D", "", strip_tags(m_stars.group(1))) if m_stars else ""

        m_today = re.search(r'class="d-inline-block float-sm-right"[^>]*>(.*?)</span>', chunk, re.S)
        stars_today = ""
        if m_today:
            m_num = re.search(r"([\d,]+)", strip_tags(m_today.group(1)))
            stars_today = re.sub(r"\D", "", m_num.group(1)) if m_num else ""

        repos.append({
            "full_name": full_name, "desc": desc, "lang": lang,
            "stars": stars, "stars_today": stars_today,
        })
    return repos


def main():
    today = datetime.now(CST).strftime("%Y-%m-%d")
    req = urllib.request.Request(TRENDING_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    repos = parse_trending(html)
    if len(repos) < 5:
        print(f"ERROR: only parsed {len(repos)} repos, trending page layout may have changed", file=sys.stderr)
        sys.exit(1)

    scored = []
    for r in repos:
        hits = is_ai_related(f"{r['full_name']} {r['desc']}")
        if hits:
            r["hits"] = hits
            scored.append(r)
    scored.sort(key=lambda r: int(r["stars_today"] or 0), reverse=True)
    top10 = scored[:10]

    lines = [
        f"# GitHub AI 热门项目 Top 10（{today}）",
        "",
        f"> 自动生成于 {datetime.now(CST).strftime('%Y-%m-%d %H:%M')} CST ｜ 数据源：GitHub Trending（daily）｜ 口径：按当日新增 star 排序，关键词筛选 AI 相关项目",
        "",
    ]
    for i, r in enumerate(top10, 1):
        st = f"{int(r['stars_today']):,}" if r["stars_today"] else "—"
        total = f"{int(r['stars']):,}" if r["stars"] else "—"
        lines += [
            f"## {i}. [{r['full_name']}](https://github.com/{r['full_name']}) — 今日 +{st} ⭐（总 {total}）",
            f"- 语言：{r['lang'] or '—'}",
            f"- 简介：{r['desc'] or '—'}",
            f"- AI 命中关键词：{', '.join(dict.fromkeys(r['hits']))}",
            "",
        ]
    others = scored[10:15]
    if others:
        lines += ["## 其他上榜 AI 项目（11-15）", ""]
        for r in others:
            lines.append(f"- [{r['full_name']}](https://github.com/{r['full_name']}) +{r['stars_today']} ⭐ — {r['desc'][:80]}")
        lines.append("")
    lines += ["## 今日趋势观察", "", f"- 今日 Trending 全榜共解析 {len(repos)} 个仓库，其中关键词命中 AI 相关的 {len(scored)} 个。"]

    report_path = f"reports/github-ai-trending-{today}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # 更新 README 索引
    try:
        with open("README.md", encoding="utf-8") as f:
            readme = f.read()
    except FileNotFoundError:
        readme = "# GitHub AI Daily Trending\n\n每天 10:00（北京时间）自动汇总 GitHub 上 AI 相关的热门项目 Top 10。\n\n## 历史报告\n"
    marker = "## 历史报告\n"
    entry = f"- [{today}](reports/github-ai-trending-{today}.md)"
    if marker in readme:
        head, tail = readme.split(marker, 1)
        old_entries = [l for l in tail.strip().splitlines() if l.strip()]
        if entry not in old_entries:
            old_entries.insert(0, entry)
        readme = head + marker + "\n".join(old_entries[:90]) + "\n"
    else:
        readme += "\n" + entry + "\n"
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"OK: {len(scored)}/{len(repos)} repos AI-related, report -> {report_path}")
    for i, r in enumerate(top10, 1):
        print(f"  {i}. {r['full_name']} (+{r['stars_today']})")


if __name__ == "__main__":
    main()
