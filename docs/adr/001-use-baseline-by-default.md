# ADR 001: Use the single-pass baseline by default

- Status: Accepted
- Date: 2026-10-07

## Context

The investigator has two implementations:

1. A baseline that collects all SQLite evidence before making one structured
   OpenAI request.
2. A LangGraph agent that decides which repository tools to call before a
   separate structured finalization request.

## Model configuration

The initial benchmark and first holdout comparison used OpenAI's
`gpt-4o-mini`. A second `job-002` comparison used OpenAI's `gpt-6.1-sol`, a
stronger model selected to test whether model capability changes the
architecture decision.

Within each comparison, the baseline and agent use the same model. This keeps
the experiment focused on the orchestration design: one structured request for
the baseline versus iterative tool use followed by structured finalization for
the agent.

## Primary benchmark

Both implementations were evaluated three times against the same deterministic
`job-001` rubric.

| Metric | Baseline | Agent |
|---|---:|---:|
| Passing runs | 3/3 | 3/3 |
| Average score | 1.0 | 1.0 |
| Average latency | 6.09 seconds | 17.05 seconds |
| Average LLM calls | 1.0 | 4.67 |
| Average tool calls | 0 | 10.33 |
| Total tokens | 5,706 | 13,660 |

The agent was 2.80 times slower and used 2.39 times as many tokens without a
correctness improvement.

## First holdout result

One `job-002` run tested a previously unseen delivery failure and a report with
insufficient evidence. Both implementations used `gpt-4o-mini`.

| Metric | Baseline | Agent |
|---|---:|---:|
| Passing runs | 0/1 | 0/1 |
| Evaluation score | 0.643 | 0.786 |
| Latency | 4.85 seconds | 15.42 seconds |
| LLM calls | 1 | 5 |
| Tool calls | 0 | 7 |
| Total tokens | 1,587 | 3,609 |

The agent performed better on correctness by assigning the expected
`insufficient_evidence` diagnosis and `investigate` action to `report-E`. The
baseline incorrectly classified that report as missing destination
configuration. However, neither implementation passed: both omitted the
required unresolved question and chose `investigate` instead of
`retry_delivery` for `report-D`; the agent also omitted required evidence
citations.

This is an encouraging signal for adaptive evidence gathering, not yet evidence
that the agent should become the default. It comes from one run, the agent still
failed the rubric, took 3.18 times as long, and used 2.27 times as many tokens.

## Stronger-model holdout result

The `job-002` holdout was then run once with `gpt-6.1-sol`.

| Metric | Baseline | Agent |
|---|---:|---:|
| Passing runs | 1/1 | 1/1 |
| Evaluation score | 1.0 | 1.0 |
| Latency | 8.84 seconds | 34.47 seconds |
| LLM calls | 1 | 7 |
| Tool calls | 0 | 12 |
| Total tokens | 1,659 | 5,793 |
| Stop reason | Complete | Tool limit |

The stronger model eliminated the correctness gap: both implementations passed
every deterministic check. The agent reached the tool-call limit but still
produced a complete passing result from the evidence it had gathered.

The baseline remained 3.90 times faster and the agent used 3.49 times as many
tokens. For evidence that is already inexpensive to collect, increasing model
capability improves quality but does not justify the agent's orchestration
overhead.

## Decision

Use the single-pass baseline as the default for jobs whose evidence can be
collected cheaply and fits within the model context window.

Keep agent mode as an experimental path for cases where evidence is too large,
expensive, remote, or incomplete enough that adaptive retrieval could avoid
unnecessary work or resolve uncertainty.

## Consequences

- Production behavior remains simpler, faster, and cheaper for the current
  workload.
- Agent mode must demonstrate an improvement on holdout cases before becoming
  the default. A higher partial score is useful evidence, but promotion requires
  consistent passing results or a justified quality/cost tradeoff.
- Evaluation compares correctness, latency, model calls, tool calls, and token
  usage; architectural complexity alone is not treated as a benefit.
- `job-002` tests unseen failure and insufficient-evidence behavior.
- `job-003` tests whether the current tool-calling loop scales across several
  expected reports without exhausting its tool-call budget.
