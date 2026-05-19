# Implementation Plan: Email Delivery Fix

## Overview

Three targeted changes across two files: add `EMAIL_ENABLED` to `settings.py`, update `ResearchManager.send_email()` to guard and return a status string, and update the call-site in `ResearchManager.run()` to yield that string. No new classes or dependencies.

## Tasks

- [x] 1. Add `EMAIL_ENABLED` constant to `src/config/settings.py`
  - [x] 1.1 Add `EMAIL_ENABLED` below the existing `SENDER`/`RECIPIENT` lines
    - Insert `EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"` in the e-mail config block
    - Keep `SENDER`, `RECIPIENT`, and `DEFAULT_AWS_REGION` unchanged
    - _Requirements: 1.1, 1.2, 1.3, 6.3_

  - [x] 1.2 Write property test for `EMAIL_ENABLED` parsing
    - **Property 1: EMAIL_ENABLED is False for any non-"true" env var value**
    - Use `hypothesis` to generate arbitrary strings; assert `EMAIL_ENABLED` is `False` for all values except case-insensitive `"true"`
    - **Validates: Requirements 1.2**

- [x] 2. Update `ResearchManager.send_email()` in `src/core/research_manager.py`
  - [x] 2.1 Change return type from `None` to `str` and add the `EMAIL_ENABLED` guard
    - Import `EMAIL_ENABLED` alongside `RECIPIENT` and `SENDER` from `src.config.settings` at the top of the method (local import to match existing pattern)
    - Return `"Email skipped: EMAIL_ENABLED is not set.\n"` when `EMAIL_ENABLED` is `False`
    - Return `"Email skipped: SENDER or RECIPIENT not configured.\n"` when either credential is empty
    - Replace `print("Email sent")` with result-aware return: inspect `str(result.final_output)` for `"error"` (case-insensitive) and return `"Warning: email delivery failed — check SES configuration.\n"` or `"Email sent.\n"` accordingly
    - Keep `update_usage_stats` and `print(f"Total cost: ...")` calls in the success path
    - Update the method docstring to reflect the new return type and behaviour
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 6.1, 6.2_

  - [x] 2.2 Write property test: `send_email` always returns a non-empty `str`
    - **Property 2: send_email always returns a str**
    - Use `hypothesis` to vary `EMAIL_ENABLED`, `SENDER`, `RECIPIENT`, and agent output; assert return is `str` and non-empty in all cases
    - Mock `Runner.run` to avoid network calls
    - **Validates: Requirements 4.3**

  - [x] 2.3 Write property test: Email_Agent never called when `EMAIL_ENABLED` is `False`
    - **Property 3: Email_Agent is never called when EMAIL_ENABLED is False**
    - Use `hypothesis` to generate arbitrary `FinalReportData`-compatible inputs; assert `Runner.run` is never called when `EMAIL_ENABLED=False`
    - **Validates: Requirements 2.1, 2.3**

  - [x] 2.4 Write property test: Email_Agent never called when credentials are missing
    - **Property 4: Email_Agent is never called when credentials are missing**
    - Use `hypothesis` to vary `SENDER`/`RECIPIENT` as empty strings with `EMAIL_ENABLED=True`; assert `Runner.run` is never called
    - **Validates: Requirements 3.1, 3.2, 3.4**

  - [x] 2.5 Write property test: agent output containing "error" produces a warning
    - **Property 5: Agent output containing "error" produces a warning return value**
    - Use `hypothesis` to generate strings that contain `"error"` in any case; assert return value contains `"Warning"`
    - **Validates: Requirements 4.2**

  - [x] 2.6 Write property test: agent output without "error" produces success string
    - **Property 6: Agent output not containing "error" produces the success return value**
    - Use `hypothesis` to generate strings that do not contain `"error"`; assert return value is `"Email sent.\n"`
    - **Validates: Requirements 4.1**

- [x] 3. Update the call-site in `ResearchManager.run()`
  - [x] 3.1 Capture and yield the return value of `send_email()`
    - Change `await self.send_email(final_report)` to `status = await self.send_email(final_report)` followed by `yield status`
    - The preceding `yield "Sending email...\n"` line stays unchanged
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 3.2 Write unit tests for the updated `send_email()` method
    - `test_send_email_skipped_when_disabled`: patch `EMAIL_ENABLED=False`, assert return is the skip string and `Runner.run` is not called
    - `test_send_email_skipped_when_no_credentials`: patch `EMAIL_ENABLED=True`, `SENDER=""`, assert early return and no agent call
    - `test_send_email_success`: mock `Runner.run` returning output without `"error"`, assert `"Email sent.\n"`
    - `test_send_email_failure_surfaced`: mock `Runner.run` returning output with `"status": "error"`, assert return contains `"Warning"`
    - `test_run_yields_email_status`: assert the string returned by `send_email()` appears in the SSE stream produced by `run()`
    - _Requirements: 2.1, 2.2, 3.1, 3.3, 4.1, 4.2, 5.2_

- [x] 4. Checkpoint — Ensure all tests pass
  - Run `python -m pytest tests/` and confirm no regressions. Ask the user if any questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests use `hypothesis`; unit tests use `pytest` with `unittest.mock.patch`
- `src/agents/email_agent.py` is explicitly out of scope — do not modify it
- All imports must follow the `src.*` absolute path convention from `AGENTS.md`
- The local import of `EMAIL_ENABLED` inside `send_email()` matches the existing pattern for `SENDER`/`RECIPIENT` in `email_agent.py`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "3.1"] },
    { "id": 3, "tasks": ["3.2"] }
  ]
}
```
