# OHI/O Registration Tracker

## Setup

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/), then run
`uv sync --locked`. Set `QUALTRICS_API_KEY` and `DISCORD_WEBHOOK_URL` for report
commands. You may put them in the ignored root `.env` file:

```text
QUALTRICS_API_KEY=your-key
DISCORD_WEBHOOK_URL=your-webhook-url
```

GitHub Actions uses `QUALTRICS_API_KEY` and per-event webhook secrets such as
`HACKOHIO_DISCORD_WEBHOOK_URL`.

## Events and history

Profiles live in `events.toml`. Each profile contains the event and Qualtrics
IDs plus a `history` section. Put the two raw historical exports at the
configured paths under ignored `private/`, then run:

```sh
uv run python -m ohi_o_reg_tracker build-history --event KEY
```

Commit only the resulting `history/*.csv`; never commit raw exports.

## Operations

```sh
uv run python -m ohi_o_reg_tracker check --event KEY
uv run python -m ohi_o_reg_tracker report --event KEY --dry-run
uv run python -m ohi_o_reg_tracker report --event KEY
```

The dry run writes `artifacts/KEY.png`. Add ready event keys and webhook secret
names to the workflow matrix to activate them; remove them to deactivate them.

Failures are reported by the command and GitHub Actions logs. Rotate credentials
through the relevant Qualtrics/Discord settings and repository secrets.

## GitHub Actions configuration

The workflow is defined in `.github/workflows/registration-reports.yml`. It runs
every day at 9:00 AM and 8:00 PM Eastern, and can also be started manually from
the repository's **Actions** tab.

Add these as repository secrets under **Settings → Secrets and variables →
Actions**:

- `QUALTRICS_API_KEY` — shared Qualtrics API key.
- `HACKOHIO_DISCORD_WEBHOOK_URL` — HackOHI/O channel webhook URL.

The webhook secret name is selected by the event matrix in the workflow and
passed to the application as `DISCORD_WEBHOOK_URL`. Add a separate webhook
secret and matrix entry for each additional active event.

To test the setup, open **Actions → Registration reports → Run workflow**. The
job logs show progress through Qualtrics exports, quota requests, chart
generation, and Discord delivery.

**Never** put secret values in `events.toml`, workflow files, logs, or commits.
GitHub may disable scheduled workflows in public repositories after 60 days
without repository activity, so verify that the workflow is enabled before each
registration season.
