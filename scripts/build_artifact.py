"""Turn the replay build (web/dist-replay/index.html) into a hosted-page file.

Writes:
  artifact/index.html        page body for the claude.ai Artifact (no doctype/html/head/body;
                             React 18.3.1 UMD from cdnjs)
  artifact/local_test.html   the same page wrapped as a full document with React from
                             node_modules, for offline screenshots

    cd web && npm run build:replay && cd .. && python scripts/build_artifact.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web" / "dist-replay" / "index.html"
OUT = ROOT / "artifact"

CDN = [
    "https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js",
]


def main():
    html = SRC.read_text(encoding="utf-8")
    style = "\n".join(re.findall(r"<style[^>]*>.*?</style>", html, flags=re.S))
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S)
    app_js = max(scripts, key=len)
    fonts = re.search(r'<link rel="stylesheet" href="https://fonts.googleapis.com[^"]+"\s*/?>', html).group(0)
    head = ('<title>Service Ops AI Pilot</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            + fonts + "\n" + style + "\n")
    body = '<div id="root"></div>\n'
    app = "<script>\n" + app_js.replace("</script", "<\\/script") + "\n</script>\n"
    OUT.mkdir(exist_ok=True)
    cdn = "".join(f'<script src="{u}"></script>\n' for u in CDN)
    (OUT / "index.html").write_text(head + cdn + body + app, encoding="utf-8")
    nm = ROOT / "web" / "node_modules"
    local = "".join(f'<script src="file://{nm}/{p}"></script>\n' for p in
                    ("react/umd/react.production.min.js", "react-dom/umd/react-dom.production.min.js"))
    (OUT / "local_test.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        + head + "</head><body>" + local + body + app + "</body></html>", encoding="utf-8")
    print("artifact/index.html", round((OUT / "index.html").stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
