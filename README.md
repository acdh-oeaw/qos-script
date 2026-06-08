# Quality of Service script (qos-script)

This repository contains a tool that discovers services in Kubernetes, runs website-level QoS checks, and keeps service metadata in Redmine.

## What this project does

- Discovers services by reading Kubernetes ingress resources.
- Fetches each service homepage once and runs HTML-based checks.
- Writes formatted results back to Redmine, keeping service records up to date.
- Provides a small restore helper for historical Redmine issue restoration.

## How the main runner works

### `qos_runner.py`

This is the async runner and main entrypoint for service checks.

- It uses `utils/k8s_client.py` to discover ingresses in the cluster.
- It creates a shared `ResilientHttpClient` from `utils/http_client.py`.
- It fetches each service URL exactly once and passes the returned HTML into every check.
- It batches service execution by `runner.batch_size` and waits `runner.batch_delay` between batches.
- It handles individual service failures and continues processing remaining services.

### `scripts/qos-script-update-redmine`

This script is the current deployment wrapper used for Redmine synchronization.
It harvests Rancher/Rancher-derived services, runs QoS checks, formats a Redmine table, and updates Redmine issues.

## What is checked

The current QoS checks are implemented in `checks/`:

- `checks/logo_check.py`
  - Verifies an ACDH logo is present in the page source or image tags.
  - Uses configured `logo_patterns`.

- `checks/helpdesk_check.py`
  - Verifies the configured helpdesk email address appears in the page.
  - Checks both raw text and `mailto:` links.

- `checks/imprint_check.py`
  - Finds an imprint/legal-notice link in the page.
  - If a shared HTTP client is provided, it optionally fetches the link to verify reachability.

- `checks/accessibility_check.py`
  - Performs basic accessibility heuristics:
    - `lang` attribute on `<html>`
    - `<title>` tag content
    - at least one `<h1>` tag
    - viewport meta tag
    - `<img>` tags with `alt`
    - form inputs with label or aria labeling

## Configuration

Configuration is centralized in `config.yaml` and loaded by `config.py`.

### `config.yaml` sections

- `checks`
  - `helpdesk_email`: email to look for in helpdesk checks.
  - `logo_patterns`: list of strings to search for in logo HTML.
  - `imprint_keywords`: list of keywords used to find imprint/legal links.

- `http`
  - `requests_per_second`: global HTTP request rate for the shared client.
  - `max_concurrent`: HTTP concurrency limit.
  - `timeout_seconds`: request timeout.
  - `max_retries`: retry count for transient HTTP failures.

- `k8s`
  - `requests_per_second`: rate limit for Kubernetes API calls.

- `runner`
  - `batch_size`: number of services processed per batch.
  - `batch_delay`: seconds to wait between batches.

- `redmine`
  - `request_interval_seconds`: delay between Redmine backend requests.

### Environment variable overrides

The following variables can override values from `config.yaml`:

- `QOS_HELPDESK_EMAIL`
- `QOS_LOGO_PATTERNS`
- `QOS_IMPRINT_KEYWORDS`
- `QOS_HTTP_REQUESTS_PER_SECOND`
- `QOS_HTTP_MAX_CONCURRENT`
- `QOS_HTTP_TIMEOUT_SECONDS`
- `QOS_HTTP_MAX_RETRIES`
- `QOS_K8S_REQUESTS_PER_SECOND`
- `QOS_BATCH_SIZE`
- `QOS_BATCH_DELAY`
- `QOS_REDMINE_REQUEST_INTERVAL_SECONDS`

## Usage

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the async runner directly:

```bash
python3 qos_runner.py
```

Run the deployed Redmine sync script with API key (recommended):

```bash
python3 scripts/qos-script-update-redmine --rancher --rancherUrl "https://rancher.example/v3" --rancherToken "$RANCHER_TOKEN" --redmineApiKey "$REDMINE_API_KEY"
```

Or using Basic Auth as fallback:

```bash
python3 scripts/qos-script-update-redmine --rancher --rancherUrl "https://rancher.example/v3" --rancherToken "$RANCHER_TOKEN" --redminePswd "$REDMINE_PSWD"
```

Run in read-only mode:

```bash
python3 scripts/qos-script-update-redmine --rancher --readOnly --rancherUrl "https://rancher.example/v3" --rancherToken "$RANCHER_TOKEN"
```

## Redmine authentication

Redmine integration supports two authentication methods:

1. **API Key (recommended)**: Use `--redmineApiKey` or `$REDMINE_API_KEY` environment variable for token-based authentication.
2. **Basic Auth (fallback)**: Use `--redmineUser` and `--redminePswd` (or `$REDMINE_PSWD`) if no API key is provided.

Authentication priority is: API Key first, then Basic Auth. If an API key is available, it will be used automatically.

## Legacy restore helper

- `scripts/qos-script-restore-from-redmine`
  - Reads local host `config.json` files under `/home`.
  - Fetches Redmine issue history and restores service aliases and backend connection details.
  - Supports both API key and Basic Auth authentication.

Example with API key:

```bash
python3 scripts/qos-script-restore-from-redmine --redmineUrl https://redmine.acdh.oeaw.ac.at --redmineApiKey "$REDMINE_API_KEY" --homeDir /home
```

Example with Basic Auth:

```bash
python3 scripts/qos-script-restore-from-redmine --redmineUrl https://redmine.acdh.oeaw.ac.at --redmineUser qosScript --redminePswd "$REDMINE_PSWD" --homeDir /home
```

## Architecture notes

- `utils/http_client.py` manages a single shared `aiohttp.ClientSession`.
- `utils/rate_limiter.py` implements token-bucket rate limiting.
- `utils/k8s_client.py` implements Kubernetes API throttling and pagination.
- `acdhQos/backend.py` contains the Redmine backend helper with request throttling and improved error handling.

## Deployment notes

The repository also contains GitHub Actions and deployment configuration, typically deploying the update script in a CronJob.
The deployment uses the Redmine sync wrapper `scripts/qos-script-update-redmine` and runtime secrets like `REDMINE_PSWD` and `RANCHER_TOKEN`.





