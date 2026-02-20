# Security Policy

## Supported Versions

Only the latest release of TraceKit is supported with security updates.

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Instead, contact me directly:

- **Email:** ckdake@ckdake.com
- **GitHub:** [@ckdake](https://github.com/ckdake)

Include as much detail as possible:

- A description of the vulnerability and its potential impact
- Steps to reproduce or proof-of-concept
- Any suggested mitigations, if known

I will acknowledge receipt within a few days and work on a fix as quickly as possible. Once the issue is resolved, I'm happy to credit you in the release notes if you'd like.

## Scope

This project is a personal tool for syncing fitness activity data. It handles API credentials (Strava, Garmin, RideWithGPS) stored in local config files. Security concerns most relevant to this project include:

- Credential exposure or leakage
- Insecure handling of OAuth tokens
- Vulnerabilities in dependencies

Thank you for helping keep this project secure.
