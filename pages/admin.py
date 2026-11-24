"""?page=admin — operational status console (admin only)."""
from dash import Input, Output, callback, html
from dash.exceptions import PreventUpdate

from constants import AI_SEARCH_ENDPOINT, COLLECTIONS
from pages.pages_constants import PIPELINE_STEPS
from utils import data, security
from utils import databricks_client as db
from utils.auth_ui import login_view, logout_button
from utils.design import alert, as_of_text, container, fmt_int, icon, page_header


def _pill(text: str, kind: str) -> html.Span:
    return html.Span(text, className=f"pill {kind}")


def _status():
    def load():
        return {"endpoint": db.endpoint_status(AI_SEARCH_ENDPOINT), "indexes": [db.index_status(c.index) for c in COLLECTIONS]}

    return data.cached("admin:status", load, force=False)


def _body(force: bool = False):
    try:
        if force:
            data.get_metadata(True)
            data.cache_clear("admin:status", "asof")
        status, meta = _status(), data.get_metadata()
    except Exception:
        return alert("Failed to load status. Check the Databricks connection settings.")
    ep = status["endpoint"]
    online = str(ep["state"]).upper() == "ONLINE"
    idx_rows = [
        html.Tr(
            [
                html.Td(html.Span(i["name"].rsplit(".", 1)[-1], title=i["name"]), className="name"),
                html.Td(i["type"] or "—", className="m"),
                html.Td(fmt_int(i["rows"]) if i["rows"] is not None else "—", className="r num"),
                html.Td(_pill("Ready", "ok") if i["ready"] else _pill(i["message"][:60] or "Not ready", "warn")),
            ]
        )
        for i in status["indexes"]
    ]
    meta_rows = [
        html.Tr(
            [
                html.Td(r["collection"], className="name"),
                html.Td(fmt_int(r["documents"]), className="r num"),
                html.Td(fmt_int(r["total_chunks"]), className="r num"),
            ]
        )
        for r in meta
    ]
    table = lambda head, rows: html.Div(  # noqa: E731
        html.Table([html.Thead(html.Tr(head)), html.Tbody(rows)], className="data-table"), className="card data-card", style={"marginTop": "1rem"}
    )
    return [
        html.Div(
            [
                html.H2("AI Search"),
                html.P(
                    [f"Endpoint {ep['name']} ", _pill(str(ep["state"] or "Unknown"), "ok" if online else "warn"), f" · {ep['type'] or '—'} · {ep['indexes'] if ep['indexes'] is not None else '—'} indexes"]
                ),
                table([html.Th("Index"), html.Th("Type"), html.Th("Rows", className="r"), html.Th("Status")], idx_rows),
            ],
            className="card admin-panel",
        ),
        html.Div(
            [
                html.H2("Data freshness"),
                html.P(as_of_text() or "Refresh time unavailable."),
                table([html.Th("Collection"), html.Th("Documents", className="r"), html.Th("Chunks", className="r")], meta_rows),
            ],
            className="card admin-panel",
        ),
        html.Div(
            [html.H2("Updating the data"), html.P("Ingestion runs in the Databricks notebook pipeline, not in this app."), html.Ol([html.Li(s) for s in PIPELINE_STEPS])],
            className="card admin-panel",
        ),
    ]


def layout(params: dict):
    if not security.is_admin():
        return login_view("The admin console")
    return container(
        [
            html.Div(
                [
                    html.Div(page_header("Administration", "Admin Console", "Operational status of the Databricks data services behind this app.", "lead-3xl")),
                    html.Div(
                        [html.Button([icon("refresh-cw", "4"), "Refresh"], id="admin-refresh", type="button", className="btn btn-outline btn-sm", n_clicks=0), logout_button()],
                        className="head-actions",
                    ),
                ],
                className="head-row",
            ),
            html.Div(_body(), id="admin-body"),
        ],
        width="5xl",
    )


@callback(Output("admin-body", "children"), Input("admin-refresh", "n_clicks"), prevent_initial_call=True)
def _refresh(n):
    if not n or not security.is_admin():
        raise PreventUpdate
    return _body(force=True)
