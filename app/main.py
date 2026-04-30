import logging

import streamlit as st
from dotenv import load_dotenv

from app.core.config import get_settings
from app.core.seed import seed_default_config


load_dotenv()


@st.cache_resource
def _bootstrap() -> dict:
    s = get_settings()
    logging.basicConfig(
        level=getattr(logging, s.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    )
    if s.seed_on_startup:
        try:
            seed_default_config()
        except Exception as e:
            logging.exception("Seed failed: %s", e)
    return {"ready": True}


_bootstrap()

st.set_page_config(page_title="Promptify · Concrete Tracker", layout="wide")
st.title("Promptify · Concrete Tracker")
st.caption(
    "Test and improve OCR prompts for concrete delivery notes. "
    "Switch between Mistral 2505, Mistral 2512, and Azure DI + GPT-4.1-mini."
)

st.markdown(
    """
**What you can do here:**

- **Playground** — upload one BL, edit the prompt and field schema, pick a model, run it, see the extracted JSON.
- (Coming in later phases) Versioned configs, batch evaluation against a labelled dataset, dataset upload & ground-truth.

Use the left sidebar to navigate.
"""
)

with st.expander("Environment", expanded=False):
    s = get_settings()
    st.code(
        f"DATABASE_URL          = {s.database_url}\n"
        f"MISTRAL_ENDPOINT      = {s.azure_mistralocr_endpoint or '(not set)'}\n"
        f"DI_ENDPOINT           = {s.azure_document_intelligence_endpoint or '(not set)'}\n"
        f"OPENAI_ENDPOINT       = {s.azure_openai_endpoint or '(not set)'}\n"
        f"OPENAI_DEPLOYMENT     = {s.azure_openai_deployment_name}\n"
        f"OPENAI_API_VERSION    = {s.azure_openai_api_version}\n"
        f"SEED_ON_STARTUP       = {s.seed_on_startup}\n",
        language="ini",
    )
