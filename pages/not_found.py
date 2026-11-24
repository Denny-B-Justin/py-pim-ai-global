"""Unknown ?page= values"""
from dash import html

from utils.design import icon, link_button


def layout(params: dict):
    return html.Div(
        className="nf",
        children=[
            html.Div(icon("search"), className="bubble"),
            html.H1("Page Not Found"),
            html.P(
                "The page you're looking for doesn't exist or has been moved. Try searching our document "
                "collections or head back to the home page."
            ),
            html.Div(
                [
                    link_button([icon("search"), "Search Documents"], "query", size="lg"),
                    link_button([icon("home"), "Home"], "home", "outline", "lg"),
                ],
                className="actions",
            ),
            html.Button([icon("arrow-left"), "Go back"], type="button", className="back", **{"data-back": "1"}),
        ],
    )
