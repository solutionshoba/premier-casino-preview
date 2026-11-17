"""Build the public, read-only preview from a Premier Casino Webflow snapshot."""

import argparse
import base64
import hashlib
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit


PAGES = {
    "/": "index.html",
    "/arusha": "arusha.html",
    "/dodoma": "dodoma.html",
    "/mbeya": "mbeya.html",
    "/mwanza": "mwanza.html",
    "/careers": "careers.html",
    "/career-role": "career-role.html",
    "/lucky": "lucky.html",
}
SITE_HOSTS = {"premiercasino.tz", "www.premiercasino.tz", "premier-casino-b5c288c3794.webflow.io"}
SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
FORMS = re.compile(r"<form\b([^>]*)>(.*?)</form\s*>", re.I | re.S)
LINK = re.compile(r'\bhref=(["\'])([^"\']*)\1', re.I)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)

BOOTSTRAP = r"""
(() => {
  const roles = JSON.parse(document.getElementById('preview-roles').textContent);
  const slug = new URLSearchParams(location.search).get('role') || 'dealer';
  const role = Object.hasOwn(roles, slug) ? roles[slug] : null;
  const content = document.querySelector('.role-preview-primary');
  if (!content || slug === 'dealer') return;
  if (!role) {
    const title = document.createElement('h1');
    title.className = 'role-preview-title';
    title.textContent = 'Role unavailable in this preview';
    content.replaceChildren(title);
    return;
  }
  for (const [field, value] of Object.entries(role)) {
    const element = content.querySelector('[data-role-' + field + ']');
    if (element) element.textContent = value;
  }
  content.querySelectorAll('.role-preview-h2, .role-preview-list').forEach(element => element.remove());
  document.title = role.title + ' | Premier Casino preview';
})();
"""


def link_for_preview(match):
    quote, raw = match.groups()
    value = urlsplit(html.unescape(raw))
    if value.netloc and value.hostname not in SITE_HOSTS:
        return match[0]
    if value.scheme and value.scheme not in {"http", "https"}:
        return match[0]
    if not value.path.startswith("/") or value.path not in PAGES:
        return match[0]
    if value.path == "/":
        target = "./"
    else:
        target = "./" + PAGES[value.path]
    if value.query:
        target += "?" + value.query
    if value.fragment:
        target += "#" + value.fragment
    return f"href={quote}{html.escape(target, quote=True)}{quote}"


def freeze_form(match):
    attributes, _ = match.groups()
    if 'role-application' in attributes:
        return (
            '<div id="role-application"><h2>Applications</h2>'
            '<p>This is a preview. Visit the official careers page for current vacancies and applications.</p>'
            '<p><a href="https://www.premiercasino.tz/careers">Official careers page ↗</a></p></div>'
        )
    return (
        '<div class="form-block"><p>This preview does not send messages.</p>'
        '<p><a href="https://www.premiercasino.tz/">Visit the official website ↗</a></p></div>'
    )


def remove_live_script(match):
    attributes, code = match.groups()
    if any(marker in code for marker in ("const CRM =", "[custom-submit]")):
        return ""
    if "attributes-cmsload" in attributes:
        return ""
    return match[0]


def archived_roles(careers):
    roles = {}
    card = r'<a href="/career-role\?role=([a-z-]+)"[^>]*>(.*?)</a>'
    for match in re.finditer(card, careers, re.S):
        slug, markup = match.groups()
        title = re.search(r'class="careers-role-title">([^<]+)', markup)[1]
        city = re.search(r'class="careers-role-city">([^<]+)', markup)[1]
        team = re.search(r'class="careers-role-type">([^<]+)', markup)[1]
        summary = re.search(r"<p>([^<]+)</p>", markup)[1]
        roles[slug] = {k: html.unescape(v) for k, v in {
            "title": title, "city": city, "team": team,
            "category": team, "summary": summary,
        }.items()}
    return roles


class AssetLocalizer:
    def __init__(self, snapshot, output):
        self.snapshot = snapshot
        self.output = output
        manifest = json.loads((snapshot / "manifest.json").read_text())
        self.assets = {a["url"]: a["file"] for a in manifest["assets"] if a.get("file")}
        self.replacements = {
            form: file
            for url, file in self.assets.items()
            for form in (url, html.escape(url, quote=False))
        }
        self.pattern = re.compile("|".join(map(re.escape, sorted(self.replacements, key=len, reverse=True))))
        self.copied = set()

    def replace(self, content, *, relative_to_assets=False):
        def local(match):
            file = self.replacements[match[0]]
            self.copy(file)
            if relative_to_assets:
                return "./" + Path(file).name
            return "./" + file

        return self.pattern.sub(local, content)

    def copy(self, file):
        if file in self.copied:
            return
        self.copied.add(file)
        source = self.snapshot / file
        target = self.output / file
        if source.suffix == ".css":
            target.write_text(self.replace(source.read_text(), relative_to_assets=True))
        else:
            shutil.copyfile(source, target)

    def fix_stylesheet_integrity(self, match):
        tag = match[0]
        if "cdn.prod.website-files.com" in tag and re.search(r'rel="(?:preconnect|dns-prefetch)"', tag):
            return ""
        asset = re.search(r'href="\./(assets/[^"]+\.css)"', tag)
        integrity = re.search(r'integrity="(sha(?:256|384|512))-[^"]+"', tag)
        if not asset or not integrity:
            return tag
        algorithm = integrity[1]
        digest = hashlib.new(algorithm, (self.output / asset[1]).read_bytes()).digest()
        replacement = f'integrity="{algorithm}-{base64.b64encode(digest).decode()}"'
        return tag.replace(integrity[0], replacement)


def build(snapshot, output, base_path):
    if not (snapshot / "manifest.json").is_file():
        raise ValueError("Point the builder at the production-webflow folder from the migration archive.")
    if not re.fullmatch(r"/(?:[a-zA-Z0-9_-]+/)*", base_path):
        raise ValueError("The base path must start and end with a slash.")
    output.mkdir(exist_ok=True, parents=True)
    (output / "assets").mkdir(exist_ok=True)
    localize = AssetLocalizer(snapshot, output)
    roles = archived_roles((snapshot / "pages" / "careers.html").read_text())
    badge = (
        '<aside class="pc-preview" aria-label="Preview notice">'
        'Site preview · forms disabled</aside>'
    )
    style = """<meta name="robots" content="noindex, nofollow">
<style>
.pc-preview{position:fixed;z-index:9999;inset:auto 10px 10px auto;background:#161616;color:#e8c688;
 border:1px solid #9b8b6e;padding:5px 8px;border-radius:4px;font:12px Arial,sans-serif;pointer-events:none}
.cert-gallery[open]{max-width:none}
@media(max-width:767px){.section-sert .sert_block{flex-direction:row!important}}
</style>
"""
    for route, filename in PAGES.items():
        text = (snapshot / "pages" / filename).read_text()
        text = SCRIPT.sub(remove_live_script, text)
        text = LINK.sub(link_for_preview, text)
        text = FORMS.sub(freeze_form, text)
        text = localize.replace(text)
        text = LINK_TAG.sub(localize.fix_stylesheet_integrity, text)
        text = text.replace("</head>", style + "</head>", 1)
        if route == "/careers":
            text = text.replace(
                'Explore opportunities across our four locations. Different backgrounds. Shared ambition.',
                'Example roles from the archived website. See the official careers page for current openings.',
            )
        if route == "/career-role":
            data = json.dumps(roles, ensure_ascii=False).replace("<", "\\u003c")
            text = text.replace("</body>", (
                f'<script type="application/json" id="preview-roles">{data}</script>'
                f'<script>{BOOTSTRAP}</script></body>'
            ), 1)
        if route == "/lucky":
            text = re.sub(
                r'<iframe\b[^>]*\bsrc="https://casinosystem\.app/lucky"[^>]*>.*?</iframe>',
                '<main style="padding:5rem 1rem;text-align:center"><h1>Lucky Page</h1>'
                '<p>The interactive service is available on the official website.</p>'
                '<a href="https://www.premiercasino.tz/lucky">Visit the official page ↗</a></main>',
                text, flags=re.I | re.S,
            )
        text = text.replace("</body>", badge + "</body>", 1)
        if route == "/dodoma":
            text = text.replace(
                "Discover unmatched excitement at Mwanza Casino, located on the 2nd floor of Rock City Mall.",
                "Discover Premier Casino Dodoma, located at New Dodoma Hotel.",
            )
        if FORMS.search(text) or "premier-hr-crm-dev.vercel.app" in text:
            raise ValueError(f"Live form or CRM integration in {filename}")
        (output / filename).write_text(text)
    (output / ".nojekyll").touch()
    (output / "404.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Page not found | Premier Casino preview</title><body style="background:#111;color:#e8c688;'
        'font:18px system-ui;padding:4rem 1rem;text-align:center"><h1>Page not found</h1>'
        '<p><a id="preview-home" style="color:inherit" href="/">Back to the preview</a></p>'
        f'<script>const root={json.dumps(base_path)};if(location.pathname.startsWith(root))'
        'document.getElementById("preview-home").href=root;</script></body></html>\n'
    )
    print(f"Built {len(PAGES)} pages and {len(localize.copied)} local assets in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="production-webflow folder from the migration archive")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "docs")
    parser.add_argument("--base-path", default="/premier-casino-preview/", help="Mount point used by the 404 page")
    args = parser.parse_args()
    build(args.snapshot, args.output, args.base_path)
