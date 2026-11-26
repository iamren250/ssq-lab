
import csv
import io
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen
from html.parser import HTMLParser

OUTPUT = Path("data/draws.json")
REPORT = Path("data/validation.json")

HISTORY_URL = "https://raw.githubusercontent.com/cs4745/PickWise/main/data/ssq.csv"
VALIDATION_URL = "https://raw.githubusercontent.com/cs4745/PickWise/main/data/validation.json"
LATEST_URL = "https://www.swlc.net.cn/lottery/ssq.html?limit=100&view=previous"
GUANGXI_URL = "https://www.gxcaipiao.com.cn/notice/list/ssq/1.html"

def fetch(url):
    last_error = None
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=40) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"获取失败：{url}；{last_error}")


def valid(issue, red, blue):
    return (
        re.fullmatch(r"20\d{5}", str(issue)) is not None
        and len(red) == 6
        and len(set(red)) == 6
        and all(isinstance(n, int) and 1 <= n <= 33 for n in red)
        and isinstance(blue, int)
        and 1 <= blue <= 16
    )


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


def load_history():
    raw = fetch(HISTORY_URL).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    draws = {}

    for row in reader:
        issue = str(row.get("issue", "")).strip()
        date = str(row.get("date", "")).strip()
        red = [int(x) for x in re.findall(r"\d+", row.get("front", ""))]
        blue_nums = re.findall(r"\d+", row.get("back", ""))

        if len(blue_nums) != 1:
            continue

        blue = int(blue_nums[0])
        if not valid(issue, red, blue):
            continue

        item = {
            "issue": issue,
            "date": date,
            "red": sorted(red),
            "blue": blue
        }

        if issue in draws and draws[issue] != item:
            raise RuntimeError(f"历史库内部期号冲突：{issue}")

        draws[issue] = item

    if len(draws) < 3500:
        raise RuntimeError(f"历史数据数量异常：只读取到 {len(draws)} 期，停止更新")

    return draws


def load_history_validation():
    obj = json.loads(fetch(VALIDATION_URL).decode("utf-8"))
    ssq = obj.get("games", {}).get("ssq", {})
    cross = ssq.get("cross_check", {})

    if ssq.get("validation_errors", 1) != 0:
        raise RuntimeError("历史数据源的格式校验未通过")

    if cross.get("conflicts", []) or cross.get("conflict_count", 0) != 0:
        raise RuntimeError("历史数据源报告存在号码冲突")

    return {
        "source_count": ssq.get("count"),
        "cross_checked": cross.get("checked", 0),
        "cross_conflicts": cross.get("conflict_count", 0),
        "source_rows": ssq.get("source_rows", {})
    }


def load_latest():
    html = fetch(LATEST_URL).decode("utf-8", errors="replace")
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
        if not date_match:
            continue

        red_text = re.sub(r"\D", "", row[2])
        blue_text = re.sub(r"\D", "", row[3])

        if len(red_text) != 12 or len(blue_text) != 2:
            continue

        red = [
            int(red_text[i:i + 2])
            for i in range(0, 12, 2)
        ]
        blue = int(blue_text)

        if not valid(issue, red, blue):
            continue

        draws[issue] = {
            "issue": issue,
            "date": date_match.group(),
            "red": sorted(red),
            "blue": blue
        }

    if not draws:
        raise RuntimeError("近期官方开奖数据读取失败")

    return draws

def load_guangxi():
    html = fetch(GUANGXI_URL).decode("utf-8", errors="replace")
    parser = TableParser()
    parser.feed(html)
    draws = {}

    for row in parser.rows:
        if len(row) < 3:
            continue

        issue = row[0].strip()
        if not re.fullmatch(r"20\d{5}", issue):
            continue

        date_match = re.search(r"20\d{2}-\d{2}-\d{2}", row[1])
        nums = [int(x) for x in re.findall(r"\d+", row[2])]

        if not date_match or len(nums) != 7:
            continue

        red = nums[:6]
        blue = nums[6]

        if not valid(issue, red, blue):
            continue

        draws[issue] = {
            "issue": issue,
            "date": date_match.group(),
            "red": sorted(red),
            "blue": blue
        }

    if not draws:
        raise RuntimeError("广西福彩数据读取失败")

    return draws
def main():
    history = load_history()
    validation = load_history_validation()
    latest = load_latest()
    guangxi = load_guangxi()
    verified_latest = {}

    for issue, official in latest.items():
        if issue not in guangxi:
            continue

        other = guangxi[issue]
        if official["red"] != other["red"] or official["blue"] != other["blue"]:
            raise RuntimeError(f"上海福彩与广西福彩号码冲突：{issue}")

        verified_latest[issue] = official

    if len(verified_latest) < 10:
        raise RuntimeError(
            f"两地交叉核验期数不足：{len(verified_latest)}期，停止更新"
        )

    latest = verified_latest
    conflicts = []
    for issue, official in latest.items():
        if issue in history:
            old = history[issue]
            if old["red"] != official["red"] or old["blue"] != official["blue"]:
                conflicts.append(issue)

    if conflicts:
        raise RuntimeError(
            "历史数据与近期官方数据号码不一致，停止写入："
            + ", ".join(conflicts)
        )

    # 以全量历史库为基础，用近期官方数据补齐最新期。
    history.update(latest)

    # 保留已有文件中不冲突的记录，不覆盖已经核验的数据。
    if OUTPUT.exists():
        old = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if isinstance(old, list):
            for item in old:
                issue = str(item.get("issue", ""))
                red = item.get("red", [])
                blue = item.get("blue")
                if valid(issue, red, blue) and issue not in history:
                    history[issue] = item

    result = sorted(
        history.values(),
        key=lambda x: x["issue"],
        reverse=True
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    report = {
        "total_count": len(result),
        "earliest_issue": result[-1]["issue"],
        "latest_issue": result[0]["issue"],
        "history_source": "PickWise：中彩网 + 500彩票网历史数据",
        "history_source_count": validation["source_count"],
        "historical_cross_checked": validation["cross_checked"],
        "historical_conflicts": validation["cross_conflicts"],
        "recent_official_source": "上海福彩",
        "recent_official_count": len(latest),
        "recent_conflicts": conflicts
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(
        f"更新成功：共 {len(result)} 期；"
        f"历史交叉核验 {validation['cross_checked']} 期；"
        f"近期官方数据 {len(latest)} 期。"
    )


if __name__ == "__main__":
    main()
