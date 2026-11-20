
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from html.parser import HTMLParser

URL = "https://www.swlc.net.cn/lottery/ssq.html?limit=100&view=previous"
OUTPUT = Path("data/draws.json")


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def main():
    request = Request(
        URL,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    parser = TableParser()
    parser.feed(html)

    draws = {}
    for row in parser.rows:
        if len(row) < 4:
            continue

        issue = row[0].strip()
        if not re.fullmatch(r"20\d{5}", issue):
            continue

        date_match = re.search(r"20\d{2}-\d{2}-\d{2}", row[1])
        red_text = re.sub(r"\D", "", row[2])
        blue_text = re.sub(r"\D", "", row[3])

        if not date_match or len(red_text) != 12 or len(blue_text) != 2:
            continue

        red = [int(red_text[i:i+2]) for i in range(0, 12, 2)]
        blue = int(blue_text)

        if (len(set(red)) != 6 or
                any(n < 1 or n > 33 for n in red) or
                blue < 1 or blue > 16):
            continue

        draws[issue] = {
            "issue": issue,
            "date": date_match.group(),
            "red": sorted(red),
            "blue": blue
        }

    if not draws:
        raise RuntimeError("没有读取到有效开奖数据，停止更新。")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    old = {}
    if OUTPUT.exists():
        old_data = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if isinstance(old_data, list):
            old = {str(x["issue"]): x for x in old_data}

    old.update(draws)
    result = sorted(
        old.values(),
        key=lambda x: x["issue"],
        reverse=True
    )

    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"成功更新 {len(draws)} 期官方开奖数据。")


if __name__ == "__main__":
    main()
