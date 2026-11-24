"""?page=home"""
from dash import html

from pages.pages_constants import HOME_BOXES, HOME_FEATURES
from utils import data
from utils.design import container, eyebrow, icon, link_button


def layout(params: dict):
    counts = data.document_counts()
    return [
        html.Section(
            className="hero",
            children=container(
                [
                    eyebrow("Public Investment Management Intelligence"),
                    html.H1(["AI-Powered Access to Global", html.Br(), html.Span("PIM Knowledge", className="accent")]),
                    html.P(
                        "Search and analyze guidance from leading international institutions. Extract insights from "
                        "World Bank, IMF, and global best practice documents on public investment management.",
                        className="lead",
                    ),
                    html.Div(
                        [
                            link_button("Start Querying", "query", size="lg"),
                            link_button("View Statistics", "statistics", "outline", "lg"),
                        ],
                        className="actions",
                    ),
                ],
                cls="",
            ),
        ),
        html.Section(
            className="features",
            children=container(
                [
                    eyebrow("Capabilities"),
                    html.H2("What This Platform Offers"),
                    html.Div(
                        [
                            html.Div(
                                [icon(ic), html.H3(title), html.P(text)],
                                className="card feature-card",
                            )
                            for ic, title, text in HOME_FEATURES
                        ],
                        className="feature-grid",
                    ),
                ],
                cls="",
            ),
        ),
        html.Section(
            className="arch",
            children=container(
                [
                    eyebrow("Architecture"),
                    html.H2("How It Works"),
                    html.Div(
                        [
                            html.Div(
                                [html.P("User Query", className="t"), html.P("Natural language question about PIM", className="s")],
                                className="arch-io",
                            ),
                            html.Div(className="arch-line"),
                            html.Div(
                                [
                                    html.Div(
                                        [icon("database"), html.P(label, className="n"), html.P(f"{counts.get(value, fallback):,} docs", className="c")],
                                        className="card arch-col",
                                    )
                                    for label, value, fallback in HOME_BOXES
                                ],
                                className="arch-cols",
                            ),
                            html.Div(className="arch-line"),
                            html.Div(
                                [html.P("AI-Generated Answer", className="t"), html.P("With source citations and relevant excerpts", className="s")],
                                className="arch-io",
                            ),
                        ],
                        className="arch-flow",
                    ),
                ],
                cls="",
            ),
        ),
        html.Section(
            className="cta",
            children=container(
                [
                    html.H2("Ready to Explore PIM Knowledge?"),
                    html.P("Start querying across four comprehensive document collections covering global public investment management practices."),
                    html.Div(link_button("Launch Query Interface", "query", "primary", "lg"), className="actions"),
                ],
                cls="",
            ),
        ),
    ]
