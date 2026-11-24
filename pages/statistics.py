"""?page=statistics — collection statistics from the metadata table."""
from dash import Input, Output, callback, html
from dash.exceptions import PreventUpdate

from pages.pages_constants import TECH_SPECS
from utils import data
from utils.design import alert, as_of_text, container, fmt_int, icon, page_header
from utils.security import rate_limited


def _body(force: bool = False):
    try:
        rows = data.get_metadata(force)
    except Exception:
        return alert("Failed to load statistics. Please try again later.")
    total = lambda key: sum(int(float(r.get(key) or 0)) for r in rows)  # noqa: E731
    cards = [
        ("Total Chunks", total("total_chunks"), "database"),
        ("Text Chunks", total("text"), "file-text"),
        ("Image Chunks", total("images"), "image"),
        ("Unique Documents", total("documents"), "file-text"),
    ]
    table_rows = [
        html.Tr(
            [
                html.Td(r["collection"], className="name"),
                html.Td(fmt_int(r["total_chunks"]), className="r num"),
                html.Td(fmt_int(r["text"]), className="r num m"),
                html.Td(fmt_int(r["images"]), className="r num m"),
                html.Td(fmt_int(r["documents"]), className="r num m"),
                html.Td(f"{fmt_int(r['avg_chunk_length'])} chars" if r.get("avg_chunk_length") else "—", className="r num m"),
            ]
        )
        for r in rows
    ]
    return [
        html.Div(
            [html.Div([icon(ico), html.P(fmt_int(v), className="v"), html.P(label, className="l")], className="card stat-card") for label, v, ico in cards],
            className="stat-grid cols-4",
        ),
        html.Div(
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("Collection"),
                                *[html.Th(t, className="r") for t in ("Total Chunks", "Text", "Images", "Documents", "Avg Chunk Length")],
                            ]
                        )
                    ),
                    html.Tbody(table_rows),
                ],
                className="data-table",
            ),
            className="card data-card",
        ),
        html.Div(
            [
                html.H3("Technical Specifications"),
                html.Dl([html.Div([html.Dt(k), html.Dd(v)]) for k, v in TECH_SPECS]),
            ],
            className="specs",
        ),
    ]


def layout(params: dict):
    return container(
        [
            html.Div(
                [
                    html.Div(
                        [
                            *page_header(
                                "Vector Database Analytics",
                                "Collection Statistics",
                                "Overview of the four document collections stored in Databricks Unity Catalog and indexed with "
                                "Databricks AI Search. Statistics are refreshed from the dashboard tables.",
                            ),
                            html.P(as_of_text(), className="asof"),
                        ]
                    ),
                    html.Button([icon("refresh-cw", "4"), "Refresh"], id="stats-refresh", type="button", className="btn btn-outline btn-sm", n_clicks=0),
                ],
                className="head-row",
            ),
            html.Div(_body(), id="stats-body"),
        ],
        width="6xl",
    )


@callback(Output("stats-body", "children"), Input("stats-refresh", "n_clicks"), prevent_initial_call=True)
def _refresh(n):
    if not n:
        raise PreventUpdate
    blocked, _ = rate_limited("refresh", 6, 60)
    return _body(force=not blocked)
