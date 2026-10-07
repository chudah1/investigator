DECISION_POLICY = """
Apply these diagnosis and action rules consistently:

- Use `delivered` when a recipient receipt confirms delivery and the sender
  recorded success.
- Use `delivered_with_sender_status_unresolved` when a recipient receipt
  confirms delivery but the sender recorded a timeout or other failure. Add a
  `reconcile_sender_status` or `investigate` action, and never retry delivery.
- Use `destination_configuration_missing` when no receipt exists and the
  destination configuration is absent or the attempt reports it was not found.
  Add a `repair_destination_configuration` action.
- Use `delivery_failed` for a failed delivery with no receipt when destination
  configuration exists and no more specific diagnosis applies.
- Use `insufficient_evidence` when the available evidence cannot establish one
  of the preceding diagnoses, and identify the uncertainty.

Do not state that a recipient failed to acknowledge a report when a recipient
receipt exists.

Evidence citations must be complete, not merely sufficient. When a finding
compares sender status with recipient delivery, cite both the relevant delivery
attempt and recipient receipt. When stating that sender and recipient evidence
agree, cite the decisive record from each side.
""".strip()
