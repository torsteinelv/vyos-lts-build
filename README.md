# vyos-lts-build

Build VyOS from source, pin it to a specific commit so nothing changes
without a deliberate decision, and verify it in CI before you'd ever
consider deploying it.

## Scope

This is a pure VyOS build/test pipeline. It does **not** produce
Proxmox-specific artifacts (no QCOW2 conversion), isn't wired to any real
router, and isn't a general-purpose config management tool. It builds an
ISO, tests it, and (if the tests pass) publishes it as a versioned
release.

## Versioning strategy: pinned rolling, not frozen LTS

The first version of this pipeline tried to build VyOS's `sagitta`
(1.4 LTS) branch. That didn't work, for a real reason confirmed in CI, not
a guess: VyOS renamed the branch to `sagitta-public-unmaintained`, and its
package repository (`dev.packages.vyos.net/repositories/sagitta`) doesn't
resolve at all -

```
Could not resolve 'dev.packages.vyos.net'
```

The `-public-unmaintained` suffix isn't cosmetic - VyOS is no longer
backporting fixes to the free/public LTS branches, and the package
infrastructure that branch depends on to even build is gone. Rebuilding
`sagitta-public-unmaintained` wouldn't give you a maintained LTS, just a
frozen source snapshot that can't fetch its own dependencies.

So instead of imitating an official LTS channel that VyOS itself isn't
maintaining for free users, this repo:

1. Builds `rolling` (VyOS's actively-developed branch, live package
   mirrors, gets real security fixes) pinned to a **specific commit SHA**
   - not the branch head, which moves constantly.
2. Runs it through the full test gate below.
3. If everything passes, publishes it as a dated release - this repo's
   own "qualified stable" channel, distinct from and independent of
   VyOS's own LTS/rolling distinction.

```
vyos rolling (upstream, moves constantly)
        │
        │  pick a specific commit
        ▼
   build + test (this repo)
        │
        │  all gates pass
        ▼
  a dated release in THIS repo
  (only this gets deployed anywhere)
```

Nothing gets rebuilt or re-tagged automatically. Moving `VYOS_SOURCE_SHA`
forward in `.github/workflows/build-and-test.yml` is a deliberate,
reviewed decision every time - typically prompted by a VyOS/FRR/Debian
security advisory, not a schedule.

## Pinning

- `VYOS_SOURCE_SHA` - exact commit from `vyos/vyos-build`'s `rolling`
  branch. This is what actually gets built; update it on purpose.
- `VYOS_BUILD_IMAGE` - the build container, pinned by **digest**, not a
  mutable tag (`vyos/vyos-build:rolling` gets overwritten regularly on
  Docker Hub - the digest doesn't).

Both live in `.github/workflows/build-and-test.yml`'s `env:` block.

## Pipeline

1. **`build`** - checks out `vyos/vyos-build` at the pinned commit
   (`git fetch --depth=1 origin $SHA && git checkout --detach $SHA`, not
   a branch clone), builds the ISO, uploads it as a workflow artifact.
2. **`smoketest`** - downloads the ISO, runs VyOS's own official
   `scripts/check-qemu-install` against it (installs into a QEMU disk
   image, boots, logs in, runs VyOS's built-in smoketest/config-test
   suites) at the *same pinned commit*. Needs KVM (`/dev/kvm`) - present
   by default on GitHub-hosted `ubuntu-latest` runners.
3. **`candidate-config-test`** - loads `config/candidate.txt` (a
   placeholder set of VyOS `set` commands - see that file) into a live
   boot of the built ISO via a `pexpect`-driven script
   (`scripts/test-candidate-config.py`), commits it, and fails loudly if
   VyOS printed any error text at any point (not just on a hang or an
   explicit "Commit failed" - a rejected command that still returns to a
   normal prompt is caught too). This is a **production gate**: the
   `release` job requires it to pass.
4. **`release`** - only runs if `build`, `smoketest`, and
   `candidate-config-test` all succeed. Computes a SHA256 checksum,
   writes a `manifest.json` recording the exact source commit, build
   image digest, and CI run ID, and publishes a GitHub Release with the
   ISO + checksum + manifest attached. This is the durable artifact -
   don't rely on the 14-day workflow artifact for anything you actually
   plan to use.

## What's deliberately not here (yet)

- **Proxmox/QCOW2 conversion** - out of scope for this repo by design
  (see "Scope" above). If/when needed, that belongs in a separate,
  infrastructure-specific pipeline that consumes this repo's releases.
- **Integration testing** (BGP peering, WireGuard tunnels, VRRP
  failover, conntrack survival across a simulated failure) - this repo
  tests that a single built image installs, boots, and accepts a
  candidate config cleanly. It does not stand up a multi-router lab.
  That's real, valuable next work, but it's a different kind of project
  (needs actual multi-VM infrastructure, not just CI) and shouldn't be
  bolted onto a "pure VyOS build" repo.
- **SBOM / artifact attestation** - `manifest.json` currently records
  provenance manually (source SHA, image digest, run ID). Signing
  releases with GitHub's Sigstore-backed attestations
  (`gh attestation verify`) so deployment tooling can cryptographically
  verify an artifact came from this exact repo/workflow/commit is a
  reasonable next step, not implemented yet.

## Requirements to build/test

- A CI runner with KVM available (`smoketest`, `candidate-config-test`).
- Nothing else - no VyOS subscription, no external credentials for the
  `build` job.
