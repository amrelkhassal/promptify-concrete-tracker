from app.core.config import get_settings


def get_current_user() -> str:
    """
    Resolve the current user's email.

    On Azure App Service Easy Auth, Streamlit receives identity via headers
    (`X-MS-CLIENT-PRINCIPAL-NAME`). Streamlit exposes them through
    `st.context.headers`. Locally, fall back to LOCAL_DEV_USER.
    """
    try:
        import streamlit as st

        headers = getattr(st, "context", None)
        if headers is not None:
            h = getattr(headers, "headers", {}) or {}
            for key in ("X-MS-CLIENT-PRINCIPAL-NAME", "x-ms-client-principal-name"):
                if h.get(key):
                    return h[key]
    except Exception:
        pass

    return get_settings().local_dev_user
