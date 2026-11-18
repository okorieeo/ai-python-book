# Chapter 41 code: ai_verify

Small tools for checking what an AI assistant gave you. Standard library only.

    pip install -r requirements.txt
    python -m pytest -q ai_verify                       # the toolkit's own 61 tests

    python -m ai_verify smells sample/test_weak.py --target sample/billing_math.py
    python -m ai_verify mutate --project sample --module billing_math.py \
        --cmd "python -m pytest -x -q -p no:cacheprovider test_weak.py"
    python -m ai_verify imports examples/ai_snippet.py  # invented names
    python -m ai_verify bugreport --title T --expected E --actual A --traceback tb.txt
    python -m ai_verify package requests                # needs internet (PyPI)

For your own project run `imports` from its root, or pass `--root` and `--django-settings`.

- `ai_verify/hallucination.py`  do the imports, attributes and keywords exist?
- `ai_verify/smells.py`         weak-test patterns (hints, not verdicts)
- `ai_verify/mutation.py`       break the code on purpose; do the tests notice?
- `ai_verify/bugreport.py`      redacted, trimmed bug report
- `ai_verify/packages.py`       does this package exist on PyPI?
- `sample/`, `examples/`        the module, weak and strong tests, and snippets used in the chapter
