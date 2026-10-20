# Project Architecture and Runtime Flow

This page follows the project from a fault being injected into the demo service to the final diagnosis and remediation decision. The diagrams map each stage to the code that implements it.

> **Important runtime distinction:** the service, Prometheus, and fault injectors can run continuously in Docker Compose. The current detector-to-agent diagnosis path is an evaluation workflow over saved Parquet baseline/incident data; it is not yet an always-on alert consumer. `agent/evaluate_diagnosis.py` builds the diagnosis state from a dataset, then invokes the LangGraph agent, whose evidence nodes query live Prometheus and local logs.

## End-to-end architecture

```mermaid
flowchart TB
    subgraph LAB["1 · Demo system and fault injection"]
        direction LR
        USER["Traffic generator / API caller<br/>chaos/locustfile.py"]
        PROXY["Nginx proxy<br/>app-proxy:8000"]
        CLI["Experiment CLI<br/>chaos/run_experiments.py"]
        INJECT["Chaos scripts<br/>chaos/scripts/*.py"]
        CHAOS_API["Fault-control endpoints<br/>service/chaos_routes.py"]
        CHAOS_STATE["In-memory fault state<br/>service/chaos_state.py"]
        API["FastAPI app replicas (1–3)<br/>service/main.py · service/routes.py"]
        REDIS[("Redis")]
        DOWNSTREAM["Simulated catalog dependency"]
        USER --> PROXY --> API
        CLI --> INJECT
        INJECT -->|"HTTP controls / container actions"| CHAOS_API
        CHAOS_API --> CHAOS_STATE
        CHAOS_STATE -. "delay · failure · CPU · memory" .-> API
        API --> REDIS
        API --> DOWNSTREAM
    end

    subgraph OBS["2 · Observable signals"]
        direction LR
        METRICS["Prometheus metrics<br/>service/metrics.py"]
        LOGS[("Structured app logs<br/>logs/app.jsonl")]
        DEPLOYS[("Deploy history<br/>logs/deploys.jsonl")]
        PROM["Prometheus scraper<br/>prometheus/prometheus.yml"]
        PDB[("Prometheus time series")]
        API --> METRICS
        API --> LOGS
        PROM -->|"scrapes /metrics"| METRICS
        PROM --> PDB
    end

    subgraph EVAL["3 · Detection and statistical root-cause ranking (dataset evaluation)"]
        direction LR
        RUNNER["Evaluation entry point<br/>agent/evaluate_diagnosis.py"]
        DATA[("data/baseline.parquet<br/>data/incidents/*.parquet")]
        EVAL_INC["Incident window + detector<br/>detector/evaluate.py"]
        MAD["MAD / CUSUM anomaly scores<br/>detector/mad_detector.py"]
        EVENTS["Anomaly events<br/>onset · offset · peak"]
        RANK["Causal ranking<br/>detector/rootcause/analysis.py"]
        TOPO["Dependency prior<br/>detector/rootcause/topology.py"]
        CANDIDATES["Ranked candidates + confidence<br/>prior · lag correlation · onset"]
        RUNNER --> DATA --> EVAL_INC --> MAD --> EVENTS --> RANK --> CANDIDATES
        TOPO --> RANK
    end

    subgraph AGENT["4 · LangGraph evidence and diagnosis"]
        direction TB
        BUILD["Build typed incident state<br/>agent/build_state.py"]
        GRAPH["LangGraph workflow<br/>agent/graph.py"]
        METRIC_E["Metric evidence<br/>agent/tool_nodes.py → Prometheus"]
        LOG_E["Incident-window log evidence<br/>agent/tool_nodes.py → logs/app.jsonl"]
        DEPLOY_E["Recent deploy evidence<br/>agent/tool_nodes.py → logs/deploys.jsonl"]
        HISTORY_E["Similar incident evidence<br/>agent/tool_nodes.py → chaos/incidents.log"]
        LLM["Evidence-grounded diagnosis<br/>agent/diagnosis.py · agent/llm.py"]
        BEDROCK["Amazon Bedrock<br/>configured model provider"]
        MORE{"Confidence sufficient,<br/>or iteration limit reached?"}
        EXTEND["Investigate related metrics<br/>agent/tool_nodes.py"]
        DIAGNOSIS["Root cause · hypothesis · confidence<br/>recommended action · reasoning"]

        BUILD --> GRAPH
        GRAPH --> METRIC_E --> LOG_E --> DEPLOY_E --> HISTORY_E --> LLM
        LLM <-->|"model request / response"| BEDROCK
        LLM --> MORE
        MORE -->|"No: needs evidence and under 3 iterations"| EXTEND
        EXTEND --> LLM
        MORE -->|"Yes"| DIAGNOSIS
    end

    subgraph ACTION["5 · Safety gate and outcome"]
        direction LR
        FINALIZE["Validate action and risk<br/>agent/remediation.py"]
        ROUTER{"Action?"}
        APPROVAL["Human approval interrupt<br/>agent/tool_nodes.py"]
        APPROVED{"Approved?"}
        EXEC["Execute supported action<br/>agent/remediation.py"]
        RESULT["Recorded result<br/>executed · dry_run · skipped · failed"]
        NOOP["Finish without action"]

        FINALIZE --> ROUTER
        ROUTER -->|"none"| NOOP
        ROUTER -->|"high-risk action"| APPROVAL
        APPROVAL --> APPROVED
        APPROVED -->|"No"| NOOP
        APPROVED -->|"Yes"| EXEC
        ROUTER -->|"low-risk action"| EXEC
        EXEC --> RESULT
    end

    CANDIDATES --> BUILD
    PDB -. "Queried by evidence nodes" .-> METRIC_E
    LOGS -. "Read for incident window" .-> LOG_E
    DEPLOYS -. "Read around incident" .-> DEPLOY_E
    DIAGNOSIS --> FINALIZE

    classDef app fill:#123047,stroke:#39bdf8,color:#f0f9ff,stroke-width:2px
    classDef telemetry fill:#12372f,stroke:#34d399,color:#ecfdf5,stroke-width:2px
    classDef analysis fill:#342654,stroke:#c4b5fd,color:#f5f3ff,stroke-width:2px
    classDef agent fill:#493314,stroke:#fbbf24,color:#fffbeb,stroke-width:2px
    classDef safety fill:#48212a,stroke:#fb7185,color:#fff1f2,stroke-width:2px
    classDef store fill:#17202b,stroke:#94a3b8,color:#f8fafc

    class API,CHAOS_API,CHAOS_STATE,CLI,INJECT,USER,REDIS,DOWNSTREAM app
    class METRICS,PROM telemetry
    class RUNNER,EVAL_INC,MAD,EVENTS,RANK,TOPO,CANDIDATES analysis
    class BUILD,GRAPH,METRIC_E,LOG_E,DEPLOY_E,HISTORY_E,LLM,BEDROCK,EXTEND,DIAGNOSIS agent
    class FINALIZE,ROUTER,APPROVAL,APPROVED,EXEC,RESULT,NOOP safety
    class LOGS,DEPLOYS,PDB,DATA store
```

## Runtime walkthrough

The expected evaluation path, from the repository root, is:

```text
python -m agent.evaluate_diagnosis
    ├─ Read baseline and labeled incident Parquet files
    ├─ detector/evaluate.py
    │    └─ detector/mad_detector.py: score metrics and emit sustained anomaly flags
    ├─ agent/build_state.py
    │    └─ detector/rootcause/analysis.py + topology.py: extract and rank candidate causes
    ├─ agent/graph.py
    │    ├─ Gather metric, log, deploy, and incident-history evidence
    │    ├─ agent/diagnosis.py → agent/llm.py → configured LLM provider
    │    ├─ If uncertain: inspect related metrics and diagnose again (up to 3 attempts)
    │    └─ Finalize action → approval interrupt if high risk → supported executor
    └─ Print diagnosis, evaluation result, and remediation status
```

The service's telemetry and Prometheus are live inputs for evidence collection, but the **initial alert and ranked candidate list are currently built from saved incident datasets** by the evaluation harness. A future always-on workflow would connect live Prometheus alerting to the same state-building and diagnosis stages.

## What each stage passes forward

| Stage | Input | Output | Main code |
|---|---|---|---|
| Fault injection | Fault type and parameters | Fault state, timing, and ground-truth incident record | `chaos/run_experiments.py`, `chaos/scripts/`, `service/chaos_routes.py` |
| Service telemetry | API requests and active fault state | Prometheus metrics and structured logs | `service/routes.py`, `service/metrics.py`, `service/logger.py` |
| Detection | Baseline plus incident time series | Per-metric scores and persistent anomaly flags | `detector/evaluate.py`, `detector/mad_detector.py` |
| Candidate ranking | Anomaly events and aligned metric window | Ordered root-cause candidates with confidence features | `detector/rootcause/analysis.py`, `detector/rootcause/topology.py` |
| State construction | Candidate list and incident window | Typed `DiagnosisState` for the graph | `agent/build_state.py`, `agent/state.py` |
| Evidence gathering | Diagnosis state and incident time window | Metric summaries, app logs, deploy history, similar incidents | `agent/tool_nodes.py`, `agent/utils.py` |
| LLM diagnosis | Ranked candidates plus gathered evidence | Hypothesis, root cause, confidence, action, reasoning | `agent/diagnosis.py`, `agent/llm.py`, `agent/utils.py` |
| Safety and remediation | Recommended action and diagnosis state | Approval pause, no-op, or action result | `agent/remediation.py`, `agent/tool_nodes.py`, `agent/graph.py` |

## Remediation boundary

The Compose demo implements `scale_out` by adding one `aiops-app` replica behind the Nginx proxy, with a maximum of three replicas. `rollback_deploy` restores the prior image tagged by `scripts/deploy-compose.sh` and requires recent deployment evidence. Both actions are high-risk and require approval in the interactive graph. Remediation defaults to dry-run through `AIOPS_DRY_RUN=true`; the diagnosis evaluator still auto-approves approval interrupts, so never run that evaluator with live remediation enabled. The app image deploy, scale, and rollback scripts are documented in the end-to-end [deployment guide](../INTERVIEW_AND_DEPLOYMENT_GUIDE.md).

These actions are single-host Compose demonstrations, not production autoscaling or a production rollback controller. The deployment history is a local JSONL file, and helper scripts invoked directly do not add a separate confirmation prompt.

The chaos endpoints are also unauthenticated. Keep them isolated; do not expose them or the demo dashboards directly to the public internet.

## Related documentation

- [README.md](../README.md) — project overview and results.
- [METHODOLOGY.md](../METHODOLOGY.md) — detector, ranking, and evaluation details.
- [INTERVIEW_AND_DEPLOYMENT_GUIDE.md](../INTERVIEW_AND_DEPLOYMENT_GUIDE.md) — walkthrough and deployment guide.
- [ROADMAP.md](../ROADMAP.md) — proposed future work.
- [terraform/README.md](../terraform/README.md) — cost-conscious AWS demo deployment.
