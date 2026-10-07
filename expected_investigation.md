# Expected investigation: job-001

This file is evaluation data. The investigator must not receive it as evidence.

## report-A

- Conclusion: Delivered.
- Supporting evidence: `attempt-A-1` and `receipt-A-1`.
- Recommended action: None.

## report-B

- Conclusion: Delivered, but the sender's recorded status is unresolved.
- Supporting evidence: `attempt-B-1` and `receipt-B-1`.
- Recommended action: Reconcile the sender's delivery status. Do not resend.

## report-C

- Conclusion: Delivery could not be attempted successfully because destination
  configuration is missing.
- Supporting evidence: `attempt-C-1` and the absence of a configuration record
  for `destination-C`.
- Recommended action: Repair the destination configuration before retrying.

# Holdout investigations

These cases are also evaluation data and must not be included in model prompts.

## job-002: failure and uncertainty

### report-D

- Conclusion: Delivery failed with no recipient receipt while valid destination
  configuration exists.
- Supporting evidence: `attempt-D-1`.
- Recommended action: Retry delivery.

### report-E

- Conclusion: Insufficient evidence. The report is queued, destination
  configuration exists, and no attempt or recipient receipt is recorded.
- Supporting evidence: `report-E` and `destination-E`.
- Recommended action: Investigate whether delivery was attempted; do not retry
  until that uncertainty is resolved.

## job-003: multi-report scale

Each report from `report-scale-01` through `report-scale-06` was delivered.
Every finding must cite its corresponding `attempt-scale-NN` and
`receipt-scale-NN`. No action is required.
