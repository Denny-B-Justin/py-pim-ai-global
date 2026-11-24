"""?page=analytics — query log analytics (admin only)."""
from datetime import datetime, timezone

from dash import Input, Output, callback, html
from dash.exceptions import PreventUpdate

from utils import data, security
from utils.auth_ui import login_view, logout_button
from utils.design import alert, container, fmt_int, icon, page_header


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _secs(ms) -> str:
    return f"{_num(ms) / 1000:.1f}s" if _num(ms) else "—"


def _stat(label: str, value, ico: str, warn: bool = False) -> html.Div:
    return html.Div([icon(ico), html.P(value, className="v"), html.P(label, className="l")], className=f"card stat-card{' alert' if warn else ''}")


def _bar(label: str, value: float, total: float, color: str, suffix: str = "") -> html.Div:
    pct = min(100.0, value / total * 100) if total else 0
    return html.Div(
        [
            html.Div([html.Span(label), html.Span(f"{fmt_int(value)}{suffix}")], className="top"),
            html.Div(html.Div(className=f"bar-fill {color}", style={"width": f"{pct:.1f}%"}), className="bar-track"),
        ],
        className="bar-row",
    )


def _kv(label: str, value, unit: str = "") -> html.Div:
    return html.Div([html.P(label, className="k"), html.P([value, html.Small(f" {unit}") if unit else None], className="big")])


def _when(ts) -> str:
    if not isinstance(ts, datetime):
        return "—"
    ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%b %d, %H:%M")


def _body(force: bool = False):
    try:
        d = data.get_analytics(force)
    except Exception:
        return alert("Failed to load analytics. Ensure the query log table exists and the service principal can read it.")
    s = d["summary"]
    total, retrieval, llm = _num(s.get("avg_total_ms")), _num(s.get("avg_retrieval_ms")), _num(s.get("avg_llm_ms"))
    errors = int(_num(s.get("errors")))
    tin, tout = int(_num(s.get("input_tokens"))), int(_num(s.get("output_tokens")))
    top = lambda rows: max([int(_num(r["n"])) for r in rows] or [1])  # noqa: E731

    cards = html.Div(
        [
            _stat("Queries (24h)", fmt_int(s.get("total_queries")), "activity"),
            _stat("Avg Latency", _secs(total), "clock"),
            _stat("Avg Sources Used", f"{_num(s.get('avg_chunks')):.1f}", "zap"),
            _stat("Errors", fmt_int(errors), "alert-triangle", warn=errors > 0),
        ],
        className="stat-grid cols-4",
    )
    panels = html.Div(
        [
            html.Div(
                [
                    html.H3([icon("clock", "4"), "Avg Latency Breakdown"]),
                    html.Div(
                        [
                            _bar("Retrieval", retrieval, total, "teal", "ms"),
                            _bar("LLM Generation", llm, total, "purple", "ms"),
                            _bar("Other", max(total - retrieval - llm, 0), total, "blue", "ms"),
                            html.Div(f"Total: {fmt_int(total)}ms", className="bar-total"),
                        ],
                        className="body",
                    ),
                ],
                className="card panel bars",
            ),
            html.Div(
                [
                    html.H3([icon("database", "4"), "Usage (24h)"]),
                    html.Div(
                        [
                            html.P("By collection", className="k"),
                            *[_bar(r["name"], int(_num(r["n"])), top(d["by_collection"]), "blue") for r in d["by_collection"]],
                            html.P("By model", className="k"),
                            *[_bar(r["name"], int(_num(r["n"])), top(d["by_model"]), "purple") for r in d["by_model"]],
                        ],
                        className="body",
                    ),
                ],
                className="card panel bars",
            ),
            html.Div(
                [
                    html.H3([icon("cpu", "4"), "Token Usage (24h)"]),
                    html.Div([_kv("Input Tokens", fmt_int(tin)), _kv("Output Tokens", fmt_int(tout)), _kv("Total", fmt_int(tin + tout))], className="body"),
                ],
                className="card panel",
            ),
        ],
        className="panel-grid",
    )
    rows = [
        html.Tr(
            [
                html.Td(r["query_text"], title=r["query_text"], className="q"),
                html.Td(r["collection"], className="s"),
                html.Td(r["model"], className="s"),
                html.Td(_secs(r["total_ms"]), className="r num"),
                html.Td(f"{fmt_int(r['retrieval_ms'])}ms", className="r num"),
                html.Td(_secs(r["llm_ms"]), className="r num"),
                html.Td(fmt_int(_num(r["input_tokens"]) + _num(r["output_tokens"])), className="r num"),
                html.Td(_when(r["created_at"]), className="s"),
            ],
            className="err" if r.get("error") else "",
        )
        for r in d["recent"]
    ]
    recent = (
        html.Div(
            html.Table(
                [
                    html.Thead(html.Tr([html.Th(t, className="r" if t in ("Total", "Search", "LLM", "Tokens") else "") for t in ("Query", "Collection", "Model", "Total", "Search", "LLM", "Tokens", "Time (UTC)")])),
                    html.Tbody(rows),
                ],
                className="log-table",
            ),
            className="table-wrap",
        )
        if rows
        else html.P("No queries logged yet. Submit a query to see analytics here.", className="muted", style={"marginTop": "1rem", "fontSize": "0.875rem"})
    )
    return [cards, panels, html.Div([html.H3("Recent Queries"), recent], className="recent")]


def layout(params: dict):
    if not security.is_admin():
        return login_view("Query analytics")
    return container(
        [
            html.Div(
                [
                    html.Div(page_header("Observability", "Query Analytics", "Performance metrics, token usage, and usage patterns for the last 24 hours.")),
                    html.Div(
                        [html.Button([icon("refresh-cw", "4"), "Refresh"], id="analytics-refresh", type="button", className="btn btn-outline btn-sm", n_clicks=0), logout_button()],
                        className="head-actions",
                    ),
                ],
                className="head-row",
            ),
            html.Div(_body(), id="analytics-body"),
        ],
        width="6xl",
    )


@callback(Output("analytics-body", "children"), Input("analytics-refresh", "n_clicks"), prevent_initial_call=True)
def _refresh(n):
    if not n or not security.is_admin():
        raise PreventUpdate
    return _body(force=True)
