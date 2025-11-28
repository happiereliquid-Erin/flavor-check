from flask import Flask, request, render_template_string, send_file
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import csv
import io
from nltk.stem import PorterStemmer

app = Flask(__name__)

# 电子烟常用风味关键词及类别
VAPE_FLAVOR_KEYWORDS = {
    "mango":"fruit","peach":"fruit","pineapple":"fruit","grapefruit":"fruit","orange":"fruit",
    "lemon":"fruit","lime":"fruit","kiwi":"fruit","apple":"fruit","pear":"fruit",
    "blueberry":"fruit","blackberry":"fruit","blackcurrant":"fruit","strawberry":"fruit",
    "raspberry":"fruit","cherry":"fruit","grape":"fruit","watermelon":"fruit","guava":"fruit",
    "lychee":"fruit","banana":"fruit","coconut":"fruit","dragonfruit":"fruit","passion":"fruit",
    "melon":"fruit",
    "ice":"cool","cool":"cool","menthol":"cool","mint":"cool","fresh":"cool","icy":"cool","cold":"cool",
    "sweet":"sweet","sour":"sweet","tart":"sweet","creamy":"creamy","smooth":"creamy","rich":"creamy",
    "cola":"other","coffee":"other","caramel":"sweet","vanilla":"sweet","biscuit":"creamy",
    "cookie":"creamy","donut":"creamy","yogurt":"creamy","milk":"creamy","cream":"creamy",
    "tobacco":"tobacco","custard":"creamy","energy":"other","bull":"other",
    "gummy":"sweet","candy":"sweet","fruit":"fruit"
}

# 词干处理
stemmer = PorterStemmer()
VAPE_STEM_MAP = {stemmer.stem(k): (k, VAPE_FLAVOR_KEYWORDS[k]) for k in VAPE_FLAVOR_KEYWORDS}

last_csv = None

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

                # BFS全站搜索产品页
                while to_visit:
                    current = to_visit.pop()
                    visited.add(current)

                    r = requests.get(current, timeout=8)
                    soup = BeautifulSoup(r.text, "html.parser")

                    # 判断页面是否包含目标口味
                    if flavor_lower in soup.get_text(" ", strip=True).lower():
                        desc = extract_description(soup)
                        if desc:
                            found_description = desc
                            source_url = current
                            break

                    # 扫描可能的产品/集合链接
                    for a in soup.find_all("a"):
                        href = a.get("href")
                        if not href:
                            continue
                        full = urljoin(base + "/", href)
                        if full.startswith(base) and full not in visited and any(k in full for k in ["product","collection","flavour","liquid","shop"]):
                            to_visit.add(full)

                # 如果找不到产品页，尝试搜索页面
                if not found_description:
                    search_url = f"{base}/search?q={flavor.replace(' ', '+')}"
                    try:
                        r = requests.get(search_url, timeout=8)
                        soup = BeautifulSoup(r.text, "html.parser")
                        first_product = soup.select_one("a[href*='/product/']")
                        if first_product:
                            full = urljoin(base + "/", first_product['href'])
                            r2 = requests.get(full, timeout=8)
                            soup2 = BeautifulSoup(r2.text, "html.parser")
                            desc = extract_description(soup2)
                            if desc:
                                found_description = desc
                                source_url = full
                    except:
                        pass

                if found_description:
                    break

            except:
                continue

        # 提取关键词
        keywords = extract_keywords(found_description)

        results.append({
            "flavor": flavor,
            "description": found_description or "❌ 未找到描述",
            "keywords": ", ".join([k[0] for k in keywords]),
            "categories": ", ".join([k[1] for k in keywords]),
            "source": source_url or "N/A"
        })

    # CSV生成
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=["Flavor","Description","Keywords","Categories","Source"])
    writer.writeheader()
    for r in results:
        writer.writerow(r)
    csv_buffer.seek(0)

    global last_csv
    last_csv = csv_buffer

    html = """
    <h2>爬取结果</h2>
    <a href="/download_csv">⬇ 下载 CSV</a><br><br>
    {% for r in results %}
        <h3>{{r.flavor}}</h3>
        <p><b>描述：</b>{{r.description}}</p>
        <p><b>关键词：</b>{{r.keywords}}</p>
        <p><b>类别：</b>{{r.categories}}</p>
        <p><b>来源：</b>{{r.source}}</p>
        <hr>
    {% endfor %}
    """
    return render_template_string(html, results=results)


@app.route("/download_csv")
def download_csv():
    global last_csv
    if not last_csv:
        return "没有可下载的 CSV"
    last_csv.seek(0)
    return send_file(io.BytesIO(last_csv.getvalue().encode("utf-8")),
                     mimetype="text/csv",
                     as_attachment=True,
                     download_name="flavor_results.csv")


def extract_description(soup):
    # meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"]

    # 常用描述 div
    for cls in ["description","product-description","product_desc","desc","detail"]:
        tag = soup.find("div", class_=lambda c: c and cls in c.lower())
        if tag:
            text = tag.get_text(" ", strip=True)
            if len(text) > 40:
                return text

    # 长段落 p
    for p in soup.find_all("p"):
        t = p.get_text(" ", strip=True)
        if len(t) > 60:
            return t

    return None


def extract_keywords(description):
    if not description:
        return []
    text = description.lower()
    words = re.findall(r'\b\w+\b', text)
    found = set()
    for w in words:
        stem = stemmer.stem(w)
        if stem in VAPE_STEM_MAP:
            found.add(VAPE_STEM_MAP[stem])
    return list(found)


if __name__ == "__main__":
    app.run(debug=True)
