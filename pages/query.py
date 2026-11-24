"""?page=query — RAG query interface."""
import time
from datetime import datetime, timezone

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from constants import (
    COLLECTION_BY_ID,
    COLLECTIONS,
    DEFAULT_COLLECTION_ID,
    DEFAULT_MODEL_ID,
    LLM_TIMEOUT_S,
    MAX_QUERY_LENGTH,
    MODEL_BY_ID,
    MODELS,
    PROVIDER_LABEL,
    RATE_LIMIT_QUERY,
)
from pages.pages_constants import HISTORY_KEY_LIMIT, QUERY_PLACEHOLDER
from utils import rag, state
from utils.design import alert, button, container, icon, link, page_header
from utils.security import clean_text, client_ip, ip_hash, rate_limited, session_id


def _select(field_id: str, label: str, options: list[dict], value: str, helptext: str):
    return html.Div(
        [
            html.Label(label, htmlFor=field_id, className="field-label"),
            html.Div(
                dcc.Dropdown(id=field_id, options=options, value=value, clearable=False, searchable=False),
                className="select-wrap",
            ),
            html.P(helptext, id=f"{field_id}-desc", className="field-help"),
        ]
    )


def layout(params: dict, history: list | None = None):
    col_id = params.get("collection") if params.get("collection") in COLLECTION_BY_ID else DEFAULT_COLLECTION_ID
    return container(
        [
            *page_header(
                "RAG Query Interface",
                "Search Document Collections",
                "Select a document collection, choose an AI model, and submit your question. The system will retrieve "
                "relevant passages and generate an AI-powered answer with source citations.",
            ),
            html.Div(history_view(history), id="q-history-box"),
            html.Div(
                className="query-form",
                children=[
                    html.Div(
                        className="field-grid",
                        children=[
                            _select(
                                "q-collection",
                                "Document Collection",
                                [{"label": c.label, "value": c.id} for c in COLLECTIONS],
                                col_id,
                                COLLECTION_BY_ID[col_id].description,
                            ),
                            _select(
                                "q-model",
                                "AI Model",
                                [{"label": f"{m.label} ({PROVIDER_LABEL[m.provider]})", "value": m.id} for m in MODELS],
                                DEFAULT_MODEL_ID,
                                MODEL_BY_ID[DEFAULT_MODEL_ID].description,
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            html.Label("Your Question", htmlFor="q-input", className="field-label"),
                            html.Div(
                                [
                                    dcc.Textarea(
                                        id="q-input",
                                        value="",
                                        rows=3,
                                        maxLength=MAX_QUERY_LENGTH,
                                        placeholder=QUERY_PLACEHOLDER,
                                        className="text-input",
                                    ),
                                    html.Span(id="q-hint", className="textarea-hint"),
                                ],
                                className="textarea-wrap",
                            ),
                        ]
                    ),
                    html.Button(
                        [
                            html.Span([icon("send"), "Submit Query"], className="label-idle"),
                            html.Span([icon("loader-2", cls="spin"), html.Span("Searching & Generating...", role="status")], className="label-busy"),
                        ],
                        id="q-submit",
                        type="button",
                        className="btn btn-default btn-lg btn-submit",
                        disabled=True,
                    ),
                ],
            ),
            html.Div(id="q-error"),
            html.Div(id="q-results", **{"aria-live": "polite"}),
            dcc.Store(id="q-job"),
            dcc.Store(id="q-busy", data=False),
            dcc.Interval(id="q-poll", interval=1500, disabled=True),
        ],
        width="5xl",
    )


# ── Client-side UI state ─────────────────────────────────────────────────
dash.clientside_callback(
    dash.ClientsideFunction("pim", "hint"), Output("q-hint", "children"), Input("q-input", "value")
)
dash.clientside_callback(
    dash.ClientsideFunction("pim", "submitState"),
    Output("q-submit", "disabled"),
    Output("q-submit", "className"),
    Input("q-input", "value"),
    Input("q-busy", "data"),
)


@callback(Output("q-collection-desc", "children"), Input("q-collection", "value"))
def _collection_desc(value):
    return COLLECTION_BY_ID.get(value, COLLECTIONS[0]).description


@callback(Output("q-model-desc", "children"), Input("q-model", "value"))
def _model_desc(value):
    return MODEL_BY_ID.get(value, MODELS[0]).description


# ── History (browser local storage) ──────────────────────────────────────
def _entries(raw) -> list[dict]:
    """Validate history read back from browser storage (client-controlled)."""
    out = []
    for e in raw if isinstance(raw, list) else []:
        if not isinstance(e, dict):
            continue
        ts = e.get("timestamp")
        out.append(
            {
                "query": clean_text(e.get("query"), MAX_QUERY_LENGTH),
                "collection": e.get("collection") if e.get("collection") in COLLECTION_BY_ID else DEFAULT_COLLECTION_ID,
                "model": e.get("model") if e.get("model") in MODEL_BY_ID else DEFAULT_MODEL_ID,
                "timestamp": int(ts) if isinstance(ts, (int, float)) and 0 <= ts < 4e12 else 0,
            }
        )
    return [e for e in out if e["query"]][:HISTORY_KEY_LIMIT]


def history_view(raw):
    entries = _entries(raw)
    if not entries:
        return None
    items = []
    for i, e in enumerate(entries):
        label = COLLECTION_BY_ID[e["collection"]].label
        when = datetime.fromtimestamp(e["timestamp"] / 1000, timezone.utc).strftime("%d %b %Y")
        items.append(
            html.Button(
                html.Div([html.P(e["query"]), html.P(f"{label} · {when}")], className="q"),
                id={"type": "q-hist", "index": i},
                type="button",
                className="history-item",
                n_clicks=0,
            )
        )
    return html.Details(
        className="history",
        children=[
            html.Summary([icon("history"), f"Recent queries ({len(entries)})", icon("chevron-down", "3", "chev")]),
            html.Div(
                className="card history-panel",
                children=[
                    html.Div(
                        [
                            html.Span("Query History", className="t"),
                            html.Button([icon("trash-2", "3"), "Clear"], id="q-hist-clear", type="button", className="history-clear", n_clicks=0),
                        ],
                        className="history-head",
                    ),
                    html.Div(items, className="history-list"),
                ],
            ),
        ],
    )


@callback(Output("q-history-box", "children"), Input("q-history", "data"), prevent_initial_call=True)
def _render_history(entries):
    return history_view(entries)


@callback(Output("q-history", "data", allow_duplicate=True), Input("q-hist-clear", "n_clicks"), prevent_initial_call=True)
def _clear_history(n):
    if not n:
        raise PreventUpdate
    return []


@callback(
    Output("q-input", "value"),
    Output("q-collection", "value"),
    Output("q-model", "value"),
    Input({"type": "q-hist", "index": ALL}, "n_clicks"),
    State("q-history", "data"),
    prevent_initial_call=True,
)
def _apply_history(_clicks, entries):
    trig = ctx.triggered_id
    if not trig or not ctx.triggered[0]["value"]:
        raise PreventUpdate
    try:
        e = _entries(entries)[trig["index"]]
    except (IndexError, TypeError, KeyError):
        raise PreventUpdate
    return e["query"], e["collection"], e["model"]


# ── Submit / poll ────────────────────────────────────────────────────────
@callback(
    Output("q-job", "data"),
    Output("q-poll", "disabled"),
    Output("q-busy", "data"),
    Output("q-results", "children"),
    Output("q-error", "children"),
    Output("q-history", "data"),
    Input("q-submit", "n_clicks"),
    State("q-input", "value"),
    State("q-collection", "value"),
    State("q-model", "value"),
    State("q-history", "data"),
    prevent_initial_call=True,
)
def _submit(n_clicks, text, collection_id, model_id, history):
    if not n_clicks:
        raise PreventUpdate
    query = clean_text(text, MAX_QUERY_LENGTH)
    fail = lambda msg: (no_update, True, False, no_update, alert(msg), no_update)  # noqa: E731
    if not query:
        return fail("Please enter a question.")
    if collection_id not in COLLECTION_BY_ID or model_id not in MODEL_BY_ID:
        return fail("Invalid collection or model.")
    blocked, retry = rate_limited("query", *RATE_LIMIT_QUERY)
    if blocked:
        return fail(f"Too many requests. Please wait {retry} seconds and try again.")
    job_id = rag.submit(session_id(), query, collection_id, model_id, ip_hash(client_ip()))
    entry = {"query": query, "collection": collection_id, "model": model_id, "timestamp": int(time.time() * 1000)}
    kept = [h for h in _entries(history) if h["query"] != query]
    return job_id, False, True, [], None, [entry, *kept][:HISTORY_KEY_LIMIT]


def _finished(error=None, results=None):
    return results if results is not None else [], alert(error) if error else None, True, False


@callback(
    Output("q-results", "children", allow_duplicate=True),
    Output("q-error", "children", allow_duplicate=True),
    Output("q-poll", "disabled", allow_duplicate=True),
    Output("q-busy", "data", allow_duplicate=True),
    Input("q-poll", "n_intervals"),
    State("q-job", "data"),
    prevent_initial_call=True,
)
def _poll(_n, job_id):
    if not job_id:
        raise PreventUpdate
    job = state.job_get(job_id, session_id())
    if job is None:
        return _finished("This result has expired. Please submit your question again.")
    if job["status"] == "running":
        if time.time() - job["created"] > LLM_TIMEOUT_S * 2 + 60:
            return _finished("The request took too long. Please try again.")
        raise PreventUpdate
    if job["status"] == "error":
        return _finished(job.get("error", "Something went wrong."))
    return _finished(results=_render_result(job_id, job))


# ── Rendering ────────────────────────────────────────────────────────────
def _render_result(job_id: str, job: dict):
    answer, meta, sources = job["answer"], job["meta"], job["sources"]
    export = f"_export/{job_id}.doc"
    tokens = (meta.get("input_tokens") or 0) + (meta.get("output_tokens") or 0)
    meta_bits = [
        html.Span([icon("cpu", "3"), meta.get("model", "")]),
        html.Span([icon("clock", "3"), f"{meta.get('latency_ms', 0) / 1000:.1f}s"]),
    ]
    if meta.get("input_tokens") and meta.get("output_tokens"):
        meta_bits.append(html.Span(f"{tokens} tokens"))
    cards = []
    for s in sources:
        bits = [b for b in (s["collection"], s["country"], str(s["year"]) if s["year"] else "", s["pages"], s["section"]) if b]
        cards.append(
            html.Div(
                className="source-card",
                children=html.Div(
                    className="row",
                    children=[
                        icon("file-text"),
                        html.Div(
                            [
                                html.P([s["file"], html.Span(" · ".join(bits))] if bits else s["file"], className="name"),
                                html.P(s["excerpt"], className="ex"),
                            ],
                            className="body",
                        ),
                    ],
                ),
            )
        )
    return html.Div(
        className="results",
        children=[
            html.Div(
                className="card answer-card",
                role="region",
                **{"aria-label": "AI-generated answer"},
                children=[
                    html.Div(
                        className="answer-head",
                        children=[
                            html.Div(
                                [
                                    html.H2("Answer"),
                                    html.Button(
                                        [
                                            html.Span([icon("copy", "3"), "Copy"], className="idle"),
                                            html.Span([icon("check", "3"), "Copied"], className="copied"),
                                        ],
                                        type="button",
                                        className="chip-btn",
                                        **{"data-copy": answer, "aria-label": "Copy answer to clipboard"},
                                    ),
                                    html.A(
                                        [icon("download", "3"), "Word"],
                                        href=export,
                                        className="chip-btn",
                                        title="Download as Word document (.doc)",
                                        **{"aria-label": "Download answer as Word document"},
                                    ),
                                ],
                                className="left",
                            ),
                            html.Div(meta_bits, className="answer-meta"),
                        ],
                    ),
                    html.Div(dcc.Markdown(answer, dedent=False, link_target="_blank"), className="answer-body md"),
                ],
            ),
            html.Div(
                [html.H3(f"Sources ({len(sources)})"), html.Div(cards, className="sources-list")],
                className="sources",
                role="region",
                **{"aria-label": "Source documents"},
            )
            if sources
            else None,
            html.Div(
                className="results-foot",
                children=[
                    html.P("Save this result as a Word document for sharing or archiving."),
                    html.A(
                        [icon("download"), "Download as Word"],
                        href=export,
                        className="btn btn-outline btn-sm",
                        **{"aria-label": "Download answer as Word document"},
                    ),
                ],
            ),
        ],
    )
