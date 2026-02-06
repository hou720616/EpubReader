import os
import zipfile
import xml.etree.ElementTree as ET
import html
from html.parser import HTMLParser

def read_text_with_fallback(path: str) -> str:
    for enc in ("utf-8", "gbk", "utf-16"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.block_tags = {
            "p",
            "div",
            "br",
            "li",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
            "pre",
            "section",
            "article",
        }

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        text = html.unescape("".join(self.parts))
        lines = [line.rstrip() for line in text.splitlines()]
        return "\n".join([line for line in lines if line.strip() != ""])


def parse_epub_chapters(epub_path: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(epub_path, "r") as zf:
        if "META-INF/container.xml" not in zf.namelist():
            raise ValueError("无效的 EPUB：缺少 container.xml")
        container = ET.fromstring(zf.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is None:
            raise ValueError("无效的 EPUB：缺少 rootfile")
        opf_path = rootfile.attrib.get("full-path")
        if not opf_path:
            raise ValueError("无效的 EPUB：rootfile 路径为空")
        opf_data = zf.read(opf_path)
        opf = ET.fromstring(opf_data)
        manifest = {}
        for item in opf.findall(".//{*}manifest/{*}item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            if item_id and href:
                manifest[item_id] = href
        spine_items = []
        for itemref in opf.findall(".//{*}spine/{*}itemref"):
            ref = itemref.attrib.get("idref")
            if ref:
                spine_items.append(ref)
        base_dir = os.path.dirname(opf_path)
        chapters: list[dict[str, str]] = []
        for item_id in spine_items:
            href = manifest.get(item_id)
            if not href:
                continue
            full_path = os.path.normpath(os.path.join(base_dir, href)).replace("\\", "/")
            if full_path not in zf.namelist():
                continue
            raw = zf.read(full_path)
            html_text = raw.decode("utf-8", errors="ignore")
            parser = HTMLTextExtractor()
            parser.feed(html_text)
            text = parser.get_text()
            if text:
                title = os.path.splitext(os.path.basename(href))[0] or "章节"
                chapters.append({"title": title, "text": text})
        if not chapters:
            raise ValueError("未解析到可读文本")
        return chapters
