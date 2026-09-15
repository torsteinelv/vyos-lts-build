# vyos-lts-build

> **Unofficial, independent project.** Not affiliated with, endorsed by,
> or supported by VyOS Networks or the VyOS project. This repo does not
> provide official VyOS LTS or support of any kind - see LICENSE and
> SECURITY.md.

Build VyOS from a pinned public source commit, qualify it through an
automated test gate, and publish it as a traceable, versioned release -
without relying on VyOS's paid pre-built LTS images or an unpinned
rolling release.

**What this is, precisely:** given a pinned public VyOS source revision,
produce a traceable VyOS image and prove, at a general VyOS level, that
it installs, boots, and accepts a representative configuration cleanly.
Whether a given image fits any particular deployment is a separate
concern - see "Scope" below.

## Scope

This is a pure VyOS build/test pipeline. It isn't wired to any real
router and isn't a general-purpose config management tool. It builds an
ISO, tests it, and (if the tests pass) publishes it as a versioned
release - nothing else.

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

**This is not bit-for-bit reproducible.** VyOS's build fetches pre-built
`.deb` packages from `packages.vyos.net` at build time - pinning the
source commit and the build container digest fixes the *build recipe*,
not necessarily every byte of every dependency, since that package
repository can change contents independently of the VyOS source commit.
The accurate claim is "pinned and qualified," not "reproducible." Each
release includes the SBOMs VyOS's own build already generates
(CycloneDX + SPDX, listing every package actually installed) so you can
at least see exactly what went into a given release after the fact.

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
3. **`candidate-config-test`** - loads `config/qualification.txt` (a
   representative, non-topology-specific set of VyOS `set` commands -
   see that file) into a live boot of the built ISO via a
   `pexpect`-driven script (`scripts/test-candidate-config.py`), commits
   it, and fails loudly if VyOS printed any error text at any point (not
   just on a hang or an explicit "Commit failed" - a rejected command
   that still returns to a normal prompt is caught too), **and** verifies
   every applied command is actually present in the post-commit
   `show configuration commands` output - "commit succeeded" alone isn't
   proof the config ended up as intended. This is a **production gate**:
   the `release` job requires it to pass.
4. **`release`** - only runs if `build`, `smoketest`, and
   `candidate-config-test` all succeed. Computes a SHA256 checksum
   (correctly, matching the asset's actual uploaded filename - not
   prefixed with the local `iso/` download path), writes a
   `manifest.json` recording the exact source commit, build image
   digest, and CI run ID, picks up the SBOM files (CycloneDX + SPDX)
   VyOS's own build already generates, and publishes a GitHub Release
   with the ISO + checksum + manifest + SBOMs attached, plus a signed
   [artifact attestation](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds)
   binding the ISO's digest to this exact repo/workflow/commit
   (verifiable with `gh attestation verify`). This is the durable
   artifact - don't rely on the 14-day workflow artifact for anything
   you actually plan to use.

To verify a release before using it:

```bash
sha256sum -c SHA256SUMS
gh attestation verify vyos-<release>-generic-amd64.iso -R torsteinelv/vyos-lts-build
```

## Repository security posture

This is a public repo, which means most of GitHub's supply-chain
security tooling (normally an Advanced Security / Enterprise feature on
private repos) is free here. In use:

- **Actions are pinned to full commit SHAs**, not mutable version tags -
  [`.github/dependabot.yml`](.github/dependabot.yml) keeps them current
  via automated PRs.
- **Least-privilege workflow permissions** - `contents: read` by
  default, each job declares only the extra scopes it actually needs
  (the `release` job's `contents: write` / `id-token: write` /
  `attestations: write` / `artifact-metadata: write`).
- **Dependency Review** ([`dependency-review.yml`](.github/workflows/dependency-review.yml))
  scans every PR's changed Actions dependencies for known
  vulnerabilities - required to pass before merge.
- **OpenSSF Scorecard** ([`scorecard.yml`](.github/workflows/scorecard.yml))
  runs GitHub's own recommended supply-chain check (SHA-pinning, token
  scopes, risky workflow patterns) on every push to `main` and weekly,
  reporting into the repo's code scanning tab.
- **Secret scanning + push protection** and **CodeQL** - enabled at the
  repo level (Settings -> Code security), not tracked as files here.
- **Build provenance + SBOM attestations** on every release ISO
  (Sigstore-backed, see the `release` job) - `gh attestation verify`.
- **`release` environment** - the `release` job runs through a named
  GitHub Environment, infrastructure for adding required reviewers later
  (a second maintainer approving before an ISO is actually published)
  without changing the pipeline itself. No protection rules configured
  yet - solo maintainer today, so a required-approval rule would add
  friction without a real security benefit. Revisit if that changes.
- **Branch/tag rulesets on `main` and release tags** - PR required to
  merge to `main` (0 required approvals for the same solo-maintainer
  reason above; revisit alongside the environment rule), force-push and
  deletion blocked on both `main` and release tags, so a published
  release's tag can't move or disappear after the fact.

## What's deliberately not here (yet)

- **Broader qualification coverage** - `config/qualification.txt`
  currently proves a minimal, representative slice (interfaces + a
  firewall rule) parses and commits. Expanding it to cover more general
  VyOS feature areas (VLAN, NAT, WireGuard, VRRP, BGP, ...) as a broader
  but still non-topology-specific smoke set is reasonable future work -
  each addition needs its syntax verified against a real boot first, the
  same way the current lines were (see the git history for this file for
  what that process looks like in practice).
- **GitHub Immutable Releases** - a real GitHub feature (locks a
  release's tag and assets after publishing) that would strengthen the
  "durable artifact" claim further. Not yet researched carefully enough
  to implement correctly - noted here rather than guessed at.

## Requirements to build/test

- A CI runner with KVM available (`smoketest`, `candidate-config-test`).
- Nothing else - no VyOS subscription, no external credentials for the
  `build` job.

