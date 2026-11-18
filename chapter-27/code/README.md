# Chapter 27 code: the AI Lab

Framework-independent helpers for the chapter. Nothing here imports Django.

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # then add your key, and export the variables
    python -m pytest -q ai_lab  # works with no key and no network
    python -m ai_lab.lab --help

Files: `ai_lab/catalog.py` (models and prices), `cost.py` (tokens to dollars),
`tokens.py` (estimates and exact counts), `providers.py` (one interface over Claude,
OpenAI and local servers), `embeddings.py` (vectors and similarity), `router.py`
(pick the cheapest model that fits a job), `lab.py` (command line).
