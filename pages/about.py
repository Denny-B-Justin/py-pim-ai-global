"""?page=about"""
from dash import html

from pages.pages_constants import ABOUT_COLLECTIONS, ABOUT_INTRO, ABOUT_STACK
from utils.design import container, eyebrow


def layout(params: dict):
    return container(
        [
            eyebrow("About"),
            html.H1("PIM AI Global", className="page-title"),
            html.Div(
                [
                    html.P(ABOUT_INTRO),
                    html.H2("Document Collections"),
                    html.Div(
                        [html.Div([html.H3(title), html.P(text)], className="about-card") for title, text in ABOUT_COLLECTIONS],
                        className="about-cols",
                    ),
                    html.H2("Technology Stack"),
                    html.Ul([html.Li([html.Strong(f"{k}:"), f" {v}"]) for k, v in ABOUT_STACK], className="about-list"),
                ],
                className="about-body",
            ),
        ],
        width="4xl",
    )
