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
