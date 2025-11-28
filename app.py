from flask import Flask, request, render_template_string
import requests
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
import re

app = Flask(__name__)

# 显示界面
@app.route("/", methods=["GET"])
def index():
    return open("index.html", encoding="utf-8").read()

# 主爬虫逻辑
@app.route("/scrape", methods=["POST"])
def scrape():
    urls = request.form["urls"].splitlines()
    brand = request.form["brand"].strip()
    flavors = request.form["flavors"].splitlines()

    results = []

    for flavor in flavors:
        flavor_lower = flavor.lower().strip()
        found_description = None
        source_url = None

        # 遍历所有网址寻找匹配页面
        for base in urls:
            base = base.strip().rstrip("/")
            try:
                # 避免无效网址
                if not base.startswith("http"):
                    continue

                r = requests.get(base, timeout=8)
                soup = BeautifulSoup(r.text, "html.parser")

                # 尝试查找所有链接，匹配品牌和口味
                links = soup.find_all("a")
                for a in links:
                    href = a.get("href")
                    if not href:
                        continue

                    text = (a.text or "").lower()

                    if flavor_lower in text or flavor_lower.replace(" ", "-") in href.lower():
                        # 构造完整 URL
                        if href.startswith("http"):
                            product_url = href
                        else:
                            product_url = base + "/" + href.lstrip("/")

                        # 请求具体页面
                        pr = requests.get(product_url, timeout=8)
                        psoup = BeautifulSoup(pr.text, "html.parser")

                        # 抓取最可能的描述区域
                        desc = extract_description(psoup)

                        if desc:
                            found_description = desc
                            source_url = product_url
                            break
                if found_description:
                    break
            except Exception:
                continue

        # 关键词提取
        keywords = extract_keywords(found_description) if found_description else ""

        results.append({
            "flavor": flavor,
            "description": found_description or "❌ 未找到描述",
            "keywords": ", ".join(keywords),
            "source": source_url or "N/A"
        })

    # 显示结果页面
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
    # 尝试多个可能的位置
    candidates = []

    for tag in soup.find_all(["p", "div", "section"]):
        text = tag.get_text(" ", strip=True)
        if 50 < len(text) < 600:  # 过滤过短/过长
            candidates.append(text)

    return candidates[0] if candidates else None


def extract_keywords(text):
    if not text:
        return []

    text = re.sub(r"[^a-zA-Z\s]", " ", text)

    vec = TfidfVectorizer(stop_words="english", max_features=10)
    tfidf = vec.fit_transform([text])

    return vec.get_feature_names_out()


if __name__ == "__main__":
    app.run(debug=True)
