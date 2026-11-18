# Chapter 31 code: Retrieval-Augmented Generation

This chapter builds on Chapter 28: `rag/` imports the `prompts` package (templates, registry,
injection checks, the model adapter). Keep Chapter 28's `prompts/` and `prompt_library/` in your
backend folder, then copy `rag/` and `knowledge/` next to them.

    python -m unittest rag.test_rag             # 103 tests, no network, no database, no Django
    python -m rag.tour                          # real output for each tool (toy embedder)
    python -m rag.cli chunk page.md --size 800  # try the chunker on your own file
    python -m rag.cli search "What does error ERR_4021 mean?"
    python -m rag.cli ask "When do approved refunds appear on my card?"
    python -m rag.cli eval                      # vector vs keyword vs hybrid on 15 questions
    python -m rag.cli lock && python -m rag.cli check   # lock the RAG prompts (rag/prompt_library)

    pip install pgvector voyageai               # for Postgres and the live commands
    export VOYAGE_API_KEY=... ANTHROPIC_API_KEY=...     # never commit keys (Chapter 17)
    python -m rag.cli live

The RAG prompts live in `rag/prompt_library` with their own LOCK.json, so Chapter 28's library and
tests are untouched.

`HashingEmbedder` and `demo_answer_model` are toys for tests and demos. They are not real models.

`knowledge/` is a Django app (models, pgvector store, Celery task, API). Add "knowledge" to
INSTALLED_APPS and run `python manage.py makemigrations knowledge && python manage.py migrate`
(the first migration enables the pgvector extension). It needs Postgres with pgvector, Celery and
the settings shown in section 31.10, and it was not executed when the chapter was written.
