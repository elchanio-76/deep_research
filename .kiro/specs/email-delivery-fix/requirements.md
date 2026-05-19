# Requirements Document

## Introduction

The email delivery pipeline in the deep-research application currently runs unconditionally: the `send_email()` step always invokes the SES-backed email agent, and a hardcoded `print("Email sent")` fires regardless of whether the SES call actually succeeded. This feature introduces an explicit opt-in gate (`EMAIL_ENABLED`), short-circuits the email step when the feature is disabled or credentials are missing, and surfaces real delivery outcomes into the SSE stream instead of printing blindly.

The scope is narrow: one new constant in `settings.py`, one updated method in `ResearchManager`, and one updated call-site in `ResearchManager.run()`. No new classes, no new dependencies, no schema changes.

## Glossary

- **ResearchManager**: The core orchestration class in `src/core/research_manager.py` that drives the research pipeline and owns the `send_email()` method.
- **Settings**: The configuration module at `src/config/settings.py` that exposes module-level constants loaded from environment variables.
- **EMAIL_ENABLED**: A boolean constant in Settings that gates the email delivery step. Defaults to `False`.
- **SENDER**: The SES-verified sender email address, read from the `EMAIL_SENDER` environment variable.
- **RECIPIENT**: The delivery email address, read from the `EMAIL_RECIPIENT` environment variable.
- **Email_Agent**: The OpenAI Agents SDK agent defined in `src/agents/email_agent.py` that converts a markdown report to HTML and calls the SES `send_email` function tool.
- **SSE_Stream**: The server-sent events async generator produced by `ResearchManager.run()` that yields status strings to the API layer.
- **FinalReportData**: The Pydantic domain model representing the completed research report passed to `send_email()`.

## Requirements

### Requirement 1: Email Feature Flag Configuration

**User Story:** As a system operator, I want to control whether email delivery is attempted at all, so that I can deploy the application without SES credentials and avoid unintended outbound email.

#### Acceptance Criteria

1. THE Settings module SHALL expose a constant `EMAIL_ENABLED` of type `bool`.
2. WHEN the `EMAIL_ENABLED` environment variable is absent or set to any value other than `"true"` (case-insensitive), THE Settings module SHALL set `EMAIL_ENABLED` to `False`.
3. WHEN the `EMAIL_ENABLED` environment variable is set to `"true"` (case-insensitive), THE Settings module SHALL set `EMAIL_ENABLED` to `True`.
4. THE Settings module SHALL continue to expose `SENDER` read from the `EMAIL_SENDER` environment variable, defaulting to `""`.
5. THE Settings module SHALL continue to expose `RECIPIENT` read from the `EMAIL_RECIPIENT` environment variable, defaulting to `""`.

---

### Requirement 2: Email Step Opt-In Gate

**User Story:** As a system operator, I want the email step to be skipped entirely when `EMAIL_ENABLED` is `False`, so that no SES calls are made and no credentials are required in the default configuration.

#### Acceptance Criteria

1. WHEN `EMAIL_ENABLED` is `False`, THE ResearchManager SHALL return from `send_email()` without invoking the Email_Agent.
2. WHEN `EMAIL_ENABLED` is `False`, THE ResearchManager `send_email()` method SHALL return a non-empty string indicating the email step was skipped.
3. WHEN `EMAIL_ENABLED` is `False`, THE ResearchManager `send_email()` method SHALL NOT make any outbound network calls related to email delivery.

---

### Requirement 3: Missing Credentials Guard

**User Story:** As a system operator, I want the email step to be skipped when `SENDER` or `RECIPIENT` is not configured, so that a misconfigured deployment does not attempt SES calls that will fail.

#### Acceptance Criteria

1. WHEN `EMAIL_ENABLED` is `True` and `SENDER` is an empty string, THE ResearchManager SHALL return from `send_email()` without invoking the Email_Agent.
2. WHEN `EMAIL_ENABLED` is `True` and `RECIPIENT` is an empty string, THE ResearchManager SHALL return from `send_email()` without invoking the Email_Agent.
3. IF `SENDER` or `RECIPIENT` is empty, THEN THE ResearchManager `send_email()` method SHALL return a non-empty string indicating the email step was skipped due to missing credentials.
4. IF `SENDER` or `RECIPIENT` is empty, THEN THE ResearchManager `send_email()` method SHALL NOT make any outbound network calls related to email delivery.

---

### Requirement 4: Delivery Outcome Surfacing

**User Story:** As a system operator, I want the actual result of the SES call to be reflected in the SSE stream, so that I can distinguish a successful delivery from a silent failure.

#### Acceptance Criteria

1. WHEN `EMAIL_ENABLED` is `True` and both `SENDER` and `RECIPIENT` are non-empty and the Email_Agent returns output that does not contain `"error"` (case-insensitive), THE ResearchManager `send_email()` method SHALL return the string `"Email sent.\n"`.
2. WHEN `EMAIL_ENABLED` is `True` and both `SENDER` and `RECIPIENT` are non-empty and the Email_Agent returns output that contains `"error"` (case-insensitive), THE ResearchManager `send_email()` method SHALL return a string containing `"Warning"` that describes the delivery failure.
3. THE ResearchManager `send_email()` method SHALL always return a value of type `str` regardless of the execution path taken.

---

### Requirement 5: SSE Stream Integration

**User Story:** As a developer consuming the SSE stream, I want the email delivery status to appear as a yielded event in the stream, so that clients receive accurate progress information.

#### Acceptance Criteria

1. WHEN `ResearchManager.run()` reaches the email step, THE SSE_Stream SHALL yield the string `"Sending email...\n"` before invoking `send_email()`.
2. WHEN `ResearchManager.run()` receives the return value of `send_email()`, THE SSE_Stream SHALL yield that return value as the next event.
3. THE SSE_Stream SHALL NOT yield a hardcoded `"Email sent"` string that is independent of the actual delivery outcome.

---

### Requirement 6: No Regression on Existing Behaviour

**User Story:** As a developer, I want the rest of the research pipeline to be unaffected by this change, so that existing functionality continues to work correctly.

#### Acceptance Criteria

1. THE ResearchManager SHALL continue to invoke the Email_Agent with the `markdown_report` field of `FinalReportData` when `EMAIL_ENABLED` is `True` and credentials are present.
2. THE ResearchManager SHALL continue to call `update_usage_stats("email_agent", ...)` after a successful agent invocation.
3. THE Settings module SHALL NOT remove or rename the `SENDER`, `RECIPIENT`, or `DEFAULT_AWS_REGION` constants.
4. THE Email_Agent module (`src/agents/email_agent.py`) SHALL remain unchanged by this fix.
