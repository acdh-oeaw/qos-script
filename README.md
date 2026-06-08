
# Quality of Service script (qos-script)

This repository contains a small tool that collects information about services deployed on the ACDH infrastructure and writes it to a backend (currently: Redmine).

Purpose
- Periodically collect information from Rancher/Portainer (workloads, endpoints, images)
- Maintain this information in Redmine issues as a service registry

Contents
- Package: [acdhQos](acdhQos)
- QoS checks: [checks](checks)
- Resilient runner: `qos_runner.py`
- Utility modules: [utils](utils)
- CLI scripts: [scripts/qos-script-update-redmine](scripts/qos-script-update-redmine), [scripts/qos-script-restore-from-redmine](scripts/qos-script-restore-from-redmine)
- Packaging: `setup.py`, `requirements.txt`, `Dockerfile`

New resilient design
- `utils/rate_limiter.py`: token bucket rate limiting for HTTP checks
- `utils/http_client.py`: async HTTP client with per-host circuit breaker, retries and concurrency control
- `utils/k8s_client.py`: throttled Kubernetes API client with caching and 429 handling
- `qos_runner.py`: batch-oriented runner that pre-fetches HTML, performs checks, and formats results for Redmine
- `checks/imprint_check.py`: verifies found imprint links and optionally checks reachability via http_client

Quick start

Requirements
- Python 3.8+
- Install dependencies:

```bash
pip install -r requirements.txt
```

Example run (read-only):

```bash
python3 scripts/qos-script-update-redmine --rancher --readOnly --rancherUrl "https://rancher.example/v3" --rancherToken "$RANCHER_TOKEN"
```

Example run (updates Redmine):

```bash
python3 scripts/qos-script-update-redmine --rancher --rancherUrl "https://rancher.example/v3" --rancherToken "$RANCHER_TOKEN" --redminePswd "$REDMINE_PSWD"
```

Alternative run (async resilient checks):

```bash
python3 qos_runner.py
```

Configuration / arguments
- `--redmineUrl`, `--redmineUser`, `--redminePswd`
- `--rancherUrl`, `--rancherToken`, `--rancherProject` and filtering flags
- `--readOnly` lists collected data only, `--verbose` enables verbose logging


CI / GitHub Actions and Deployment

- Workflows: The repository contains a GitHub Actions workflow at `.github/workflows/starter.yaml` which runs on `push` and `workflow_dispatch` (manual run).
- Environment selection: The workflow maps the Git ref to an environment — `main` → `production`, other branches → `review/{branch}`. This determines the target deployment namespace and `PUBLIC_URL` when not explicitly provided.
- Build & push: The workflow reuses `acdh-oeaw/gl-autodevops-minimal-port` reusable workflows to build the `Dockerfile` and push the image to the registry root `ghcr.io/${{ github.repository }}/` (image name `qos-script`).
- Deploy: After building the image the workflow calls the reusable `deploy.yml` which performs a Helm/Kubernetes deployment using repo-provided values and secrets. Secrets such as `KUBE_CONFIG`, `KUBE_INGRESS_BASE_DOMAIN`, and other environment-specific secrets must be provided by the organization or the repository environment.

Auto-deploy values

The file `.github/auto-deploy-values.yaml` contains Helm-like values used for the deployment. Key points from the current file:

- `image.repository`: `ghcr.io/acdh-oeaw/qos-script/qos-script`, tag `latest`
- `replicaCount`: currently `0` (service is not scaled up by default)
- `ingress.enabled`: `false` (no ingress configured by default)
- Health probes: disabled (`livenessProbe`/`readinessProbe`/`startupProbe` = false)
- `cronjobs.job`: a scheduled CronJob is defined (currently `0 8 * * 5`, i.e. Fridays 08:00) which runs the update script inside the container:

```yaml
command: [ "/bin/bash" ]
args: [ "-c", "python /app/scripts/qos-script-update-redmine --redminePswd $REDMINE_PSWD --rancher --rancherUrl $RANCHER_URL --rancherToken $RANCHER_TOKEN --rancherSkipClusters $SKIP_CLUSTERS --rancherSkipTypes $SKIP_TYPES --verbose" ]
```

The CronJob references a Kubernetes secret via `extraEnvFrom.secretRef.name: qos-script-master` to load runtime secrets such as `REDMINE_PSWD` and `RANCHER_TOKEN`.

How deployment currently works (summary)
- A push to `main` triggers a production build+deploy; a push to any other branch triggers a review deployment (`review/{branch}`).
- The build step produces and pushes a Docker image to GitHub Container Registry under `ghcr.io/...`.
- The deploy step (reusable workflow) applies Helm/Kubernetes manifests with values from `.github/auto-deploy-values.yaml` and organization-level secrets/configuration.





