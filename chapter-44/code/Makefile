.PHONY: check
# One command that says whether the project is healthy. Claude, hooks and CI all run exactly this.
check:
	cd tests && python3 -W error::ResourceWarning -m unittest discover -p "test_*.py"
	python3 tools/validate_claude_config.py
	python3 tools/promptlint.py prompts/weak_vs_strong/*-strong.md prompts/templates/feature.md prompts/templates/bugfix.md prompts/templates/refactor.md
