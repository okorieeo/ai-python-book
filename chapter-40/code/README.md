# Chapter 40 code: Debugging Like a Professional

    core/debugging/      plain Python, no Django: traceparse, sourcemap, logtriage, sqlcheck, plancheck, nettiming, asyncdebug
    core/test_debugging.py   36 unittest tests:  python -m unittest core.test_debugging -v
    lab/bugs/            five seeded bugs (read the symptom in each file's docstring)
    lab/solutions/       reference fixes (look only after you have tried)
    lab/test_lab.py      python -m unittest lab.test_lab -v                      (fails on the buggy code, by design)
                         LAB_PACKAGE=lab.solutions python -m unittest lab.test_lab -v    (passes)
    demo/pricing.py      the file used for the pdb session in section 40.3

Log triage from a terminal:  python -m core.debugging.logtriage < web.log
The Django, Celery and Channels snippets in the chapter were checked for syntax only.
