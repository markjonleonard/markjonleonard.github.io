#!/usr/bin/env python3
"""One-off import of weakspeak.blogspot.com posts into content/blog/ as Markdown.

Reads the public Blogger JSON feed (no login or export needed), converts each
post's HTML body to Markdown, and downloads any images into static/images/.

    python3 scripts/import_blogger.py
"""
import json
import os
import pathlib
import re
import urllib.request
from html import unescape
from html.parser import HTMLParser

FEED = "https://weakspeak.blogspot.com/feeds/posts/default?alt=json&max-results=500"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = pathlib.Path(os.environ.get("IMPORT_OUT", ROOT / "content" / "blog"))
IMAGES = ROOT / "static" / "images" / "weakspeak"

VOID = {"br", "img", "hr"}
# Stands in for list-item indentation so whitespace cleanup leaves it alone.
INDENT = "\x02"


class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs or {}), parent, []


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node("root")

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            n = self.cur
            while n is not self.root and n.tag not in ("ul", "ol", "li"):
                n = n.parent
            if n.tag == "li":
                self.cur = n.parent
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def style_of(node):
    return (node.attrs.get("style") or "").replace(" ", "").lower()


def inline_wrap(text, mark):
    # Keep surrounding whitespace outside the emphasis markers, or Markdown ignores them.
    m = re.match(r"^(\s*)(.*?)(\s*)$", text, re.S)
    lead, core, trail = m.groups()
    return f"{lead}{mark}{core}{mark}{trail}" if core else text


class Converter:
    def __init__(self, slug):
        self.slug = slug

    def children(self, node):
        return "".join(self.convert(c) for c in node.children)

    def convert(self, node):
        if isinstance(node, str):
            return re.sub(r"\s+", " ", node).replace("*", r"\*")
        tag, inner = node.tag, None
        if tag == "br":
            return "\n"
        if tag in ("p", "div"):
            return "\n\n" + self.children(node).strip() + "\n\n"
        if tag == "blockquote":
            body = self.children(node).strip()
            body = re.sub(r"\n{3,}", "\n\n", body)
            return "\n\n" + "\n".join(("> " + l).rstrip() for l in body.split("\n")) + "\n\n"
        if tag in ("ul", "ol"):
            items = [c for c in node.children if isinstance(c, Node) and c.tag == "li"]
            lines = []
            for i, li in enumerate(items, 1):
                marker = f"{i}. " if tag == "ol" else "- "
                body = re.sub(r"\n{3,}", "\n\n", self.children(li).strip())
                lines.append(marker + "\n".join((INDENT * len(marker) + l) if l.strip() else "" for l in body.split("\n")).lstrip(INDENT))
            loose = any("\n" in l for l in lines)
            return "\n\n" + ("\n\n" if loose else "\n").join(lines) + "\n\n"
        if tag == "a":
            text = self.children(node)
            href = node.attrs.get("href")
            if not href or not text.strip():
                return text
            return _link(text, href)
        if tag in ("em", "i"):
            return inline_wrap(self.children(node), "*")
        if tag in ("strong", "b"):
            return inline_wrap(self.children(node), "**")
        if tag in ("strike", "s", "del"):
            return inline_wrap(self.children(node), "~~")
        if tag == "img":
            return f"\n\n![]({self.fetch_image(node.attrs['src'])})\n\n"
        if tag == "table":
            # Only used for image layout on Blogger; flatten it.
            return self.children(node)
        if tag == "span":
            s = style_of(node)
            inner = self.children(node)
            if "font-style:italic" in s:
                return inline_wrap(inner, "*")
            if "font-weight:bold" in s:
                return inline_wrap(inner, "**")
            # Blogger's "small text" asides. Skip Word-paste debris (font-family) and
            # anything spanning a line break, which would break the Markdown.
            if (
                "font-size:" in s
                and "font-family" not in s
                and inner.strip()
                and "\n" not in inner.strip()
                and "<small>" not in inner
            ):
                return inline_wrap(inner, "\x01").replace("\x01", "<small>", 1).replace("\x01", "</small>", 1)
            return inner
        return self.children(node)

    def fetch_image(self, src):
        IMAGES.mkdir(parents=True, exist_ok=True)
        ext = pathlib.Path(src.split("?")[0]).suffix or ".jpg"
        name = f"{self.slug}{ext}"
        dest = IMAGES / name
        if not dest.exists():
            urllib.request.urlretrieve(src, dest)
        return f"/images/weakspeak/{name}"


def _link(text, href):
    internal = re.match(r"^https?://weakspeak\.blogspot\.com/\d{4}/\d{2}/([^/.]+)\.html$", href)
    if internal:
        href = f"/blog/{internal.group(1)}/"
    m = re.match(r"^(\s*)(.*?)(\s*)$", text, re.S)
    lead, core, trail = m.groups()
    return f"{lead}[{core}]({href}){trail}"


def to_markdown(html, slug):
    builder = TreeBuilder()
    builder.feed(html)
    md = Converter(slug).convert(builder.root)
    # Blogger uses <br /><br /> for paragraph breaks.
    md = md.replace("</small><small>", "")
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n[ \t]+", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    # A lone newline inside a paragraph was a <br />: keep it as a hard break.
    md = re.sub(r"(?<=[^\n>])\n(?=[^\n>])", "  \n", md)
    md = md.replace(INDENT, " ")
    return md.strip() + "\n"


def toml_str(s):
    return json.dumps(s, ensure_ascii=False)


def main():
    with urllib.request.urlopen(FEED) as r:
        feed = json.load(r)["feed"]
    OUT.mkdir(parents=True, exist_ok=True)
    for e in feed["entry"]:
        title = unescape(e["title"]["$t"])
        url = next(l["href"] for l in e["link"] if l["rel"] == "alternate")
        old_path = re.sub(r"^https?://[^/]+", "", url)
        slug = pathlib.Path(url).stem
        published = e["published"]["$t"]
        date = published[:10]
        body = to_markdown(e["content"]["$t"], slug)
        front = "\n".join([
            "+++",
            f"title = {toml_str(title)}",
            f"date = {published}",
            "",
            "[taxonomies]",
            'tags = ["weak-speak"]',
            "",
            "[extra]",
            f"blogger_url = {toml_str(url)}",
            "+++",
        ])
        (OUT / f"{date}-{slug}.md").write_text(front + "\n\n" + body, encoding="utf-8")
        print(f"{date}  {title}  ({old_path})")


if __name__ == "__main__":
    main()
