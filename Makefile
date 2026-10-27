# Reproduce everything that is published from this repository.
#
#   make reproduce   generate data, lint, test, re-score every saved eval report
#                    offline, then rewrite results/metrics.json and the README
#                    results block
#   make ci          the same checks without writing: fails if the committed
#                    metrics or README block are stale (this is what CI runs)
#   make live ...    run a NEW live eval (calls the LLM API; needs a key and a
#                    preregistration). A finished report is never overwritten.
#
# On Windows without make, run the commands under each target directly.

PYTHON ?= python

.PHONY: reproduce ci data lint test rescore publish check live

reproduce: data lint test publish

ci: data lint test check

data:
	$(PYTHON) generate_sample_data.py

lint:
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest -q

# Re-execute every stored question trial of one report and compare summaries.
rescore:
	@for f in results/eval_report*.json; do \
	  echo "re-scoring $$f"; $(PYTHON) -m evals.run_eval --offline --report $$f > /dev/null || exit 1; \
	done

publish:
	$(PYTHON) -m evals.publish --write

check:
	$(PYTHON) -m evals.publish --check

# make live REPORT=results/eval_report_v3.json PREREG=evals/PREREGISTRATION_v3.md [MODES=pandas] [INTERVAL=7]
live:
	@test -n "$(REPORT)" -a -n "$(PREREG)" || { echo "usage: make live REPORT=results/eval_report_vN.json PREREG=evals/PREREGISTRATION_vN.md"; exit 2; }
	$(PYTHON) -m evals.run_eval --live --report $(REPORT) --prereg $(PREREG) --modes $(or $(MODES),sql,pandas) --min-interval $(or $(INTERVAL),7)
