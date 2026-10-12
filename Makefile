.PHONY: help sync test check history participant-dry-run dry-run report

help: ## List available make targets
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "%-24s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install locked dependencies
	uv sync --locked

test: ## Run the test suite
	uv run python -m unittest discover -s tests

check: ## Check the configured event
	uv run python -m ohi_o_reg_tracker check --event hack

history: ## Build registration history
	uv run python -m ohi_o_reg_tracker build-history --event hack

participant-dry-run: ## Preview participants without posting
	uv run python -m ohi_o_reg_tracker preview-participants --event hack

dry-run: ## Render a report without posting
	uv run python -m ohi_o_reg_tracker report --event hack --dry-run

report: ## Post a report to Discord
	uv run python -m ohi_o_reg_tracker report --event hack
