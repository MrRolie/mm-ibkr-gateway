# IBKR 2FA Integration Plan

## Goal
Make IBKR Gateway login resilient with 2FA while keeping watchdogs and the API stable.

## Options Overview
- IBAutomater (current Windows UI automation path)
- IBController (headless controller alternative)

### IBAutomater (Windows UI automation)
Pros
- Already integrated via `deploy/windows/start-gateway.ps1` and `deploy/windows/ibautomater/IBAutomater.jar`.
- Minimal change surface for the current Windows execution node.
- Uses the existing Gateway UI flow.

Cons
- Requires a desktop session and UI stability.
- 2FA may still need manual approval depending on IBKR policy and account setup.
- UI changes can break automation.

### IBController (headless controller)
Pros
- Better suited for headless servers and deterministic login flows.
- Supports scripted 2FA handling when configured (see IBController docs).

Cons
- Additional install and configuration surface area.
- Separate config file and runtime to monitor and update.
- More moving parts for the watchdog to manage.

## Recommendation
- Windows execution node: keep IBAutomater and add explicit 2FA configuration + runbook.
- Headless or non-Windows nodes: evaluate IBController for stability.

## IBAutomater Integration Steps (Plan)
1. Keep `deploy/windows/ibautomater/IBAutomater.jar` and `deploy/windows/start-gateway.ps1`.
2. Add 2FA configuration inputs:
   - `IBKR_2FA_MODE=push|ibkey|totp` (new)
   - `IBKR_2FA_TIMEOUT_SEC=90` (new, optional)
   - `IBKR_2FA_DEVICE_ID=` (new, optional)
3. Update `start-gateway.ps1` to pass 2FA fields to the agent config file.
4. First-run validation:
   - Run `.\start-gateway.ps1 -ShowWindow -Force`.
   - Confirm auto-login works and the 2FA prompt is handled (or manual approval is required).
5. Health checks:
   - Extend `/health` to report `gateway_authenticated` and last successful login time.
6. Runbook:
   - If 2FA approval is missed, watchdog restarts the Gateway once.
   - If failures persist, stop retries and alert for manual intervention.

## IBController Integration Steps (Plan)
1. Add IBController under `deploy/windows/tools/ibcontroller/` (or a separate repo checkout).
2. Create an `ibcontroller.ini` with Gateway path, credentials, and 2FA options.
3. Update `start-gateway.ps1` to launch IBController instead of `ibgateway.exe`.
4. Update watchdog logic to detect login failures and restart IBController.

## Security and Secrets
- Keep credentials out of the repo (`secrets/ibkr_credentials.json`, Windows Credential Manager, or DPAPI).
- If TOTP is used, store the secret in OS-protected storage and never in `.env`.
- Restrict ACLs on `secrets/` and `C:\ProgramData\mm-ibkr-gateway`.

## Decision Checklist
- Need headless operation? Prefer IBController.
- Need minimal changes on Windows desktop? Keep IBAutomater.
- 2FA requires manual approval? Document approval steps and test watchdog behavior.
