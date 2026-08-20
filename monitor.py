import json
import urllib.request
from pathlib import Path

URL = "https://qqdoc-monitor-global-dpz5wry62pcc.edgeone.dev/api/qqdoc?id=DV1BNQkZiamdJaVVI&tab=5b4psn"
SNAPSHOT = Path("snapshot.json")


def fetch():
    with urllib.request.urlopen(URL, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    data = fetch()
    # TODO: extract only real cell values from qqdoc JSON
    current = data.get("document", data)
    old = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    if old != current:
        SNAPSHOT.write_text(json.dumps(current, ensure_ascii=False, indent=2))
        print("snapshot updated")
    else:
        print("no change")


if __name__ == "__main__":
    main()
