from flask import Flask, request, render_template_string, send_file
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import io
import csv
import re
from nltk.stem import PorterStemmer
from urllib.parse import urljoin, quote

app = Flask(__name__)

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

stemmer = PorterStemmer()
VAPE_STEM_MAP = {stemmer.stem(k): (k, VAPE_FLAVOR_KEYWORDS[k]) for k in VAPE_FLAVOR_KEYWORDS}

last_csv = None

@app.route("/", methods=["GET"])
def index():
    from os.path import join, dirname
    return open(join(dirname(__file__), "index.html"), encoding="utf-8").read()


@app.route("/scrape", methods=["POST"])
def scrape():
    urls = [u.strip() for u in request.form["urls"].splitlines() if u.strip()]
    brand = request.form["brand"].strip()
    flavors = [f.strip() for f in request.form["flavors"].splitlines() if f.strip()]

    results = asyncio.run(scrape_all(urls, flavors))

    # 生成 CSV
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


async def scrape_all(urls, flavors):
    results = []
    timeout = aiohttp.ClientTimeout(total=5)
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        tasks = [scrape_flavor(session, urls, flavor) for flavor in flavors]
        results = await asyncio.gather(*tasks)

    return results


async def scrape_flavor(session, urls, flavor):
    flavor_lower = flavor.lower()
    description = None
    source_url = None

    for url in urls:
        search_url = urljoin(url, f"search?q={quote(flavor)}")
        try:
            async with session.get(search_url) as r:
                if r.status != 200:
                    continue
                text = await r.text()
        except:
            continue

        soup = BeautifulSoup(text, "html.parser")
        product_link = None
        for a in soup.find_all("a", href=True):
            if flavor_lower in a.get_text(" ", strip=True).lower():
                product_link = urljoin(url, a["href"])
                break

        if product_link:
            try:
                async with session.get(product_link) as r2:
                    if r2.status == 200:
                        text2 = await r2.text()
                        soup2 = BeautifulSoup(text2, "html.parser")
                        description = extract_description(soup2)
                        source_url = product_link
            except:
                description = None
                source_url = product_link
            break

    keywords = extract_keywords(description)
    return {
        "flavor": flavor,
        "description": description or "❌ 未找到描述",
        "keywords": ", ".join([k[0] for k in keywords]),
        "categories": ", ".join([k[1] for k in keywords]),
        "source": source_url or "N/A"
    }


def extract_description(soup):
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"]

    for cls in ["description","product-description","product_desc","desc","detail"]:
        tag = soup.find("div", class_=lambda c: c and cls in c.lower())
        if tag:
            text = tag.get_text(" ", strip=True)
            if len(text) > 40:
                return text

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
