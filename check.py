"""Check the portable preview without accessing external services."""

import base64
import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.violations = []
        self.noindex = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "form":
            self.violations.append("A live form appears in the preview")
        if tag == "meta" and attrs.get("name") == "robots":
            self.noindex |= "noindex" in attrs.get("content", "")
        for name in ("src", "href", "poster"):
            if attrs.get(name):
                secured = (tag, name) in {("script", "src"), ("link", "href")}
                integrity = attrs.get("integrity") if secured else None
                self.references.append((attrs[name], integrity))
        if attrs.get("srcset"):
            self.references.extend(
                (entry.strip().split()[0], None)
                for entry in attrs["srcset"].split(",")
                if entry.strip()
            )


def check(root):
    errors = []

    def verify(file, url, integrity=None):
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
            return
        local = (file.parent / unquote(parsed.path)).resolve()
        if not local.is_relative_to(root):
            errors.append(f"{file.name}: link leaves output: {url}")
            return
        if local.is_dir():
            local /= "index.html"
        if not local.is_file():
            errors.append(f"{file.name}: missing {url}")
        elif integrity:
            algorithm, expected = integrity.split("-", 1)
            actual = base64.b64encode(hashlib.new(algorithm, local.read_bytes()).digest()).decode()
            if actual != expected:
                errors.append(f"{file.name}: integrity mismatch: {url}")

    for file in sorted(root.glob("*.html")):
        text = file.read_text()
        page = Page()
        page.feed(text)
        errors.extend(f"{file.name}: {message}" for message in page.violations)
        if not page.noindex:
            errors.append(f"{file.name}: noindex missing")
        if any(host in text for host in ("premier-hr-crm-dev.vercel.app", "challenges.cloudflare.com/turnstile", "casinosystem.app")):
            errors.append(f"{file.name}: live CRM, CAPTCHA or third-party service detected")
        for url, integrity in page.references:
            verify(file, url, integrity)
        for url in set(re.findall(r'[\'"](\./assets/[^\'"<>\s]+)[\'"]', text)):
            verify(file, url)

    for file in sorted((root / "assets").glob("*.css")):
        for url in re.findall(r'url\(\s*[\'"]?(\./[^\'"\)\s]+)', file.read_text()):
            verify(file, url)

    if not (root / ".nojekyll").is_file() or not (root / "index.html").is_file():
        errors.append("Missing GitHub Pages entry point")
    if errors:
        raise SystemExit("\n".join(sorted(set(errors))))
    print(f"Checked {len(list(root.glob('*.html')))} pages and {len(list((root / 'assets').iterdir()))} local assets.")


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "docs"
    check(root.resolve())
