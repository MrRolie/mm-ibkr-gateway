# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

**DO NOT** open public issues for security vulnerabilities.

Please report security vulnerabilities via:
- GitHub Security Advisories: https://github.com/MrRolie/mm-ibkr-gateway/security/advisories/new

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Initial response**: Within 48 hours
- **Status update**: Within 7 days
- **Fix timeline**: Depends on severity (critical: <7 days, high: <30 days)

### Disclosure Policy

We follow coordinated disclosure:
1. You report the issue privately
2. We confirm and develop a fix
3. We release the fix
4. Public disclosure (credited to reporter if desired)

## Security Best Practices for Users

1. **Never commit credentials** to version control
2. **Use paper trading mode** unless absolutely necessary
3. **Set strict order limits** in configuration
4. **Monitor IBKR account** when system is running
5. **Review all code** before enabling live trading
6. **Keep dependencies updated** (run `poetry update` regularly)

## Known Security Considerations

- This system can place REAL trades with REAL money when configured for live trading
- API key authentication is basic (suitable for local/internal use only)
- No built-in rate limiting (relies on IBKR's limits)
- Order registry is in-memory (lost on restart)

For production deployment, consider:
- Running behind a reverse proxy with authentication
- Using environment-specific secrets management
- Implementing additional rate limiting
- Adding audit logging to persistent storage

## Safety Features

This system is designed with multiple layers of protection:

- **Paper mode default**: `trading_mode=paper` in `control.json` is the default setting
- **Orders disabled by default**: `orders_enabled=false` in `control.json` prevents accidental order placement
- **Dual-toggle protection**: Live trading requires `trading_mode=live`, `orders_enabled=true`, and an override file
- **Override file requirement**: Live trading with orders enabled requires a confirmation file
- **SIMULATED status**: When orders are disabled, the system returns `SIMULATED` status instead of placing real orders

For detailed safety information, see:
- [README Safety Section](README.md#️-safety-first-️)
- [Safety Checklist](.context/SAFETY_CHECKLIST.md)
