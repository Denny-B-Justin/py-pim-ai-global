"""Word-compatible (.doc, HTML) export of a finished query job."""
import html
import re
from datetime import datetime, timezone

import markdown
import nh3

from pages.pages_constants import EXPORT_FOOTER

_TAGS = {"p", "br", "strong", "em", "b", "i", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "code", "pre", "hr", "table", "thead", "tbody", "tr", "th", "td", "a", "sup", "sub", "del"}
_CSS = """
body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; color: #1d212b; }
h1 { font-size: 18pt; color: #374696; margin-bottom: 4pt; }
h2 { font-size: 14pt; color: #374696; margin-top: 18pt; }
h3 { font-size: 12pt; color: #374696; }
.meta { color: #555; font-size: 10pt; margin-bottom: 12pt; }
.meta div { margin: 2pt 0; }
blockquote { border-left: 3pt solid #4472c4; padding-left: 10pt; color: #555; }
code { font-family: Consolas, monospace; background: #f0f5ff; padding: 1pt 3pt; }
pre { background: #f0f5ff; padding: 8pt; font-family: Consolas, monospace; font-size: 10pt; }
table { border-collapse: collapse; } th, td { border: 1pt solid #dce4f0; padding: 3pt 6pt; }
hr { border: none; border-top: 1pt solid #dce4f0; margin: 18pt 0; }
footer { color: #888; font-size: 9pt; margin-top: 24pt; }
"""


def _e(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _answer_html(markdown_text: str) -> str:
    raw = markdown.markdown(markdown_text, extensions=["tables", "fenced_code", "sane_lists"])
    return nh3.clean(raw, tags=_TAGS, attributes={"a": {"href"}}, url_schemes={"http", "https", "mailto"}, link_rel="noopener noreferrer")


def build(job: dict) -> tuple[str, str]:
    """Return (html document, download filename) for a finished job."""
    now = datetime.now(timezone.utc)
    meta, sources = job["meta"], job["sources"]
    items = "".join(
        "<li style=\"margin-bottom:8pt;\"><strong>{file}</strong>{detail}<br/><span style=\"color:#555;font-size:10pt;\">{ex}</span></li>".format(
            file=_e(s["file"]),
            detail=_e(" — " + " · ".join(b for b in (s["collection"], s["country"], str(s["year"] or ""), s["pages"], s["section"]) if b)) if any((s["collection"], s["country"], s["year"], s["pages"], s["section"])) else "",
            ex=_e(s["excerpt"]),
        )
        for s in sources
    )
    sources_html = f"<h2>Sources ({len(sources)})</h2><ol>{items}</ol>" if sources else ""
    doc = f"""<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"/><title>PIM-PAM Query Result</title><style>{_CSS}</style></head>
<body>
<h1>PIM-PAM query result</h1>
<div class="meta">
<div><strong>Question:</strong> {_e(job.get("query"))}</div>
<div><strong>Collection:</strong> {_e(job.get("collection"))}</div>
<div><strong>Model:</strong> {_e(meta.get("model"))}</div>
<div><strong>Generated:</strong> {now:%Y-%m-%d %H:%M:%S} UTC</div>
</div>
<hr/>
<h2>Answer</h2>
{_answer_html(job["answer"])}
{sources_html}
<hr/>
<footer>{_e(EXPORT_FOOTER)}</footer>
</body>
</html>"""
    slug = re.sub(r"[^a-z0-9]+", "-", str(job.get("query", "")).lower()).strip("-")[:40]
    return doc, f"pim-pam-{now:%Y-%m-%d-%H-%M}{'-' + slug if slug else ''}.doc"
