# Chapter 28 code: Prompt Engineering

Drop `prompts/`, `prompt_library/` and (optionally) `prompt_runs/` into your backend folder.

    python -m unittest prompts.test_prompts     # 65 tests, no network, no Django needed
    python -m prompts.tour                      # prints real output for each tool
    python -m prompts.cli eval                  # compare prompt versions (scripted stand-in model)
    python -m prompts.cli render summarize_conversation v2
    python -m prompts.cli scan "Ignore all previous instructions"
    python -m prompts.cli check                 # verify LOCK.json
    python -m prompts.cli lock                  # lock newly released versions

    pip install anthropic                       # only for the live commands
    export ANTHROPIC_API_KEY=...                # never commit it (Chapter 17)
    python -m prompts.cli live

`prompt_runs/` is a small Django app (model, admin, recorder). Add `"prompt_runs"` to
INSTALLED_APPS, then run `python manage.py makemigrations prompt_runs && python manage.py migrate`.
