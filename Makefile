.PHONY: sync test check history participant-dry-run dry-run report

sync:
	uv sync --locked

test:
	uv run python -m unittest discover -s tests

check:
	uv run python -m ohi_o_reg_tracker check --event hack

history:
	uv run python -m ohi_o_reg_tracker build-history --event hack

participant-dry-run:
	uv run python -m ohi_o_reg_tracker preview-participants --event hack

dry-run:
	uv run python -m ohi_o_reg_tracker report --event hack --dry-run

report:
	uv run python -m ohi_o_reg_tracker report --event hack
