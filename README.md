# AI Report Delivery Investigator

This project investigates why scheduled reports were not delivered and proposes
evidence-backed recovery actions. It includes both a fast single-pass baseline
and a LangGraph agent so their quality, latency, and cost can be compared rather
than assumed.

The central failure scenario is deliberately ambiguous: a sender can time out
waiting for a response even though the recipient has already accepted the
report. Treating that timeout as proof of failure could cause a duplicate
delivery.

## Architecture

The two investigation modes share the same SQLite evidence and structured
`InvestigationResult` contract:

```text
Baseline
SQLite repository -> collect_job_evidence() -> JobEvidence
                  -> one OpenAI Structured Outputs request
                  -> InvestigationResult

Agent
SQLite repository -> LangChain repository tools -> LangGraph tool loop
                  -> structured finalization request
                  -> InvestigationResult
```

The baseline is the default because the current evidence is cheap to collect
and fits in one model context. The agent path is retained for a production-like
future in which evidence is distributed across logs, dashboards, services, and
code, and adaptive retrieval can justify its extra model calls. See
[`docs/adr/001-use-baseline-by-default.md`](docs/adr/001-use-baseline-by-default.md)
for measured results.

Delivery and recovery form a separate workflow:

```text
Sender -> recipient stores receipt -> recipient acknowledges
   |                 |
   +------ SQLite attempts and receipts ------+
                                              |
                                    investigation result
                                              |
                                    human approval pause
                                              |
                                      fresh receipt recheck
                                        /             \
                              already delivered     safe retry
```

The recipient stores the receipt before responding. The sender uses a stable
delivery key and records each attempt. Recovery pauses for human approval,
rechecks live receipt state, and only retries when no receipt exists. A SQLite
`UNIQUE` constraint on the delivery key is the final protection against
duplicate acceptance.

## Run locally

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add your key to a local `.env` file:

```text
OPENAI_API_KEY=your-key
```

The CLI loads `.env` automatically. Seed the demonstration database and run an
investigation:

```bash
python seed.py
python cli.py job-001 --mode baseline
python cli.py job-001 --mode agent
```

Both modes default to `gpt-4o-mini`; select another model with `--model`.

## Evaluate the result

Save CLI output to a JSON file, then run the deterministic evaluator:

```bash
python eval_cli.py result.json
```

The evaluator checks diagnosis categories, evidence citations, unresolved
questions, and recommended actions. The experiment runner also compares
correctness, latency, model calls, tool calls, and token usage:

```bash
python experiment_cli.py job-001 --runs 3
```

## Tests

```bash
python -m pytest -q
```

The real HTTP integration test proves the key distributed-systems
contradiction: the sender records a timeout while the recipient has already
stored a receipt.

```bash
python -m pytest \
  tests/test_sender.py::test_sender_times_out_after_recipient_accepts_delivery \
  -q
```

Recovery behavior is covered independently:

```bash
python -m pytest tests/test_recovery_graph.py -q
```

## Safety properties

- Recipient state is committed before an acknowledgement is sent.
- Delivery keys are stable across retries.
- Only an HTTP read timeout is classified as `timed_out`; unrelated failures
  are not hidden.
- Recovery requires explicit human approval.
- Approved recovery reads current state instead of trusting stale evidence.
- SQLite decides atomically which request creates a receipt.
- Replaying the same delivery key returns the original receipt.

The recovery tests use LangGraph's in-memory checkpointer. A production service
would use durable checkpoint storage, authenticated approval identities,
least-privilege evidence connectors, and operational telemetry.
