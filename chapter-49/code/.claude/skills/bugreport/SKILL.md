---
name: bugreport
description: Build a redacted evidence pack for a bug from a log file.
argument-hint: <log file path> <one-line symptom>
disable-model-invocation: true
---
Arguments: $ARGUMENTS

1. Run `python -m tools.triage --log <log file> --symptom "<symptom>" --expected "<ask me if you do not know>"
   --repro "<steps; separated; by semicolons>" --out docs/debug/<short-id>.md`.
2. Open the report and CHECK that no secret, token, email or customer data remains. Redaction is a safety net,
   not a guarantee. Tell me about anything suspicious. Do not fix anything yet.
3. Show me the report and tell me which of the five parts is weakest (symptom, expected, steps, environment, evidence).
