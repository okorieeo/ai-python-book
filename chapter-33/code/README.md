# Chapter 33 code: Evaluating, Monitoring and Improving AI Features

Put these four folders next to Chapter 29's `ai/` package (they import its types, pricing and fake model).

    evals/    cases, checks, judge, runner, report, rollout, demo, run_live, data/chat_basic.jsonl
    feedback/ ratings rules, review sampling, feedback -> eval case; Django model/view/urls
    obs/      scrub, logpolicy, tracing, metrics, alerts, deprecation (+ model_lifecycle.json); Django models/sink/jobs
    costs/    response cache, model router, cost analysis
    .github/workflows/ai-evals.yml

Tests (Python 3.11+, nothing to install). From the folder that contains ai/, evals/, feedback/, obs/ and costs/:

    python -m unittest discover -s . -p "test_*.py" -t .        # 116 tests
    python -m evals.demo                                       # offline demo of the whole eval loop
    python -m obs.deprecation claude-sonnet-5-5 claude-haiku-5-5

Not run while writing the chapter (need the SDK, Django or a key): evals/run_live.py, feedback/models.py,
views.py, urls.py, obs/models.py, sink.py, jobs.py.
Wire-up: add "feedback" and "obs" to INSTALLED_APPS, include feedback.urls under api/v1/, add the lines from
obs/settings_snippet.py, run makemigrations/migrate, and pass `emit=db_sink` when you wrap the stream with `traced`.
