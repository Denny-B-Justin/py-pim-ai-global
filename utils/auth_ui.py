"""Admin sign-in form and auth callbacks shared by gated pages."""
from dash import Input, Output, State, callback, dcc, html, no_update
from dash.exceptions import PreventUpdate

from utils import security
from utils.design import icon


def login_view(what: str) -> html.Div:
    if not security.admin_configured():
        return html.Div(
            [html.H1("Admin access unavailable"), html.P("Admin sign-in is not configured for this deployment.")],
            className="login-box",
        )
    return html.Div(
        [
            html.H1("Admin sign-in"),
            html.P(f"{what} is restricted to administrators."),
            html.Div(
                [
                    dcc.Input(id="login-user", type="text", placeholder="Username", autoComplete="username", maxLength=64, className="text-input slim", autoFocus=True),
                    dcc.Input(id="login-pass", type="password", placeholder="Password", autoComplete="current-password", maxLength=256, className="text-input slim", n_submit=0),
                    html.Button("Sign in", id="login-submit", type="button", className="btn btn-default btn-md", n_clicks=0),
                    html.P(id="login-error", className="login-err", role="alert"),
                ],
                className="form",
            ),
        ],
        className="login-box",
    )


def logout_button() -> html.Button:
    return html.Button([icon("log-out", "4"), "Sign out"], id="logout-btn", type="button", className="btn btn-outline btn-sm", n_clicks=0)


@callback(
    Output("auth-tick", "data"),
    Output("login-error", "children"),
    Input("login-submit", "n_clicks"),
    Input("login-pass", "n_submit"),
    State("login-user", "value"),
    State("login-pass", "value"),
    State("auth-tick", "data"),
    prevent_initial_call=True,
)
def _login(clicks, submits, user, password, tick):
    if not (clicks or submits):
        raise PreventUpdate
    ok, message = security.admin_login(user or "", password or "")
    return ((tick or 0) + 1, "") if ok else (no_update, message)


@callback(
    Output("auth-tick", "data", allow_duplicate=True),
    Input("logout-btn", "n_clicks"),
    State("auth-tick", "data"),
    prevent_initial_call=True,
)
def _logout(clicks, tick):
    if not clicks:
        raise PreventUpdate
    security.admin_logout()
    return (tick or 0) + 1
