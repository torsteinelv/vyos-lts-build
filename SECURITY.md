# Security Policy

This repository's output (a VyOS ISO) is an operating system people may run
as a firewall/router. Security issues here matter more than in a typical
CI script.

## Scope

This policy covers this repository's own build/test automation (the
workflow, scripts, and how they're pinned/configured). It does **not**
cover VyOS itself - if you find a vulnerability in VyOS, FRR, or another
component this pipeline builds, report it to
[VyOS directly](https://vyos.dev) or the relevant upstream project, not
here.

Things in scope here:
- The pinned `VYOS_SOURCE_SHA` or `VYOS_BUILD_IMAGE` referencing a known-bad
  or compromised commit/image.
- A gap in the qualification gate that would let a broken/insecure image
  reach a release.
- Workflow/supply-chain issues (unpinned dependencies, missing provenance,
  a step that could be used to inject something into a release artifact).

## Reporting

Open a GitHub issue, or if it's sensitive, use GitHub's private vulnerability
reporting (Security tab -> "Report a vulnerability") on this repository.

## Disclaimer

This is an independent, unofficial project. It is not affiliated with,
endorsed by, or supported by VyOS Networks or the VyOS project. Releases
from this repository come with no warranty and no support guarantee - see
LICENSE.
