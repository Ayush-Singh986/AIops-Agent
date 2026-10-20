# AIOps Project: Interview and Deployment Guide

This guide explains the project in plain English, gives you a presentation you can use in an interview, and walks through deploying the demo stack on a Linux server.

For the detailed design and evaluation methodology, see [METHODOLOGY.md](./METHODOLOGY.md). The existing [README.md](./README.md) is the short project overview.

## 1. The real-world problem

When an online service slows down or stops working, users notice it before the engineering team knows why. A dashboard may show high response times, errors, or an outage, but those are symptoms. The actual cause could be the application, its cache, a downstream service, or a resource such as CPU or memory.

Engineers often have to:

1. Notice and acknowledge an alert.
2. Open several dashboards and log sources.
3. Work out which metric changed first and which changes are related.
4. Decide whether a proposed fix is safe.
5. Apply the fix and check that the service recovered.

That investigation can take time, especially when several metrics change together. Automatically restarting or changing services without checks can also make an incident worse.

## 2. The solution, in simple terms

This project is a small, chaos-testable AIOps incident-response prototype. It collects service metrics, detects unusual behavior, ranks likely root causes, and uses an LLM to explain or challenge that ranking using evidence. It can then recommend a limited remediation action. Higher-risk actions are designed to require human approval.

The key design choice is to keep the quantitative diagnosis outside the LLM. Statistical code detects anomalies and creates a ranked list first. The LLM receives those candidates and supporting evidence; it is not asked to discover a root cause from unfiltered telemetry.

### Interview-ready introduction (about one minute)

> “I built an AIOps incident diagnosis prototype to reduce the time engineers spend finding the cause of service incidents. The demo runs a FastAPI service with Redis and monitors it using Prometheus. I can inject controlled failures such as Redis latency, downstream failures, CPU spikes, and memory growth.
>
> The detector uses rolling median and MAD-based scores for sudden changes, CUSUM for gradual memory growth, and a persistence check to avoid reacting to a single noisy sample. When several metrics are abnormal, a separate correlation stage ranks possible causes using a dependency map, lagged correlation, and onset timing.
>
> A LangGraph workflow then gathers metric, application-log, deployment, and incident-history evidence. An LLM explains the diagnosis and can challenge the statistical ranking, but it is constrained to the evidence and a fixed action set. The workflow routes higher-risk actions through an approval step.
>
> I evaluated it using faults that I injected myself, so the expected fault type was known. On this small dataset, root-cause accuracy improved from 70% for the statistical ranking to 80% with the LLM reasoning layer. I treat those figures as indicative, not a production guarantee. The current repository is a prototype: Compose deploys the demo and monitoring stack, while diagnosis is run separately rather than as a continuously running production service.”

## 3. How a diagnosis flows from start to finish

1. **The service emits telemetry.** The FastAPI app exposes Prometheus metrics at `/metrics/`. It tracks request count and latency, and the service also exposes application, Redis, downstream, CPU, and memory metrics.
2. **Prometheus scrapes the app.** The Compose configuration scrapes every five seconds and retains its data in a Docker volume.
3. **A fault is injected for testing.** The chaos scripts can introduce Redis or downstream latency, failures, an app outage, CPU load, or memory growth. They record the fault and its timing so an evaluation can compare the diagnosis with the known cause.
4. **The detector flags unusual metrics.** Most metrics use a modified z-score based on a rolling median and median absolute deviation (MAD). Memory uses an upward CUSUM path because a leak is a gradual drift, not necessarily a single spike. A persistence filter requires repeated abnormal samples before flagging a metric.
5. **The root-cause stage ranks candidates.** A hand-maintained dependency map encodes plausible cause-and-effect relationships. The ranking combines the dependency prior, lagged correlation, and onset timing. A detected app-availability outage is treated as a hard outage signal.
6. **The diagnosis workflow gathers context.** LangGraph nodes collect metric summaries, application-log samples, nearby deployment records, and similar recorded incidents. If the first diagnosis is uncertain, the workflow investigates related metrics and tries again, with an iteration limit.
7. **The LLM explains or challenges the ranking.** Amazon Bedrock Nova Pro is the configured provider. The prompt asks it to use the provided evidence, explain its choice, and select from a fixed set of remediation actions. Its confidence is bounded by the statistical candidate confidence.
8. **The workflow applies a safety route.** The workflow can finish without action, execute a low-risk action, or pause at an approval interrupt for an action classified as high risk.
9. **The result can be checked.** The diagnosis report includes the selected root cause, confidence, hypothesis, action, approval status, and remediation result.

### What runs automatically, and what does not

`docker compose up` starts the FastAPI app, Redis, Prometheus, Grafana, and Locust. It does **not** start a background detector or a continuously listening diagnosis agent. The evaluation and diagnosis entry points are Python commands run separately from the repository root. The full diagnosis evaluation uses the checked-in baseline and incident datasets and queries the local Prometheus service for evidence; it is not a production event consumer.

## 4. Main project areas

| Path | Purpose |
|---|---|
| [service/](./service/) | FastAPI application, metrics, logging, and chaos-control endpoints |
| [chaos/](./chaos/) | Fault injection and experiment runners |
| [detector/](./detector/) | MAD and forecast-residual detectors, Prometheus queries, evaluation, and root-cause ranking |
| [agent/](./agent/) | LangGraph diagnosis workflow, evidence nodes, LLM calls, and remediation routing |
| [data/](./data/) | Baseline telemetry and labeled incident datasets used for evaluation |
| [prometheus/prometheus.yml](./prometheus/prometheus.yml) | Prometheus scrape configuration |
| [docker-compose.yml](./docker-compose.yml) | Demo application and observability stack |
| [METHODOLOGY.md](./METHODOLOGY.md) | Detection, correlation, evaluation results, case studies, and production limitations |

## 5. Interview questions and example answers

### Basic

**Q: What problem does the project solve?**  
**A:** It helps shorten incident investigation by detecting abnormal service metrics, ranking likely causes, and collecting evidence in one diagnosis workflow. It also puts approval checks between a diagnosis and higher-risk remediation.

**Q: What does AIOps mean here?**  
**A:** Applying operational data and automation to incident detection and response. In this project, that means telemetry-based anomaly detection, root-cause ranking, evidence-based diagnosis, and guarded remediation recommendations.

**Q: What technologies did you use?**  
**A:** Python, FastAPI, Redis, Prometheus, Grafana, Docker Compose, pandas and NumPy, LangGraph, and Amazon Bedrock.

**Q: What can the demo monitor or inject?**  
**A:** It tracks request rate, application latency and errors, Redis and downstream latency/errors, CPU, memory, and application availability. The experiment runner supports Redis latency/outage, app outage, downstream latency/failure, CPU spike, and memory leak faults.

### Intermediate

**Q: Why use median and MAD instead of mean and standard deviation?**  
**A:** Median and MAD are more resistant to a few extreme observations. That makes the rolling baseline less likely to be distorted by the very spikes the detector is trying to find. Thresholds and windows are configured per metric because their normal behavior differs.

**Q: Why does the detector require repeated abnormal samples?**  
**A:** A persistence filter reduces alerts caused by one noisy scrape. It trades faster detection for fewer transient alerts. With 30-second evaluation samples, three consecutive flagged points represent roughly 90 seconds of sustained deviation.

**Q: Why is memory handled differently?**  
**A:** A memory leak can appear as a slow, persistent rise rather than a sharp point anomaly. The one-sided CUSUM accumulates repeated upward deviations, making it better suited to that pattern in this prototype.

**Q: How does the system distinguish a cause from a symptom?**  
**A:** It uses a dependency prior to encode plausible direction, lagged correlation to see whether metrics move together with a time offset, and onset timing as one additional signal. The score is `0.5 × prior + 0.35 × correlation + 0.15 × onset timing`. This is a ranking heuristic, not proof of causation.

**Q: Why use an LLM after the statistical pipeline?**  
**A:** The detector and correlation stages are explainable and repeatable for numerical analysis. The LLM is used for evidence-grounded comparison and a readable explanation, not as the first or only detector. This also limits the chance of the LLM inventing a cause from raw telemetry.

**Q: What does LangGraph contribute?**  
**A:** It represents diagnosis as an explicit stateful workflow: gather evidence, diagnose, check confidence, optionally gather more evidence, finalize the action, and route through approval or execution.

**Q: How did you evaluate root-cause accuracy?**  
**A:** I injected faults whose type and timing were known, then compared the predicted root metric with that ground truth. The methodology reports 70% for the statistical pipeline and 80% after LLM reasoning on about 10–11 incidents. That dataset is too small to claim production accuracy.

### Advanced

**Q: Does correlation establish that one metric caused another?**  
**A:** No. Correlation and earlier onset are supporting signals, not causal proof. The dependency map narrows the candidates, but it is manually encoded and limited to this demo architecture. Production diagnosis should use stronger evidence such as distributed traces, service topology, and validated incident history.

**Q: What are the main limitations?**  
**A:** The evaluation set is small and self-injected; the current baseline is not seasonality-aware; the dependency map is hand-maintained; deployment and incident history are local demo logs; and there is no always-on detector/agent service. The project also has a known ambiguous CPU-spike case documented in the methodology.

**Q: Is it ready to remediate a production system autonomously?**  
**A:** No. It is a prototype. The code’s action vocabulary includes scale-out and rollback, but the current execution function only implements service restart and Redis `FLUSHALL`; the other action names are not implemented there. Also, the evaluator auto-approves interrupts and remediation is not in dry-run mode by default. I would keep it isolated, run evaluation in dry-run mode, and add policy enforcement, authentication, audit trails, blast-radius limits, and tested integrations before considering production use.

**Q: How would you improve it for a real environment?**  
**A:** First, make detection seasonal-aware and continuously consume production telemetry. Then derive dependency topology from service catalog or tracing data, integrate real deployment and incident systems, and build a larger labeled evaluation set from reviewed postmortems. I would also add authentication and authorization, structured audit logs, per-action policies, idempotency, rollback plans, and human approval for high-impact changes.

**Q: What happens if the LLM returns malformed output?**  
**A:** The diagnosis code handles a JSON parse failure by setting confidence to zero, requesting more evidence, and selecting no remediation action. The workflow has an iteration limit. Other infrastructure failures, such as unavailable Bedrock credentials or Prometheus, should be monitored and handled explicitly before production use.

**Q: What would you monitor about the AIOps system itself?**  
**A:** Detection latency, alert precision/recall, diagnosis accuracy after human review, confidence calibration, evidence-source availability, LLM latency/errors/cost, approval and rejection rates, remediation success, recovery time, and any unintended side effects.

## 6. Deploy the demo stack on an Ubuntu server

These steps deploy the **demo infrastructure**. They do not turn the repository into a production-grade, always-on AIOps platform. Run chaos experiments only on an isolated test server: some experiments stop or stress the application.

### Before you begin

- An Ubuntu 22.04/24.04 server with outbound internet access.
- A non-root account with `sudo`.
- A Git repository URL and permission to clone it.
- Enough disk for Docker images and Prometheus/Grafana data.
- If you plan to run the Bedrock-backed diagnosis agent: AWS credentials supplied securely, Bedrock model access in the configured AWS region, and permission to invoke the selected model.

Do not expose the demo ports directly to the public internet. The Compose file publishes the app, Prometheus, Grafana, and Locust ports on all host interfaces. The chaos endpoints have no authentication, and Grafana requires a password supplied through a protected, untracked `.env` file.

### Step 1: Install Docker, Compose, Git, and Python

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git python3 python3-venv python3-pip
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in so the Docker group membership takes effect, then verify:

```bash
docker --version
docker compose version
git --version
python3 --version
```

If your Ubuntu package source does not provide `docker-compose-v2`, install Docker Engine and the Compose plugin using Docker's official Ubuntu installation instructions, then rerun `docker compose version`.

### Step 2: Get the project onto the server

Replace the placeholder with your actual repository URL:

```bash
git clone <YOUR_REPOSITORY_URL>
cd <CLONED_REPOSITORY_DIRECTORY>
```

Run all project commands below from the directory containing `docker-compose.yml`. Check that you are in the right directory:

```bash
test -f docker-compose.yml
```

If the project is already on the server, use `cd` to enter that project directory instead of cloning it again.

### Step 3: Secure the demo before starting it

1. Generate a unique Grafana password in a protected `.env` file. From the project directory, run:

   ```bash
   bash scripts/setup-env.sh
   ```

   The script creates the file if missing, preserves an existing password, and sets file permissions to `600`. Docker Compose reads `.env` automatically from the project directory, and the file is ignored by Git. Do not put the password in `docker-compose.yml`, commit `.env`, or share it in logs. Compose will refuse to start Grafana if the required variable is missing or empty.
2. Restrict inbound firewall access. For a private demo, allow SSH and use SSH tunnels to access the web interfaces instead of opening their ports publicly. For example:

   ```bash
   sudo ufw allow OpenSSH
   sudo ufw enable
   sudo ufw status
   ```

3. Do not publish `/chaos` endpoints to an untrusted network. They intentionally inject faults and currently do not require authentication.

If you need remote browser access, use a properly secured reverse proxy with TLS and authentication, and restrict access to trusted users. The repository does not configure that proxy.

### Step 4: Build and start the Docker Compose services

```bash
docker compose up --build -d
docker compose ps
```

Wait for the services to start, then inspect logs if a container is not running:

```bash
docker compose logs --tail=100
docker compose logs --tail=100 aiops-app
```

### Step 5: Verify the app and metrics

Run these checks on the server:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/metrics/
```

The health endpoint should return `{"status":"healthy"}`. Prometheus is available at `http://127.0.0.1:9090`; open **Status → Targets** and confirm that the `aiops-app` target is up.

For remote access without opening ports publicly, create SSH tunnels from your workstation:

```bash
ssh -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 -L 8089:127.0.0.1:8089 <USER>@<SERVER_ADDRESS>
```

Then open the tunneled Grafana, Prometheus, or Locust page in your local browser. Grafana is at `http://127.0.0.1:3000`; Prometheus is at `http://127.0.0.1:9090`; Locust is at `http://127.0.0.1:8089`.

### Step 6: Configure Grafana (optional)

The Compose file starts Grafana, but this repository does not provision a Grafana data source or dashboard automatically.

1. Sign in to Grafana using username `admin` and the password you set in Step 3.
2. Add a Prometheus data source with URL `http://prometheus:9090`.
3. Save and test the data source.
4. Create a dashboard and add PromQL queries for the metrics you want to visualize.

The screenshots in `docs/` show example Grafana output; they do not mean a dashboard is preloaded in a fresh Grafana volume.

### Step 7: Generate demo traffic and optionally inject a fault

Locust starts as a web UI; it does not generate load until you start a test in the UI. Start with a low user count and short duration.

To run a controlled chaos experiment, execute the runner from the project root while the Compose stack is running:

```bash
python3 -m chaos.run_experiments --fault redis_latency
```

The default experiment waits 30 seconds for a baseline, then injects the fault for 60 seconds. Other supported `--fault` values are `redis_outage`, `app_outage`, `downstream_latency`, `downstream_failure`, `cpu_spike`, and `memory_leak`. These experiments disrupt or stress the demo, so do not run them against a production service.

### Step 8: Prepare the separate Python diagnosis environment (optional)

The Compose stack does not include the LangGraph diagnosis agent. To run its Python entry points on this server, create a virtual environment and install the detector requirements plus the agent dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r detector/requirements.txt langgraph boto3 python-dotenv
```

The agent imports the application logger, which requires `LOG_FILE`. Set it to the app log mounted in the repository:

```bash
export LOG_FILE="$PWD/logs/app.jsonl"
```

The Prometheus client in the detector expects Prometheus at `http://localhost:9090`, so run the agent on the Docker host with the stack active. The Bedrock client in `agent/llm.py` is configured for `ap-south-1` and Amazon Nova Pro. Set `AWS_DEFAULT_REGION=ap-south-1` and provide AWS credentials using an instance role or another secure AWS credential provider. Do not put credentials in source control or a committed `.env` file.

Before running the full agent evaluator, read the safety warning below. The detector/root-cause evaluation does not invoke remediation:

```bash
python -m detector.evaluate_rootcause
```

### Critical remediation safety warning

The current defaults are not safe for an unattended production run:

- `DRY_RUN` is `False` in `agent/remediation.py`.
- `agent/evaluate_diagnosis.py` passes `auto_approve=True`, so it automatically approves any approval interrupt during evaluation.
- The executor currently implements `restart_service` and Redis `FLUSHALL`; `scale_out` and `rollback_deploy` are named actions but are not implemented by the executor.

To run the full diagnosis evaluation without executing a supported remediation, change `DRY_RUN = True` in `agent/remediation.py` before running:

```bash
python -m agent.evaluate_diagnosis
```

Restore the original setting only when you deliberately intend to test the implemented action in an isolated environment and have reviewed the approval behavior. Do not treat the evaluator's automatic approval as a production approval workflow.

### Step 9: Stop services and preserve data

Stop containers but retain the named Prometheus and Grafana volumes:

```bash
docker compose down
```

Start them again later with:

```bash
docker compose up -d
```

`docker compose down -v` also removes the named volumes and deletes the stored Prometheus and Grafana data. Use it only when you intentionally want to erase that data.

## 7. Troubleshooting

| Symptom | Checks |
|---|---|
| A container exits or stays unhealthy | Run `docker compose ps` and `docker compose logs --tail=100 <service-name>`. |
| `/health` is unavailable | Confirm `aiops-app` is running and inspect its logs. |
| Prometheus shows the app target as down | Check `http://127.0.0.1:8000/metrics/`, then inspect the target and Prometheus logs. |
| Grafana has no charts | Add the Prometheus data source at `http://prometheus:9090`; dashboards are not provisioned by this repository. |
| Chaos runner cannot reach the app | Run it on the Docker host, from the project root, and verify `http://127.0.0.1:8000/health`. |
| Diagnosis fails before calling the model | Check that the virtual environment is active, `LOG_FILE` is set, Prometheus is running, and the command is executed from the repository root. |
| Bedrock returns an authorization or model error | Check the AWS identity, Bedrock model access, region, and `AWS_DEFAULT_REGION`. Never paste credentials into logs or source files. |
| Remediation command fails | Check that Docker is available to the Python process and that it runs from the Compose project directory. Keep `DRY_RUN=True` while troubleshooting diagnosis. |

## 8. A good closing answer in an interview

> “The main lesson from this project was to separate detection, causal ranking, and language-model reasoning instead of asking one model to do everything. The statistics provide measurable signals, the topology and lag analysis narrow likely causes, and the LLM adds an evidence-based explanation. I also learned that evaluation quality and operational safeguards matter as much as a plausible diagnosis. The current prototype demonstrates the workflow, while continuous ingestion, production integrations, security controls, and a larger evaluation set are the next steps.”

## 9. Terraform deployment on AWS

To provision a small, cost-conscious AWS host for the Docker Compose demo, follow the Terraform guide in [`terraform/README.md`](terraform/README.md). It creates a single EC2 instance with encrypted storage and Session Manager access; it does not open application, Grafana, Prometheus, Locust, or SSH ports to the internet.

## 10. Future roadmap

The planned next steps and their priorities are described in [`ROADMAP.md`](ROADMAP.md). They focus first on safety, reproducible evaluation, and diagnosis reliability before expanding integrations or production deployment.
