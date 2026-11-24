"""?page=release-notes"""
from dash import html

from pages.pages_constants import RELEASES
from utils.design import container, page_header


def layout(params: dict):
    releases = [
        html.Div(
            className="release",
            children=[
                html.Div(className="dot"),
                html.Div(
                    [
                        html.Span(r["version"], className="ver"),
                        html.Span(r["date"], className="date"),
                        html.Span(r["type"], className=f"badge {r['type']}"),
                    ],
                    className="meta",
                ),
                html.H2(r["title"]),
                html.Ul([html.Li([html.Span(className="b"), html.Span(item)]) for item in r["items"]]),
            ],
        )
        for r in RELEASES
    ]
    return container(
        [
            *page_header("Changelog", "Release Notes", "Track the latest updates, new features, and improvements to the PIM AI Global platform."),
            html.Div(releases, className="timeline"),
        ],
        width="4xl",
    )
