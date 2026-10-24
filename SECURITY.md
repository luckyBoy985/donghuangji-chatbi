# Security policy

## Reporting a vulnerability

Please use GitHub private vulnerability reporting or a private security
advisory. Do not include API keys, session cookies, private documents, or
customer data in a public issue.

Include the affected endpoint or file, reproduction steps, impact, and a
minimal proof of concept. We will acknowledge actionable reports and coordinate
disclosure after a fix is available.

## Deployment expectations

- The default Compose stack is intended for a trusted local network.
- Public deployment requires TLS, secure cookies, network restrictions, backup
  and restore drills, monitoring, and secret rotation.
- Never commit `.env`, model credentials, harvested private documents, or
  production database backups.
- Rotate any API key that has appeared in logs, screenshots, or chat tools.

## Supported version

Security fixes are applied to the latest commit on the default branch.
