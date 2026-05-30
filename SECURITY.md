# Security Policy

## Supported versions

This library is in alpha and the public API may change at any time.
Security fixes will land on the `main` branch and the most recent
released version. Older versions are not supported.

## Threat model

The NEEO Brain has **no authentication layer** on the local network -
that's how the firmware ships and there is no way to change it. This
library is designed for use behind a router on a trusted LAN; do not
expose a Brain (or this library) to the open internet.

The two surfaces worth thinking about:

- **The Brain itself.** Anyone on the LAN can read and trigger
  recipes. Treat it like any other unauthenticated IoT device.
- **The forward-actions listener.** It accepts POSTs from the Brain
  and dispatches them as events. The default path is open to
  anything on the LAN that finds it. If your HA instance forwards
  this through HA's own HTTP server, HA's auth layer covers it; if
  you run the standalone `ForwardActionsListener` directly, scope
  its `host=` to the right interface and don't bind to `0.0.0.0`
  outside your LAN.

## Reporting a vulnerability

If you think you've found a security issue in `pyneeo`,
**please do not open a public GitHub issue**. Report it privately via
either:

- GitHub's [private security advisory mechanism](https://github.com/magictom74/homeassistant-neeo/security/advisories/new) (preferred)
- Email the maintainer (the email address in `pyproject.toml`)

You can expect:

1. An acknowledgement within ~7 days.
2. A short triage assessment with a severity estimate.
3. A fix on a private branch and a coordinated disclosure timeline.

## What counts as a security issue

Examples of things we'd want to know about privately first:

- A way for an off-LAN attacker to trigger arbitrary recipes or
  macros through a misconfigured listener.
- An input handling bug in the listener that lets a Brain payload
  escape the event dispatch (path traversal, header injection, ...).
- A way to bypass the forward-chain's per-target isolation so that
  a failing chain target affects the others or the local handlers.

Things that are **not** security issues (please open a normal issue):

- The Brain itself rejecting a request - that's a protocol bug.
- Crash / DoS bugs that only affect the caller's own process.
- The Brain having no auth layer - that's a firmware property of an
  end-of-life device. We document it; we can't change it.
