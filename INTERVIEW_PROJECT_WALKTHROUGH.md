# AIOps Incident Diagnosis Project — Interview Walkthrough

Use this as a first-person explanation of the project. The short script is designed for an interview; the sections after it help you answer follow-up questions accurately.

For the final architecture diagram, see the [project README](README.md#architecture). For deeper technical detail, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [METHODOLOGY.md](METHODOLOGY.md), and [EXPLAINED_README.md](EXPLAINED_README.md).

## A two-minute project explanation

> “I built a small AIOps incident-diagnosis prototype to explore how we can reduce the time engineers spend investigating service failures without giving an AI unrestricted control of infrastructure.
>
> The project runs a FastAPI service with Redis and a simulated downstream dependency. Nginx routes requests to the app, Locust can generate traffic, and Prometheus collects application and process metrics for Grafana. I can use the chaos scripts to inject controlled examples such as Redis latency or outage, downstream latency or failure, an app outage, CPU pressure, and memory growth. Because these are self-injected test incidents, I know the expected fault label and can measure the diagnosis.
>
> The diagnosis is deliberately layered. First, statistical detectors flag anomalous metrics: most use a rolling median and median absolute deviation, while gradual memory growth uses CUSUM. A persistence filter reduces reactions to one noisy sample. Next, a root-cause stage ranks candidates using the service dependency map, lagged correlation, and onset timing.
>
> The LangGraph agent then gathers context such as Prometheus measurements, application logs, deployment records, and similar chaos incidents. Amazon Bedrock receives the ranked candidates and evidence and can accept or challenge the statistical result. The model is constrained to the evidence and a fixed remediation action set. High-risk actions require approval in interactive runs, and the default is dry-run.
>
> On the 10 labeled incidents in the evaluation output I documented, the final diagnosis was correct in 8 cases, or 80 percent. The CPU-spike and memory-leak cases were wrong, so I treat this as a small prototype evaluation rather than a production accuracy claim. Only the app-outage case executed a restart in that run; the other incidents resulted in no action.
>
> One important limitation is that this is not yet an always-on AIOps service. Docker Compose runs the application and monitoring stack, but the evaluator is started separately and builds its initial diagnosis from saved incident datasets. The agent may query live Prometheus and local logs for supporting evidence. The Compose scale-out example is limited to three replicas on one host; it is not AWS Auto Scaling. My next steps would be improving labeled evaluation coverage, integrating live alerting and real deployment context, and adding production-grade identity, audit, and policy controls.”

## What the project is solving

During an incident, many signals can change together. For example, a slow dependency can increase request latency, create errors, and affect the application. A chart can show that something changed, but it does not by itself show which signal is the cause, which is a symptom, or whether a repair is safe.

This project demonstrates a measurable workflow for:

1. Producing controlled service incidents.
2. Detecting unusual metric behavior.
3. Ranking plausible root causes rather than selecting a symptom blindly.
4. Gathering operational evidence for a diagnosis.
5. Recommending a limited action or doing nothing when evidence is insufficient.
6. Gating higher-risk remediation and recording the evaluation result.

It is a learning/evaluation prototype, not a production incident-management platform.

## Architecture diagram explained

The [README architecture diagram](README.md#architecture) has four sections:

### 1. Running demo stack

- A Locust user or another API caller sends traffic through the Nginx proxy to FastAPI.
- FastAPI handles requests using Redis and a simulated `catalog` downstream dependency.
- Prometheus scrapes the app's `/metrics` endpoint; Grafana displays the collected metrics.
- Structured application logs, chaos incident records, and deployment records provide additional evidence.
- Chaos is an explicit test operation. It can call the app's fault-control endpoints or perform bounded container actions; it is not the diagnosis trigger.

### 2. Explicit diagnosis/evaluation run

The command `python -m agent.evaluate_diagnosis` starts the evaluation workflow. It reads a baseline and labeled incident windows from Parquet datasets, runs the detector, and ranks root-cause candidates. This initial evaluation input is saved data, not an automatically generated alert from the live Grafana dashboard.

### 3. LangGraph evidence and diagnosis

The ranked candidate list becomes typed agent state. Graph nodes gather relevant metrics and logs, nearby deployment information, and incident-history evidence. If the result needs more context and the iteration limit has not been reached, the graph expands its investigation to related metrics. The LLM is asked to reason over those candidates and evidence; the statistical pipeline remains responsible for the quantitative ranking.

### 4. Safety gate and outcome

The agent validates recommendations against supported actions and policy. It can select no action, use a low-risk action, or pause a high-risk action for approval in an interactive run. Remediation defaults to dry-run. The final report includes the diagnosis and remediation status.

## Start-to-finish technical flow

1. **Start the app and observability stack.** Docker Compose starts FastAPI, Redis, Nginx, Prometheus, Grafana, and Locust. Locust's web UI does not generate traffic until a test is started.
2. **Create traffic and, optionally, an isolated fault.** Request traffic produces app and dependency metrics. A selected chaos script injects a defined fault and records its known type and timing.
3. **Prepare the incident evaluation data.** Saved baseline and incident Parquet files provide the evaluator with telemetry windows and expected labels. The fault label is what makes accuracy measurable in this lab.
4. **Detect anomalies.** `detector/mad_detector.py` scores most metrics against a rolling median/MAD reference. Memory uses a one-sided CUSUM path for gradual drift. A persistence filter requires repeated abnormal observations to suppress one-sample noise.
5. **Rank root-cause candidates.** `detector/rootcause/analysis.py` combines a dependency prior, lagged correlation, and onset timing. The dependency prior encodes plausible cause/effect relationships for this small application.
6. **Build diagnosis state.** `agent/build_state.py` packages the incident window and ranked candidates into typed state for the graph.
7. **Gather evidence and reason.** `agent/graph.py` runs evidence nodes in `agent/tool_nodes.py`, then invokes the diagnosis logic in `agent/diagnosis.py` and `agent/llm.py`. Bedrock may select a different candidate, but the answer is limited by the supplied evidence and statistical confidence.
8. **Escalate only when needed.** If the diagnosis needs more evidence and attempts remain, the graph investigates related metrics and tries again. The graph has a bounded iteration limit.
9. **Apply the safety decision.** `agent/remediation.py` validates the selected action and risk. High-risk actions use an approval interrupt in interactive graph runs; dry-run prevents container changes.
10. **Review the outcome.** The evaluator reports expected and predicted root cause, Phase 3 candidate, confidence, iterations, chosen action, approval status, and remediation result.

### What is live and what is not

| Part | Current behavior |
|---|---|
| FastAPI, Redis, Nginx, Prometheus, Grafana, Locust | Run as a Docker Compose demo stack |
| Prometheus metrics and Grafana charts | Live while the stack is running and being scraped |
| Chaos injection | Explicitly started against the isolated demo |
| Initial diagnosis/evaluation input | Saved baseline and labeled incident Parquet data |
| Agent evidence collection | Can query live Prometheus and local logs during a diagnosis run |
| Automatic alert-to-diagnosis loop | Not implemented |
| AWS scaling | Not implemented as an Auto Scaling Group; demo scale-out is bounded to three Compose replicas on one EC2 host |

## How to explain the evaluation output

The run documented in [EXPLAINED_README.md](EXPLAINED_README.md#latest-pasted-evaluation-output) scored 10 labeled incidents:

- **Ground-truth accuracy: 80%** — 8 final diagnoses matched expected labels.
- **Agreement with Phase 3: 80%** — the LLM's final answer matched the statistical candidate in 8 cases. Agreement does not imply correctness.
- **Average confidence: 0.572** — this is a system score, not a calibrated probability.
- **Average iterations: 2.30** — the agent made additional evidence passes in some cases.
- **LLM overrides: 2; correct overrides: 1** — one override corrected the statistical ranking; another did not.
- **Errors:** the CPU-spike incident was diagnosed as Redis latency, and the memory-leak incident was diagnosed as downstream latency.
- **Remediation:** only the app-outage incident selected and executed `restart_service`; the other scored incidents selected `none`.

The separate `memory_spike` record had no ground-truth label and was skipped, so it does not count in the ten-case score. With only ten labeled examples, one incident changes accuracy by ten percentage points. These results describe this run, not expected performance in production.

## How to run the demo safely

From the project root:

```bash
bash scripts/setup-env.sh
docker compose up --build -d
docker compose ps
```

Start low-volume Locust traffic in its UI if needed. To run a controlled experiment on the isolated demo:

```bash
python3 -m chaos.run_experiments --fault redis_latency
```

For a detector-only check:

```bash
python3 -m detector.evaluate
python3 -m detector.evaluate_rootcause
```

The full agent evaluation needs its Python dependencies, a running local Prometheus service, and valid AWS Bedrock access:

```bash
AIOPS_DRY_RUN=true python3 -m agent.evaluate_diagnosis
```

**Keep the evaluator in dry-run mode.** `agent.evaluate_diagnosis` automatically approves graph approval interrupts, so do not run it with `AIOPS_DRY_RUN=false`. Chaos endpoints are unauthenticated and experiments can disrupt the app; do not expose them to public networks or run them against production. See [INTERVIEW_AND_DEPLOYMENT_GUIDE.md](INTERVIEW_AND_DEPLOYMENT_GUIDE.md) for the full Ubuntu and AWS instructions.

## Interview questions you may be asked

### Why use an LLM if you already rank root causes statistically?

The detector and ranking stage produces a quantitative shortlist. The LLM helps compare the shortlist with contextual evidence such as logs and deployment history, and can challenge an ambiguous candidate. It is not a replacement for the detector and should not invent a cause from unconstrained raw telemetry.

### Does correlation prove causation?

No. The dependency map, lagged correlation, and onset timing are evidence used to rank candidates, not proof of causality. The topology is manually maintained for this demo. Distributed traces, service-catalog data, and broader reviewed incident history would improve a real deployment.

### How are risky actions controlled?

The action set is restricted and validated. The default is dry-run, and high-risk actions pause for approval in interactive graph runs. The evaluator is a special case because it automatically approves interrupts, which is why it must always run in dry-run mode.

### Is this production-ready or highly available?

No. It is a single-host learning system with self-generated incidents, local JSONL history, a small labeled dataset, and no continuous alert consumer. Compose scale-out adds up to three replicas on the same host; it is not AWS Auto Scaling. Production use would require stronger authentication and authorization, durable auditing, monitored failure paths, real operational integrations, larger held-out evaluations, and platform-native scaling and rollback.

## Related project documentation

- [README.md](README.md) — project overview, results, and final architecture diagram.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — detailed component/data-flow map.
- [METHODOLOGY.md](METHODOLOGY.md) — detection formulas, ranking, case studies, and production path.
- [EXPLAINED_README.md](EXPLAINED_README.md) — broad project explanation and pasted evaluator output.
- [INTERVIEW_AND_DEPLOYMENT_GUIDE.md](INTERVIEW_AND_DEPLOYMENT_GUIDE.md) — interview Q&A and deployment steps.
- [terraform/README.md](terraform/README.md) — cost-conscious AWS deployment details.
- [ROADMAP.md](ROADMAP.md) — proposed improvements and production-readiness direction.
