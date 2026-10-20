# AIOps Agent Self-Healing Project — Explained

This project is an end-to-end AIOps system that does not just detect an anomaly. It tries to answer three real operational questions:

1. What is broken?
2. What is the most likely root cause?
3. What safe action should be taken?

It simulates a real microservice environment, injects faults like Redis latency, downstream failures, CPU spikes, and memory leaks, collects telemetry, analyzes the signals, ranks likely causes, and then uses a LangGraph-based LLM agent to reason over the evidence before deciding whether to automate a remediation action.

The goal is to combine deterministic signal analysis with a guard-railed LLM so the bot is explainable, safer than a raw LLM autopilot, and still flexible enough to override a bad statistical guess in ambiguous cases.

---

## What problem this project is solving

In real production systems, alerts often show many noisy metrics at once. A spike in latency, failed downstream requests, elevated Redis latency, CPU pressure, and app errors may all appear at the same time.

The problem is not just detection. The real challenge is:

- separating cause from symptom
- correlating metrics with dependency relationships
- identifying the likely source of the fault
- avoiding unsafe automation
- deciding whether human approval is required

This project models exactly that workflow in a controlled lab environment.

---

## High-level architecture

The system is built in four major stages:

1. System under test
   - A small FastAPI app with Redis and a simulated downstream dependency
   - Prometheus metrics and structured app logs

2. Chaos injection
   - Faults are intentionally introduced to mimic common production incidents
   - Each fault has a known ground truth label

3. Detection and diagnosis
   - Statistical anomaly detection finds suspicious metrics
   - A root-cause ranking pipeline scores likely causes using topology, lag correlation, and onset timing
   - An LLM diagnosis agent inspects the evidence and decides if the statistical candidate is correct or needs override

4. Remediation
   - The model recommends a safe action from a restricted set
   - High-risk actions require human approval
   - Only a few actions are actually implemented and guarded

---

## End-to-end flow

The actual execution flow looks like this:

```text
Chaos fault injected
    ↓
Application emits telemetry + logs + metrics
    ↓
Anomaly detector flags suspicious metrics
    ↓
Root-cause ranking computes likely source candidates
    ↓
LangGraph agent gathers additional evidence
    ↓
LLM judges the candidate and recommends action
    ↓
Safety gate decides: execute / ask approval / no-op
```

This is not a random rule engine. It is intentionally layered so the hard part is explainable and reproducible, while LLM reasoning is deliberately constrained.

---

## 1) The service under test

This project runs a small application stack in Docker Compose. The main service is a FastAPI app that stores and retrieves items from Redis and calls a simulated downstream dependency.

### Main service files

- `service/main.py`
  - creates the FastAPI app
  - registers routes
  - mounts the Prometheus metrics endpoint
  - adds middleware to record HTTP latency and request counts

- `service/routes.py`
  - defines the item API
  - reads/writes data to Redis
  - logs cache accesses
  - triggers downstream calls

- `service/chaos_routes.py`
  - exposes endpoints for injecting chaos
  - supports Redis delay, downstream delay, downstream failure, CPU burn, and memory leak

- `service/chaos_state.py`
  - holds runtime state for the injected faults
  - acts like a small in-memory control plane for fault simulation

- `service/metrics.py`
  - defines Prometheus counters and histograms for request latency, Redis latency, cache counts, and downstream dependencies

### What the app is doing

The app behaves like a simplified real service:

- `POST /items` writes an item into Redis
- `GET /items/{id}` attempts to read the item from Redis
- if missing, it falls back to in-memory storage
- every request may hit a downstream dependency called `catalog-service`
- this downstream dependency can be delayed or fail, creating realistic dependency-chain faults

This makes it possible to simulate faults such as:

- Redis slowdown
- Redis outage
- app outage
- downstream latency
- downstream partial failure
- resource saturation
- memory leak

---

## 2) Chaos injection subsystem

The chaos subsystem intentionally creates the incident conditions we want to measure.

### Key files

- `chaos/run_experiments.py`
  - CLI entry point for running fault scenarios
  - supports faults like `redis_latency`, `app_outage`, `redis_outage`, `downstream_latency`, `downstream_failure`, `cpu_spike`, and `memory_leak`

- `chaos/scripts/`
  - each script contains a concrete fault injection scenario
  - examples:
    - `redis_latency_experiment.py`
    - `redis_outage_experiment.py`
    - `downstream_failure_experiment.py`
    - `cpu_spike.py`
    - `memory_leak_experiment.py`

- `chaos/incident_logger.py`
  - logs factually known incident metadata

- `chaos/incidents.log`
  - store of injected faults and their timestamps/parameters

### Why this matters

This project is not testing random real-world faults. It creates labeled incidents with known ground truth. That is essential for evaluating whether the detector and diagnosis logic are actually working.

If a Redis delay is injected, the correct root cause is expected to be Redis. If a memory leak is injected, the system should identify memory pressure rather than a downstream dependency issue.

---

## 3) Monitoring and telemetry pipeline

The app exposes operational metrics to Prometheus. These are the signals the detection pipeline uses.

### Examples of monitored metrics

- request rate
- app latency
- app error rate
- Redis latency
- cache error rate
- downstream latency
- downstream error rate
- process CPU rate
- process memory usage
- app availability

These metrics are collected continuously and become the evidence base for anomaly detection.

### Understanding the live Prometheus and Locust screenshots

These screenshots show the monitoring and traffic-generation parts of the demo working:

![Prometheus shows the aiops-app metrics endpoint as up](docs/live-prometheus-target-health.png)

Prometheus lists `aiops-app` as **1 / 1 up**. It successfully scraped `http://aiops-app:8000/metrics/`; the screenshot shows a five-second scrape interval and a four-millisecond scrape duration. This confirms that Prometheus can reach and collect the app's metrics endpoint. It does **not** prove that every app request is healthy or that an incident has been diagnosed.

![Locust running a one-user test against the app](docs/live-locust-running.png)

Locust is the load generator: it sends requests to the app and reports what happened. In this snapshot, the test is running with **one virtual user**, about **0.8 requests per second**, and **0% failures**. A virtual user is a simulated client, not a real person.

![Locust response-time and virtual-user charts](docs/live-locust-metrics.png)

The charts show response-time percentiles and the number of active Locust virtual users over time. Most response times are low, with brief spikes near **500 ms**. The virtual-user count briefly falls to zero and then returns to one. These are observations from this test run; the charts alone cannot identify why a spike or pause happened. Compare their timestamps with the app logs, Prometheus metrics, and chaos-experiment log before attributing them to a particular fault.

### How these live screens relate to diagnosis

The pieces fit together like this:

```text
Locust sends requests ──> FastAPI app ──> Redis / downstream dependency
                              │
                              └── /metrics ──> Prometheus scrapes and stores metrics

Saved incident telemetry ──> detector ──> root-cause ranking
                                             └──> LangGraph / Bedrock diagnosis
                                                   └──> remediation decision
```

Prometheus collection and Locust traffic happen while the demo stack is running. The diagnosis evaluation is a separate, explicitly run workflow that replays saved incident telemetry; the live dashboards do not automatically trigger a new diagnosis whenever a graph changes. The agent can also gather live Prometheus evidence during a diagnosis run, but that is not the same as an always-on alert-to-remediation service.

> **Security warning:** The original screenshots were captured by opening Prometheus and Locust through the server's public IP. These demo interfaces, as well as the chaos endpoints, do not provide authentication. Do not leave their ports publicly reachable. Remove public inbound rules or restrict access and use the Systems Manager port-forwarding approach in the [Terraform guide](terraform/README.md). The screenshots in this repository are cropped to omit the public IP and AWS account header.

---

## 4) Statistical anomaly detection

The detector logic is the quantitative core of the project.

### Main detection file

- `detector/mad_detector.py`

This implements a rolling Median Absolute Deviation (MAD) anomaly detection strategy. For each metric, it compares current values to a rolling baseline and flags if the deviation is statistically significant.

### Why MAD?

Raw thresholds are unreliable in production because metrics naturally drift. MAD based detection is more robust than simplistic hard-coded thresholds because it compares current behavior to recent historical behavior.

### Special logic for memory leak

Memory is treated differently:

- `process_resident_memory_bytes` is a slow-drift metric
- a standard point anomaly detector is poor for this case
- the code uses a CUSUM-based drift detection path for that metric

This matters because a memory leak does not look like a sudden spike; it looks like gradual upward drift.

### Persistence filter

The detector does not flag a metric immediately on a single bad sample. It requires persistence for a few consecutive samples. This avoids false positives from one noisy or transient point.

---

## 5) Root-cause ranking pipeline

Once anomalies are detected, the project needs to determine which metric is the likely source of the incident, not just which metric moved.

### Main files

- `detector/rootcause/analysis.py`
- `detector/rootcause/topology.py`

### The key idea

The system assumes some metrics are likely causes and others are downstream symptoms.

Example:

- a CPU spike can cause app latency and error increase
- Redis latency can cause cache errors and higher app latency
- downstream latency can cause app latency and errors
- app availability is usually a final symptom, not the root cause

The file `topology.py` defines a dependency prior matrix showing which metrics can plausibly cause which other metrics.

### How the ranking works

For each anomaly event, the system computes:

- prior score: does this metric look causally upstream based on dependency topology?
- correlation score: does it move in a way that aligns with other affected metrics?
- onset score: does it begin earlier or in a more causal pattern than other signals?

Then it combines these into a confidence score for each candidate root cause.

### Why this matters

A naive pipeline might pick the earliest metric or the highest-moving metric. That often produces wrong results. This project tries to rank the metric that best explains the chain of failure, not just the first observed spike.

---

## 6) LangGraph diagnosis agent

After the statistical pipeline gives a ranked list of root-cause candidates, the LLM agent reviews the evidence.

### Main files

- `agent/graph.py`
- `agent/state.py`
- `agent/diagnosis.py`
- `agent/tool_nodes.py`
- `agent/llm.py`
- `agent/utils.py`

### The graph structure

`agent/graph.py` creates a LangGraph state machine with these major nodes:

1. `summarize_metric_evidence`
   - fetches metric snapshots around each candidate
   - summarizes them into evidence objects

2. `query_recent_app_logs`
   - reads application logs in the incident time window
   - extracts event counts and representative samples

3. `query_deploy_history`
   - looks for recent deploys in the surrounding time window
   - adds deployment context

4. `query_incident_history`
   - compares the current issue to previously logged incidents

5. `diagnose`
   - sends evidence + candidate ranking to the LLM
   - asks for a root-cause hypothesis and remediation recommendation

6. `investigate_additional_metrics`
   - if confidence is low or more evidence is needed, gathers more related metrics

7. `finalize`
   - converts the hypothesis into a concrete action decision

8. `approval_gate`
   - if the action is high risk, pauses for human approval via interrupt

9. `execute_remediation`
   - runs the actual action if allowed

### Important design choice

The LLM is not allowed to invent a diagnosis from raw telemetry. It only receives:

- the ranked candidate list from the deterministic detector
- evidence summaries from metrics, logs, deploy history, and historical incidents
- a strict prompt with safety instructions

The LLM is asked to compare candidates, prefer causes over symptoms, and choose among a restricted set of valid actions.

This keeps the intelligence useful but bounded.

---

## 7) Why the LLM is used at all

The statistical pipeline is strong, but some cases are ambiguous. For example, a metric can appear high because it is downstream from the real cause, not because it caused the problem.

The LLM layer helps by:

- comparing candidate metrics with evidence from logs and timing
- checking whether a metric is a true root cause or just a consequence
- overriding a bad prediction when the statistical signal is misleading
- deciding whether more evidence is needed before acting

This is exactly what the project demonstrates in the methodology and evaluation notes.

---

## 8) Remediation and safety guardrails

The remediation system is implemented in `agent/remediation.py`.

### Allowed action types

- `none`
- `flush_cache`
- `restart_service`
- `scale_out`
- `rollback_deploy`

### Safety principles

- high-risk actions require approval
- low-risk actions may execute directly
- diagnosis runs default to dry-run unless `AIOPS_DRY_RUN=false` is explicitly set
- actions are rejected if they do not fit the diagnosis
- the code explicitly blocks unsafe recommendations such as using cache flush on Redis latency alone without evidence of cache corruption

### Example behavior

- Redis latency alone does not justify a restart
- application outage may justify a restart
- sustained CPU pressure or high app latency may justify adding one Compose replica, up to three total; an Nginx proxy routes requests across replicas
- a recent deploy may justify a rollback if strongly linked; `scripts/deploy-compose.sh` preserves the previous app image and records deployment timestamps
- no remediation is recommended when the issue is ambiguous or not actionable

`scale_out` and `rollback_deploy` are implemented for this single-host Compose demo, not as production platform integrations. Both are high-risk actions and require approval in the interactive diagnosis graph. `scale_out` is rejected for unrelated root causes, and `rollback_deploy` is rejected unless recent deployment evidence exists. The direct helper scripts in the deployment guide are operator-invoked actions and do not ask for a second confirmation.

This is critical because the project is trying to demonstrate controlled, safe automation rather than reckless self-healing.

---

## 9) File-level map of the codebase

### `service/`
Responsible for the user-facing application and chaos injection endpoints.

- `main.py` — app setup and metrics middleware
- `routes.py` — business logic and Redis/downstream behavior
- `chaos_routes.py` — fault injection endpoints
- `chaos_state.py` — memory state for active faults
- `metrics.py` — Prometheus metric definitions

### `chaos/`
Responsible for injecting faults and recording them.

- `run_experiments.py` — fault runner
- `scripts/*.py` — scenario implementations
- `incident_logger.py` — logs known incident metadata

### `detector/`
Responsible for signal detection and root-cause ranking.

- `mad_detector.py` — anomaly detection
- `forecast_detector.py` — additional detection logic
- `metric_queries.py` — Prometheus query definitions
- `prometheus_api.py` — fetches metrics from Prometheus
- `evaluate.py` — detection evaluation
- `evaluate_rootcause.py` — root-cause ranking evaluation
- `rootcause/analysis.py` — core causal ranking logic
- `rootcause/topology.py` — dependency priors

### `agent/`
Responsible for the LLM-driven reasoning and remediation pipeline.

- `graph.py` — LangGraph workflow definition
- `state.py` — typed state for the agent
- `diagnosis.py` — LLM diagnosis and confidence logic
- `tool_nodes.py` — evidence gathering and approvals
- `remediation.py` — final action routing and execution
- `llm.py` — LLM call wrapper
- `utils.py` — prompt templates, evidence helpers, historical lookups
- `evaluate_diagnosis.py` — end-to-end diagnosis evaluator

### `data/`
Stores telemetry and labeled incident datasets used for evaluation.

- `baseline.parquet`
- `telemetry_48h_raw.parquet`
- `incidents/...`

### `logs/`
Stores JSONL logs from app activity and deployments.

- `app.jsonl`
- `deploys.jsonl`

---

## 10) How the project solves the problem in practice

The real value of the system is the combination of the following:

### Step A: Detect that something changed
Metrics are monitored continuously. The MAD detector identifies abnormal behavior in multiple metrics.

### Step B: Identify likely cause candidates
The dependency graph and timing patterns help rank which metrics are likely upstream causes.

### Step C: Provide evidence to a reasoning engine
The LangGraph agent gathers metric summaries, logs, deploy history, and historical incidents to support or challenge the top candidate.

### Step D: Reason with constraint
The LLM cannot take arbitrary actions. It must choose a root cause and remediation from a constrained and explainable framework.

### Step E: Gate risky actions
High-risk remediation is interrupted for approval. This prevents unsafe automatic restarts or destructive actions when confidence is low.

### Step F: Execute only if safe
If the diagnosis is accepted and safe, the chosen remediation is executed; otherwise the system skips action or asks for review.

In other words, the agent is not just "AI for alerts." It is a bounded, operational decision pipeline.

---

## 11) Example incident types this project simulates

The repo includes several incident families, each designed to stress a different part of the system:

- `redis_latency` — Redis slows down, increasing app latency and cache problems
- `redis_outage` — Redis is unavailable, causing app failures and timeouts
- `app_outage` — the app itself is down
- `downstream_latency` — external dependency becomes slow
- `downstream_failure` — downstream dependency errors out
- `cpu_spike` — resource saturation impacts request handling
- `memory_leak` — gradual memory growth causes slow degradation

Each of these produces characteristic metric patterns that the detector and root-cause pipeline must recognize.

---

## 12) Evaluation mindset

The repo includes evaluation scripts, which is important because this project is not just a demo. It has a methodology for measuring how well each stage works.

- `detector/evaluate.py` — tests anomaly detection performance
- `detector/evaluate_rootcause.py` — tests root-cause ranking quality
- `agent/evaluate_diagnosis.py` — tests the full diagnosis flow end-to-end

The project compares:

- naive detection alone
- statistical diagnosis
- statistical + LLM diagnosis

The documentation states that the combined pipeline improves accuracy over the naive and statistical-only approaches, which is the core claim of the project.

### Understanding your `agent.evaluate_diagnosis` screenshots

In the screenshots, the evaluator finished all 10 labeled incidents. Think of it as a test: each Parquet file contains telemetry from a known, injected fault. The program predicts a root-cause metric, then compares that prediction with the known expected metric. It is replaying saved incidents; it is not currently watching new production alerts continuously.

Here is what the output means:

- **`Root cause candidate: ... prior=... corr=... onset=... conf=...`** is Phase 3's statistical ranking. `prior` measures whether the dependency map says the candidate can explain other anomalous metrics; `corr` measures lagged correlation; `onset` rewards earlier detected deviation. The combined score is `0.5 * prior + 0.35 * corr + 0.15 * onset`. The highest confidence is Phase 3's leading hypothesis, not a guaranteed answer.
- **`conf` / `Average Confidence: 0.572`** is the system's score, not a calibrated probability. A score of `0.572` does not mean there is a verified 57.2% chance the diagnosis is right.
- **`nova_pro latency: ...`** means the Amazon Bedrock request completed and reports its duration. Your successful full run shows that the earlier `NoCredentialsError` is no longer stopping this evaluation. If that error returns, the EC2 instance still needs an attached IAM role with `bedrock:InvokeModel` permission for the configured model. Adding code to GitHub alone does not attach AWS permissions to an existing instance.
- **`Escalation decision: True`** means the agent asked its graph to gather related metric evidence and try diagnosis again. `False` means it will not escalate that attempt. The graph limits diagnosis iterations.
- **`Expected`** is the labeled ground-truth metric for the injected fault. **`Phase3`** is the statistical top candidate. **`LLM`** is the agent's final diagnosis after considering evidence. An LLM answer can differ from both the expected label and Phase 3.
- **`Ground Truth Accuracy: 80.00%`** means 8 of the 10 labeled cases in this run matched the expected root cause. It is a small sample: each incident changes the score by 10 percentage points. It is not a promise of 80% accuracy in production.
- **`Agreement with Phase 3: 80.00%`** means the LLM returned the same metric as the statistical ranking for 8 of 10 incidents. Agreement is not the same as correctness: both stages can agree on the wrong answer.
- **`LLM Overrides: 2` / `Correct Overrides: 1`** means the agent changed the Phase 3 answer twice; only one change corrected the ground-truth diagnosis. In this run, CPU spike was diagnosed as Redis latency, and the memory leak was diagnosed as downstream latency. The downstream-latency case where Phase 3 favored memory was corrected by the LLM; the CPU-spike ambiguity remains unresolved.
- **`Average Iterations`, `Evidence escalation`, and `Maximum iteration cases`** describe how often the agent queried more evidence before finishing. Your screenshots report average iterations of `1.90`, evidence escalation for `5/10` incidents, and `4/10` incidents reaching the iteration limit. A different successful run in the earlier pasted output reported `2.30`, `6/10`, and `6/10`; these can vary with LLM answers and live Prometheus evidence.
- In the remediation table, **`action: none`** means no repair was selected for that case, so the blank/`NaN` remediation status means no command was executed. `approval_status: approved` by itself does not mean a person approved an action; for `none`, there is no action to approve. The app-outage case selected `restart_service` and reports `executed`.

#### Reading the confusion matrix in your screenshot

Rows are the **expected** root causes; columns are the **predicted** root causes. Each cell counts incidents. Correct predictions are on the diagonal:

| Expected root cause | Predicted root cause | Cases |
|---|---|---:|
| `app_availability` | `app_availability` | 1 |
| `downstream_average_latency_seconds` | `downstream_average_latency_seconds` | 3 |
| `downstream_error_rate` | `downstream_error_rate` | 1 |
| `process_cpu_rate` | `redis_average_latency_seconds` | 1 |
| `process_resident_memory_bytes` | `downstream_average_latency_seconds` | 1 |
| `redis_average_latency_seconds` | `redis_average_latency_seconds` | 3 |

There are 10 cases total. The diagonal adds up to 8, so accuracy is 8 ÷ 10 = **80%**. The two off-diagonal cases are the CPU-spike incident and the memory-leak incident. The first was mistaken for Redis latency; the second for downstream latency. These are real errors, not successful detections.

#### What this says about the project

The evaluator does not let the LLM examine every raw time series and independently discover an answer. The statistical detector first finds unusual metrics; the topology/correlation logic ranks possible causes; then the LangGraph agent gathers context and asks Bedrock to choose or challenge a candidate. Finally, the system selects an action or does nothing. This structure makes the reasoning measurable, but the screenshots also show its limits: the answer can still be wrong, and 10 test cases are not enough to prove production reliability.

#### Latest pasted evaluation output

This run scored 10 labeled incidents. `memory_spike_84277f58.parquet` was skipped because it has no ground-truth label, so it is not included in the accuracy calculation.

```text
Ground Truth Accuracy:       80.00% (8 of 10)
Agreement with Phase 3:      80.00% (8 of 10)
Average Confidence:           0.572
Average Iterations:           2.30
Evidence escalation:          6 of 10 incidents
Maximum iteration cases:      6 of 10 incidents
LLM Overrides:                2
Correct Overrides:            1
```

The detailed diagnoses in the pasted output are:

| Incident | Expected root cause | Phase 3 candidate | Final LLM diagnosis | Result |
|---|---|---|---|---|
| `cpu_spike_52dcb84f` | `process_cpu_rate` | `downstream_average_latency_seconds` | `redis_average_latency_seconds` | Incorrect |
| `downstream_failure_fd739d70` | `downstream_error_rate` | `downstream_error_rate` | `downstream_error_rate` | Correct |
| `downstream_latency_a00e71c7` | `downstream_average_latency_seconds` | `downstream_average_latency_seconds` | `downstream_average_latency_seconds` | Correct |
| `app_outage_9fc6ee70` | `app_availability` | `app_availability` | `app_availability` | Correct |
| `downstream_latency_f222e70b` | `downstream_average_latency_seconds` | `downstream_average_latency_seconds` | `downstream_average_latency_seconds` | Correct |
| `downstream_latency_fdc80266` | `downstream_average_latency_seconds` | `process_resident_memory_bytes` | `downstream_average_latency_seconds` | Correct; LLM override |
| `memory_leak_35c25d43` | `process_resident_memory_bytes` | `downstream_average_latency_seconds` | `downstream_average_latency_seconds` | Incorrect |
| `redis_latency_b50614d5` | `redis_average_latency_seconds` | `redis_average_latency_seconds` | `redis_average_latency_seconds` | Correct |
| `redis_outage_5742c596` | `redis_average_latency_seconds` | `redis_average_latency_seconds` | `redis_average_latency_seconds` | Correct |
| `redis_outage_8db2dfbc` | `redis_average_latency_seconds` | `redis_average_latency_seconds` | `redis_average_latency_seconds` | Correct |

The two errors are the CPU-spike case, which the LLM labels as Redis latency, and the memory-leak case, which it labels as downstream latency. The LLM changed the Phase 3 answer twice and corrected one of those overrides (`downstream_latency_fdc80266`). A confidence of `0.572` is the system's score, not a calibrated 57.2% probability that its diagnoses are correct.

The remediation review shows that only the app-outage case selected `restart_service`, and that action was executed. The other nine cases selected `none`; their blank/`NaN` remediation status means no remediation command ran. The `memory_spike` case was not scored because it has no expected label. This is a small, synthetic evaluation set, so the 80% result is useful for understanding this run but is not a production-accuracy guarantee.

#### Important: the evaluator actually restarted the app

The screenshot is from an earlier run in which `agent.evaluate_diagnosis.py` auto-approved the graph interrupt and the app-outage case executed `docker compose restart aiops-app` (shown by `[+] Restarting 1/1`). The current code defaults to dry-run via `AIOPS_DRY_RUN=true`, but the evaluator still auto-approves interrupts. Keep the default for evaluation; do not run the evaluator with `AIOPS_DRY_RUN=false`.

The earlier `NoCredentialsError` was an AWS configuration issue, not an anomaly-detector failure. The current run's successful `nova_pro latency` lines show Bedrock was reachable and authenticated for this run; they do not prove that credentials are configured safely or that future runs will use the same AWS role. For the Terraform-created instance, the Bedrock permission is defined in `terraform/bedrock-policy.json`. An existing manually created EC2 instance needs an appropriate IAM role attached separately.

---

## 13) Important design limitations

This project is deliberately a lab and demo system, not a production-ready SaaS platform. The code includes several explicit limitations:

- it uses synthetic/self-generated incidents
- the app is intentionally simple and controlled
- the LLM is guarded but still relies on the quality of the metric pipeline
- some faults remain ambiguous and are not fully resolved in all cases
- `scale_out` and `rollback_deploy` are implemented only for the single-host Compose demo: scaling is capped at three replicas and rollback depends on the deployment helper's locally saved prior image
- deployment and rollback records are local JSONL files, not a durable CI/CD audit trail

This honesty is part of the architecture — the project is designed to demonstrate reasoning under constraints, not to be a fully autonomous production system.

---

## 14) What is the real takeaway?

This project is trying to show a practical pattern for modern AIOps:

- Use robust statistical detection for the noisy, high-volume part
- Use dependency-informed ranking to reduce false root causes
- Use an LLM only as a reasoning layer on top of evidence, not as a raw source of truth
- Add safety gates before any destructive action
- Keep diagnosis explainable and auditable

That is the core idea behind the system.

---

## 15) Typical execution flow in one sentence

A fault is injected into the app stack, telemetry is collected, anomaly detection finds suspicious metrics, dependency-aware root-cause ranking picks likely causes, the LangGraph agent compares candidates against logs and historical evidence, and safe remediation is executed only after approval when necessary.

---

## 16) Quick run summary

This repo supports running the service and fault experiments with Docker Compose and Python commands such as:

```bash
docker compose up --build -d
python3 -m chaos.run_experiments --fault redis_latency
python3 -m detector.evaluate
python3 -m detector.evaluate_rootcause
```

The full diagnosis evaluator uses the LLM path and therefore requires the proper task dependencies and access configuration.

---

## Final summary

This repository is a compact AIOps lab that demonstrates how to turn noisy operational telemetry into a safe and explainable diagnosis-and-remediation workflow.

It combines:

- service simulation
- chaos injection
- metric-based anomaly detection
- dependency-aware root-cause ranking
- LangGraph-based LLM reasoning
- human approval gates
- automated remediation under strict guardrails

That makes it a good teaching example of how an agentic AIOps system can be built without blindly trusting an LLM to control production infrastructure.
