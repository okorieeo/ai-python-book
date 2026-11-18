# Chapter 30 code: agent_kit

Tools, a guarded agent loop and human approval. Framework-independent: nothing here imports Django.
It builds on the Chapter 27 `ai_lab` folder (token usage, prices, the model catalog), so copy
both folders into `backend/`:

    cp -r chapter_27_code/ai_lab chapter_30_code/agent_kit backend/
    cd backend
    pip install -r requirements.txt
    python -m pytest -q agent_kit             # no key, no network
    python -m agent_kit.walkthrough           # a scripted run, offline
    python -m agent_kit.walkthrough --decline
    python -m agent_kit.demo "Which of my chats mention eggs?"   # needs ANTHROPIC_API_KEY

Files: `tools.py` (Tool, registry, validation), `policy.py` (limits, roles, approval rules),
`state.py` (pausable run state), `agent.py` (the loop), `demo_app.py` (an in-memory chat store with
five tools), `demo.py` (terminal demo), `fake_api.py` (scripted fake Claude API for tests),
`trace.py` (readable transcripts), `walkthrough.py` (offline demo).
