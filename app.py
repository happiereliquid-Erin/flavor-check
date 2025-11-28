from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

app = Flask(__name__)

# 专业电子烟常见风味关键词
VAPE_FLAVOR_KEYWORDS = [
    "mango","peach","pineapple","grapefruit","orange","lemon","lime","kiwi","apple","pear",
    "blueberry","blackberry","blackcurrant","strawberry","raspberry","cherry","grape",
    "watermelon","guava","lychee","banana","coconut","dragonfruit","passion","melon",
    "ice","cool","menthol","mint","fresh","icy","cold",
    "sweet","sour","tart","creamy","smooth","rich",
    "cola","coffee","caramel","vanilla","biscuit","cookie","donut","yogurt","milk","cream",
    "tobacco","custard","energy","bull",
    "gummy","candy","fruit"
]

@app.route("/", methods=["GET"])
def index():
    return open("index.html", encoding="utf-8").read()


@app.route("/scrape", methods=["POST"])
def scrape():
    urls = [u.strip().rstrip("/") for u in request.form["urls"].splitlines() if u.strip()]
    brand = request.form["brand"].strip()
    flavors = [f.strip() for f in request.form["flavors"].splitlines() if f.strip()]

    results = []

    for flavor in flavors:
        flavor_lower = flavor.lower()
        found_description = None
        source_url = None

        for base in urls:
            try:
                visited = set()
                to_visit = {base}

                # 全站 BFS 搜索
                while to_visit:
                    current = to_visit.pop()
                    visited.add(current)

                    r = requests.get(current, timeout=8)
                    soup = BeautifulSoup(r.text, "html.parser")

                    # 先检查页面是否有口味名称
                    if flavor_lower in soup.get_text(" ", strip=True).lower():
                        desc = extract_description(soup)
                        if desc:
                            found_description = desc
                            source_url = current
                            break

                    # 扫描所有链接继续爬
                    for a in soup.find_all("a"):
                        href = a.get("href")
                        if not href:
                            continue

                        full = urljoin(base + "/", href)

                        if full.startswith(base) and full not in visited and any(k in full for k in ["product","collection","flavour","liquid","shop"]):
                            to_visit.add(full)

                if found_description:
                    break

            except Exception:
                continue

        # 关键词提取（按行业关键词匹配）
        keywords = extract_keywords(found_description)

        results.append({
            "flavor": flavor,
            "description": found_description or "❌ 未找到描述",
            "keywords": ", ".join(keywords),
            "source": source_url or "N/A"
        })

    # 输出
    html = """
    <h2>爬取结果</h2>
    {% for r in results %}
        <h3>{{r.flavor}}</h3>
        <p><b>描述：</b>{{r.description}}</p>
        <p><b>关键词：</b>{{r.keywords}}</p>
        <p><b>来源：</b>{{r.source}}</p>
        <hr>
    {% endfor %}
    """
    return render_template_string(html, results=results)


def extract_description(soup):
    # 1. meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"]

    # 2. 常见描述类 div
    for cls in ["description", "product-description", "product_desc", "desc", "detail"]:
        tag = soup.find("div", class_=lambda c: c and cls in c.lower())
        if tag:
            text = tag.get_text(" ", strip=True)
            if len(text) > 40:
                return text

    # 3. 找长段落
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if len(t) > 60:
            return t

    return None


def extract_keywords(description):
    if not description:
        return []

    text = description.lower()

    found = [k for k in VAPE_FLAVOR_KEYWORDS if k in text]

    return found


if __name__ == "__main__":
    app.run(debug=True)
