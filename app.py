"""Dash entrypoint for Posit Connect (`app:app`). Pages are selected with `?page=<name>`."""
import logging
import re
from urllib.parse import parse_qs

from dash import Dash, Input, Output, State, dcc, html
from flask import Flask, Response, abort

import constants as C
from pages import about, admin, analytics, home, not_found, query, registry, release_notes, statistics
from utils import auth_ui, export, security, state  # noqa: F401  (auth_ui registers callbacks)
from utils.design import alert, container, footer, header

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pim.app")

PAGES = {
    "home": home,
    "release-notes": release_notes,
    "query": query,
    "registry": registry,
    "statistics": statistics,
    "analytics": analytics,
    "about": about,
    "admin": admin,
}
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{16,32}$")
_META = [
    {"name": "viewport", "content": "width=device-width, initial-scale=1"},
    {"name": "description", "content": C.APP_DESCRIPTION},
    {"name": "theme-color", "content": "#1c2027"},
    {"property": "og:type", "content": "website"},
    {"property": "og:site_name", "content": C.APP_NAME},
    {"property": "og:title", "content": C.APP_TITLE},
    {"property": "og:description", "content": "AI-powered search across World Bank, IMF, and global best practice documents on public investment management."},
    {"name": "twitter:card", "content": "summary_large_image"},
    {"name": "twitter:title", "content": C.APP_NAME},
]
_INDEX = """<!DOCTYPE html>
<html lang="en">
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
__ICONS__
{%css%}
</head>
<body>
{%app_entry%}
<footer>
{%config%}
{%scripts%}
{%renderer%}
</footer>
</body>
</html>"""

server = Flask(__name__, static_folder=None)
app = Dash(
    __name__,
    server=server,
    title=C.APP_TITLE,
    update_title=None,
    suppress_callback_exceptions=True,
    enable_mcp=False,
    meta_tags=_META,
    csrf_token_name=C.CSRF_COOKIE,
    csrf_header_name=C.CSRF_HEADER,
)
security.init_security(app)
_icon = app.get_asset_url
app.index_string = _INDEX.replace(
    "__ICONS__",
    f'<link rel="icon" type="image/png" sizes="32x32" href="{_icon("img/favicon.png")}">\n'
    f'<link rel="icon" type="image/png" sizes="16x16" href="{_icon("img/favicon-16.png")}">\n'
    f'<link rel="apple-touch-icon" href="{_icon("img/apple-touch-icon.png")}">\n'
    f'<link rel="manifest" href="{_icon("site.webmanifest")}">',
)


def serve_layout():
    return html.Div(
        [
            dcc.Location(id="url", refresh=False),
            header(),
            html.Main(
                dcc.Loading(html.Div(id="page-content"), type="default", delay_show=300, parent_className="page-loading"),
                className="app-main",
            ),
            footer(),
            dcc.Store(id="q-history", storage_type="local"),
            dcc.Store(id="auth-tick", data=0),
            dcc.Store(id="title-sink"),
        ],
        className="app-shell",
    )


app.layout = serve_layout


@app.callback(Output("page-content", "children"), Input("url", "search"), Input("auth-tick", "data"), State("q-history", "data"))
def render_page(search, _tick, history):
    raw = parse_qs((search or "").lstrip("?"), max_num_fields=20)
    params = {k: security.clean_text(v[-1], 100) for k, v in raw.items() if v}
    module = PAGES.get(params.get("page") or "home", not_found)
    try:
        return module.layout(params, history) if module is query else module.layout(params)
    except Exception:
        log.exception("page render failed: %s", params.get("page"))
        return container(alert("Something went wrong while loading this page. Please try again."))


app.clientside_callback(
    "function(search){ return window.dash_clientside.pim.title(search); }",
    Output("title-sink", "data"),
    Input("url", "search"),
)


@server.get("/_export/<job_id>.doc")
def export_doc(job_id: str):
    job = state.job_get(job_id, security.session_id()) if _JOB_ID.match(job_id) else None
    if not job or job.get("status") != "done":
        abort(404)
    document, filename = export.build(job)
    resp = Response(document, mimetype="application/msword")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    app.run(host=C.HOST, port=C.PORT, debug=False)
