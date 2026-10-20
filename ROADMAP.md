# Project Roadmap

This roadmap describes a proposed direction for evolving the AIOps demo. It is a planning document, not a promise of delivery dates. Items below are future work unless they are already explicitly marked complete in the codebase.

## Project goal

Grow the current chaos-engineered prototype into a more reliable, testable, and secure incident-response system while retaining its central design principle: statistical detection and observable evidence should ground diagnosis, and automation should remain constrained by explicit safety controls.

## Phase 1 — Make the current workflow safer and more dependable

**Priority: highest**

- Make dry-run behavior the default for evaluation and local agent runs; require an explicit opt-in to execute changes.
- Validate model output against typed schemas, including root cause, confidence, evidence references, and allowed remediation actions.
- Ensure malformed model responses, missing evidence, and tool failures produce a visible no-action outcome with a useful error record.
- Add structured decision and approval audit records: incident ID, evidence references, model/action decision, approval decision, and execution result. Avoid logging credentials or unnecessary personal data.
- Add focused tests for approval/rejection, confidence escalation limits, action allowlists, and remediation failure handling.

**Exit criteria:** automated tests demonstrate that invalid or uncertain diagnoses cannot execute remediation, high-risk actions always pause for approval, and failures remain visible rather than appearing successful.

## Phase 2 — Improve evaluation quality and diagnosis accuracy

**Priority: high**

- Expand labeled chaos experiments across fault types, durations, load levels, and combinations of faults.
- Track detection precision/recall and time-to-detect, root-cause top-k accuracy, diagnosis confidence calibration, and unsafe-action rate.
- Add repeatable regression tests for known cases, including the ambiguous CPU-spike case and the downstream-latency override.
- Separate evaluation runs from live infrastructure state by using saved, versioned telemetry windows where appropriate.
- Record dataset versions, detector configuration, prompts, model identifier, and run results so comparisons can be reproduced.

**Exit criteria:** evaluation produces a repeatable report with per-fault results and enough labeled cases to make accuracy changes interpretable; known failure cases are visible in the report rather than hidden by aggregate scores.

## Phase 3 — Improve signals and root-cause evidence

**Priority: high**

- Evaluate seasonal baselines for traffic and latency so normal time-of-day patterns do not cause alert noise.
- Address the current ambiguous candidate rankings with targeted experiments and transparent comparisons; do not tune only to improve the existing small sample.
- Add trace or dependency-span evidence so causal relationships can be observed rather than relying only on a manually maintained topology table.
- Add telemetry freshness, missing-data, and scrape-health checks, and report when a diagnosis is based on incomplete measurements.
- Version and document metric definitions, detector thresholds, and topology assumptions.

**Exit criteria:** detector and ranking changes improve held-out evaluation results without materially increasing false alarms, and diagnoses clearly identify missing or stale evidence.

## Phase 4 — Connect real operational context

**Priority: medium**

- Replace self-logged deploy history with a read-only integration to a CI/CD source such as GitHub Actions or Argo CD.
- Replace local incident-log similarity with a controlled, read-only source of confirmed incident reports or postmortems.
- Add operator feedback for confirming or correcting diagnoses and actions.
- Use confirmed feedback to improve evaluation datasets and measure performance over time; do not silently train or change production behavior from unreviewed feedback.

**Exit criteria:** integrations use scoped credentials, fail safely when unavailable, and record the source and timestamp of evidence used in each diagnosis.

## Phase 5 — Production-readiness and deployment choices

**Priority: later, after safety and evaluation work**

- Define a production threat model and review authentication, authorization, secrets management, network exposure, data retention, and audit requirements.
- Replace the single-instance demo setup with a deployment architecture appropriate to real availability and workload requirements.
- Add infrastructure monitoring, backups, recovery procedures, resource limits, and cost alerts.
- Separate the demo fault-injection controls from any production application and require explicit authorization for disruptive experiments.
- Replace direct host-level Docker remediation with scoped, authenticated platform APIs and per-action policy controls.

**Exit criteria:** security and operational reviews are complete, recovery and rollback have been tested, and every automated action has an owner, policy, observable outcome, and tested failure path.

## Guiding principles

1. **Safety before autonomy:** keep recommendations in dry-run or approval-gated mode until the complete execution path has been reviewed and tested.
2. **Evidence before explanation:** every diagnosis should cite observable evidence and disclose uncertainty or missing data.
3. **Measure changes on held-out cases:** avoid optimizing thresholds or prompts against only the incidents used to develop them.
4. **Prefer read-only integrations first:** establish evidence quality before granting systems the ability to change infrastructure.
5. **Keep deployment proportional:** use the current low-cost single-instance setup for demos; introduce managed or highly available components only when the requirements justify their cost.
