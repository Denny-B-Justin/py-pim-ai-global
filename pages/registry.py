"""?page=registry — document registry (state in URL: collection, country)."""
from dash import dcc, html

from constants import REGISTRY_COLLECTIONS
from utils import data
from utils.design import alert, as_of_text, container, fmt_int, href, icon, link, page_header

_COLLECTION_BY_ID = {c.id: c for c in REGISTRY_COLLECTIONS}
_STATUS = {
    "embedded": ("embedded", "check-circle-2", "Embedded"),
    "catalogued": ("catalogued", "circle", "Catalogued"),
    "failed": ("failed", "alert-circle", "Failed"),
}


def _status(value) -> html.Span:
    cls, ico, label = _STATUS.get(str(value or "").lower(), ("other", "circle", str(value or "—")))
    return html.Span([icon(ico, "3"), label], className=f"status {cls}")


def _dash() -> html.Span:
    return html.Span("—", className="dash")


def _countries(rows: list[dict]) -> list[dict]:
    agg: dict[str, dict] = {}
    for r in rows:
        name = (r.get("country") or "").strip()
        if not name:
            continue
        a = agg.setdefault(name, {"country": name, "total": 0, "embedded": 0})
        a["total"] += 1
        a["embedded"] += str(r.get("status")).lower() == "embedded"
    return sorted(agg.values(), key=lambda a: a["country"].lower())


def _row(r: dict) -> html.Tr:
    year, chunks = r.get("year"), r.get("chunks")
    doc = r.get("document") or ""
    return html.Tr(
        [
            html.Td(r.get("country") or _dash()),
            html.Td(str(int(year)) if year else _dash()),
            html.Td(html.Span(doc, title=doc)),
            html.Td(_status(r.get("status"))),
            html.Td(fmt_int(chunks) if chunks and int(chunks) > 0 else "", className="r"),
        ]
    )


def layout(params: dict):
    col = _COLLECTION_BY_ID.get(params.get("collection")) or REGISTRY_COLLECTIONS[0]
    head = html.Div(
        [
            *page_header(
                "Document Registry",
                "Registry",
                "Browse every catalogued report across the four collections. Filter by country; click into a country to see its full report history.",
                "lead-3xl",
            ),
            html.P(as_of_text(), className="asof"),
        ]
    )
    tabs = html.Div(
        [link(c.label, "registry", f"reg-tab{' active' if c.id == col.id else ''}", collection=c.id) for c in REGISTRY_COLLECTIONS],
        className="reg-tabs",
    )
    try:
        payload = data.get_registry(col.value)
    except Exception:
        return container([head, tabs, alert("Failed to load registry. Please try again later.")])

    rows, countries = payload["rows"], _countries(payload["rows"])
    selected = params.get("country") if params.get("country") in {c["country"] for c in countries} else None
    shown = [r for r in rows if (r.get("country") or "").strip() == selected] if selected else rows

    items = [
        link("All countries", "registry", f"country-item{'' if selected else ' active'}", collection=col.id),
        *[
            dcc.Link(
                [html.Span(c["country"]), html.Span(c["total"], className="n")],
                href=href("registry", collection=col.id, country=None if c["country"] == selected else c["country"]),
                className=f"country-item{' active' if c['country'] == selected else ''}",
            )
            for c in countries
        ],
    ]
    rail = html.Aside(
        [html.Div([html.H2(f"Country ({len(countries)})"), html.Div(items, className="country-list")])] if countries else [],
        className="rail",
    )
    count = len(shown)
    table = html.Div(
        html.Div(
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("Country"),
                                html.Th("Year"),
                                html.Th("Document"),
                                html.Th("Status"),
                                html.Th("Chunks", className="r"),
                            ]
                        )
                    ),
                    html.Tbody(
                        [_row(r) for r in shown]
                        or [html.Tr(html.Td("No documents match these filters.", colSpan=5, className="empty"))]
                    ),
                ],
                className="reg-table",
            ),
            className="table-scroll",
        ),
        className="table-card",
    )
    note = (
        html.P(f"Showing the first {fmt_int(len(rows))} documents.", className="asof") if payload.get("truncated") else None
    )
    main = html.Div(
        [
            html.P(
                f"{count:,} report{'' if count == 1 else 's'} in {col.label}" + (f" • {selected}" if selected else ""),
                className="reg-count",
            ),
            table,
            note,
            html.Div(
                [
                    html.P(
                        f"{len(countries)} countries • {sum(c['embedded'] for c in countries)} embedded",
                        className="muted",
                    ),
                    link("Query this collection →", "query", collection=col.id),
                ],
                className="reg-foot",
            ),
        ]
    )
    return container([head, tabs, html.Div([rail, main], className="reg-grid")])
