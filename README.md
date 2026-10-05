# OHI/O Registration Tracker

## Setup

Install Python 3.11+ and [uv](https://docs.astral.sh/uv/), then run
`uv sync --locked`. Set the credentials required by each event's configured
sources for report commands. You may put them in the ignored root `.env` file:

```text
QUALTRICS_API_KEY=your-key
GOOGLE_SHEETS_API_SECRET=your-shared-secret
DISCORD_WEBHOOK_URL=your-webhook-url
```

GitHub Actions maps `QUALTRICS_API_KEY`, the optional
`GOOGLE_SHEETS_API_SECRET`, and per-event webhook secrets such as
`HACKOHIO_DISCORD_WEBHOOK_URL` into the runtime environment.

## Events and history

Profiles live in `events.toml`. Each profile contains the event and Qualtrics
IDs plus a `history` section. Put the two raw historical exports at the
configured paths under ignored `private/`, then run:

```sh
uv run python -m ohi_o_reg_tracker build-history --event KEY
```

Commit only the resulting `history/*.csv`; never commit raw exports. Optional
`participant_trends` entries in a profile add additional participant-only
comparison lines, such as the committed 2024 trend alongside the 2025 history.

### HackOHI/O participant counts

The HackOHI/O profile uses a professional survey in addition to the existing
participant survey. Its configuration includes:

```toml
professional_survey_id = "SV_29LPFsT2mjRtsMe"
marion_quota_id = "QO_lv4lRthwrF55UBH"
```

Participant and mentor/judge current counts come from their EndDate exports.
For HackOHI/O, the participant total combines the existing participant survey
and professional survey exports. The Marion quota belongs to the existing
participant survey and is shown as a breakdown. Marion is not added again
because those registrations are already included in the participant export.
Qualtrics exports explicitly exclude responses still in progress. Closed or
expired incomplete responses can still appear in the downloaded export; the
tracker counts only rows with `Finished` set to true.

Past-year comparison lines and historical aggregate files are unchanged.

## Operations

```sh
uv run python -m ohi_o_reg_tracker check --event KEY
uv run python -m ohi_o_reg_tracker report --event KEY --dry-run
uv run python -m ohi_o_reg_tracker report --event KEY
```

The dry run writes `artifacts/KEY.png`. Scheduled repository dispatches run both
events; manual runs let you choose Both, Hack only, or HS only.

Failures are reported by the command and GitHub Actions logs. Rotate credentials
through the relevant Qualtrics/Discord settings and repository secrets.

## GitHub Actions configuration

The workflow is defined in `.github/workflows/registration-reports.yml`. It is
started by a `repository_dispatch` event from the home-server cron job, and can
also be started manually from the repository's **Actions** tab. The workflow
uses the latest commit on the default branch.

Add these as repository secrets under **Settings → Secrets and variables →
Actions**:

- `QUALTRICS_API_KEY` — shared Qualtrics API key when an active event uses Qualtrics.
- `HACKOHIO_DISCORD_WEBHOOK_URL` — HackOHI/O channel webhook URL.
- `HSIO_DISCORD_WEBHOOK_URL` — HighSchool channel webhook URL.
- `HSIO_SHEETS_API_SECRET` — HighSchool Apps Script secret.

The workflow maps each selected event to its webhook secret and, for HighSchool,
its Sheets secret. Scheduled dispatches run both events. Manual runs in
**Actions → Registration reports → Run workflow** offer Both, Hack only, and HS
only; these send live reports to the selected Discord channel(s).

### Home-server cron

Create a fine-grained GitHub token for `hackohio/ohi-o-registration-tracker`
with **Contents: write** permission, and store it on the home server as
`GITHUB_TOKEN`. Do not put the token in the crontab or this repository. The
token only dispatches the workflow; the Qualtrics and Discord secrets remain in
GitHub Actions.

Use a protected script or a crontab entry like this, adjusting the path to the
token file:

```cron
CRON_TZ=America/New_York
7 9,20 * * * /usr/bin/curl --fail --silent --show-error --request POST \
  --url https://api.github.com/repos/hackohio/ohi-o-registration-tracker/dispatches \
  --header 'Accept: application/vnd.github+json' \
  --header 'X-GitHub-Api-Version: 2022-11-28' \
  --header "Authorization: Bearer $(/usr/bin/cat /etc/ohi-o-registration-tracker/github-token)" \
  --data '{"event_type":"registration-report"}' \
  >>/var/log/ohi-o-registration-tracker.log 2>&1
```

Keep the token file readable only by the cron user. A successful dispatch
returns HTTP 204; `curl --fail` makes network or API errors visible in the
server log. The `7`-minute offset is intentional so both daily runs avoid the
top of the hour.

**Never** put secret values in `events.toml`, workflow files, logs, or commits.
Before each registration season, verify that the workflow is enabled, the home
server cron is running, the token has not expired, and the event profiles and
GitHub secrets are current.

## Google Sheets via Apps Script

A Sheets-backed stream uses a public Apps Script web app with a shared secret;
GitHub does not use Google OAuth and the response contains only timestamps. The
Sheet stays private, but the endpoint is not Google-authenticated: protect
script-editor access, rotate an exposed secret, and expect unauthorized calls to
consume some Apps Script quota.

Configure each stream with exactly one provider. For example, a mixed event may
use:

```toml
participant_apps_script_url = "https://script.google.com/macros/s/DEPLOYMENT_ID/exec"
leader_survey_id = "SV_example"
```

Apps Script URLs must be production `/exec` URLs on `script.google.com`; never
put credentials in the URL. Source configuration is hard-coded in the deployed
script as `const SOURCES = { participants: {...}, leaders: {...} }`; there is no
Script Property. Replace the placeholder IDs, tab names, one-based timestamp
columns, and exact headers in the Apps Script editor only. Do not commit the
actual source IDs or deployed code.

Copy `apps-script/sheets-registration-endpoint.gs` into the event's Apps Script
project. In the editor, replace its `API_SECRET` placeholder with a random
secret of at least 32 bytes (64 hex characters or 43+ URL-safe characters), and
replace the placeholder `SOURCES` object with the confirmed mappings. Run
`selfCheck()` with its synthetic fixtures, then run `authorizeSources()` in the
editor and approve Sheet access; it checks the configured tabs and headers but
does not read response rows. Success messages appear under **Execution log**;
past runs are available from **Executions** in the left sidebar. Confirm each
Sheet timezone is the event's named
timezone (`America/Detroit` for HighSchool), then deploy a versioned web app as
**Execute as: Me** with access for callers who are not signed in. Confirm
Workspace policy allows this. Test a known timestamp through the deployed
endpoint and verify its Sheet-local date and clock time are unchanged. Then store
the same secret in local `GOOGLE_SHEETS_API_SECRET` for dry-runs; add the GitHub
Actions secret only after the dry-run is accepted and before workflow activation.

When script code changes, deploy a new version; changing the editor source does
not update an existing versioned deployment. To rotate the secret, replace it
in the script, deploy a new version, and update the local/GitHub secret. Never
commit or share the actual deployed source containing the secret. Response rows
are counted one-for-one; the live Sheet is mutable source of truth, not an
immutable ledger. Deleted or edited rows affect future counts. Source cells
must be native date values or text in `M/d/yyyy HH:mm:ss`; timestamps are
normalized to `yyyy-MM-dd HH:mm:ss` without changing the Sheet-local clock time.
Blank or invalid timestamp cells fail the whole report.

`check` is offline validation only (it does not contact Apps Script). A report
`--dry-run` fetches all required live sources and writes only its chart;
it still requires the webhook setting for report readiness but does not send
Discord. A
normal `report` sends the Discord message only after all sources succeed.

The `highschool` profile uses the confirmed 2025 history, November 15, 2026
event date, and production Apps Script endpoints. It is enabled in the workflow;
configure both `HSIO_...` secrets before dispatching it. Run a local dry-run
before sending a live report.
