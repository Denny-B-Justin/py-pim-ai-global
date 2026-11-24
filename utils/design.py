"""Shared layout building blocks (header, footer, buttons, icons, page headers)."""
from datetime import datetime, timezone

import dash
from dash import dcc, html

from constants import APP_NAME, REGISTRY_COLLECTIONS
from pages.pages_constants import FOOTER_BLURB, FOOTER_COPYRIGHT, FOOTER_TECH, NAV_LINKS
from utils import data


def href(page: str, **params) -> str:
    """Relative link in `?page=<name>` form (works under Connect's /content/<guid>/ prefix)."""
    from urllib.parse import urlencode

    return "?" + urlencode({"page": page, **{k: v for k, v in params.items() if v not in (None, "")}})


def icon(name: str, size: str = "", cls: str = "") -> html.Span:
    return html.Span(className=" ".join(filter(None, ["icon", f"icon-{name}", f"i-{size}" if size else "", cls])), **{"aria-hidden": "true"})


def link(children, page: str, cls: str = "", **params) -> dcc.Link:
    return dcc.Link(children, href=href(page, **params), className=cls)


def button(children, variant: str = "default", size: str = "md", cls: str = "", **kw) -> html.Button:
    return html.Button(children, type="button", className=f"btn btn-{variant} btn-{size} {cls}".strip(), **kw)


def link_button(children, page: str, variant: str = "default", size: str = "md", cls: str = "", **params) -> dcc.Link:
    return link(children, page, f"btn btn-{variant} btn-{size} {cls}".strip(), **params)


def eyebrow(text: str) -> html.P:
    return html.P(text, className="eyebrow")


def page_header(eyebrow_text: str, title: str, lead: str, lead_width: str = "lead-2xl"):
    return [eyebrow(eyebrow_text), html.H1(title, className="page-title"), html.P(lead, className=f"page-lead {lead_width}")]


def container(children, width: str = "7xl", cls: str = "page-pad", **kw) -> html.Div:
    return html.Div(children, className=f"container w-{width} {cls}".strip(), **kw)


def alert(message: str) -> html.Div:
    return html.Div(message, className="alert-error", role="alert")


def loading_row(text: str) -> html.Div:
    return html.Div([icon("loader-2", "5", "spin"), text], className="loading-row")


def fmt_int(value) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "0"


def as_of_text() -> str:
    ts = data.data_as_of()
    if not isinstance(ts, datetime):
        return ""
    ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return "Data as of " + ts.astimezone(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def header() -> html.Header:
    logo = html.Img(src=dash.get_asset_url("img/logo-pimpam.png"), alt="PIM PAM", width=219, height=94, className="logo logo-lg")
    return html.Header(
        className="site-header",
        children=[
            html.Div(
                className="container w-7xl header-inner",
                children=[
                    link(logo, "home", "logo-link"),
                    html.Nav([link(label, page, "nav-link") for label, page in NAV_LINKS], className="nav-desktop", **{"aria-label": "Main navigation"}),
                    html.Button(
                        [icon("menu", "24"), icon("x", "24")],
                        type="button",
                        className="nav-toggle",
                        **{"aria-expanded": "false", "aria-controls": "mobile-nav", "aria-label": "Open navigation menu"},
                    ),
                ],
            ),
            html.Nav(
                [link(label, page, "nav-link") for label, page in NAV_LINKS],
                id="mobile-nav",
                className="nav-mobile",
                **{"aria-label": "Mobile navigation"},
            ),
        ],
    )


def footer() -> html.Footer:
    counts = data.document_counts()
    collections = [
        html.Li(f"{c.label} ({counts[c.value]:,} docs)" if c.value in counts else c.label) for c in REGISTRY_COLLECTIONS
    ]
    logo = html.Img(src=dash.get_asset_url("img/logo-pimpam.png"), alt="PIM PAM", width=219, height=94, className="logo logo-md")
    return html.Footer(
        className="site-footer",
        children=html.Div(
            className="container w-7xl footer-inner",
            children=[
                html.Div(
                    className="footer-grid",
                    children=[
                        html.Div([link(logo, "home", "logo-link"), html.P(FOOTER_BLURB, className="footer-text")]),
                        html.Div(
                            [html.H4("Navigation", className="footer-h4"), html.Ul([html.Li(link(label, page)) for label, page in NAV_LINKS], className="footer-list")]
                        ),
                        html.Div(
                            [
                                html.H4("Document Collections", className="footer-h4"),
                                html.Ul(collections, className="footer-list"),
                                html.H4("Technology", className="footer-h4 mt"),
                                html.P(FOOTER_TECH, className="footer-tech"),
                            ]
                        ),
                    ],
                ),
                html.Div(FOOTER_COPYRIGHT.format(year=datetime.now().year, app=APP_NAME), className="footer-bottom"),
            ],
        ),
    )
