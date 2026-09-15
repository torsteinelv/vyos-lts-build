# vyos-lts-build

Build a free VyOS LTS ISO from source, pin the version in Git, and verify it
in CI before you'd ever consider deploying it — instead of relying on VyOS's
paid pre-built LTS images or the unpinned rolling release.

## Why this exists

VyOS's source is fully open (GPL) and its official build tooling
([`vyos/vyos-build`](https://github.com/vyos/vyos-build)) is free to use, but
pre-built LTS ISOs require a paid subscription. Building the LTS branch
yourself from source is a well-established community workaround (see e.g.
[`onedr0p/unofficial-builds-for-vyos`](https://github.com/onedr0p/unofficial-builds-for-vyos)),
not something exotic. This repo automates that build, pins it to a specific
version so nothing changes without a deliberate commit, and runs the
resulting ISO through VyOS's own official install/smoketest tooling in CI
before anything is considered a candidate for real use.

## Status: build + smoketest pipeline only, not a deployment tool

This repo builds and tests an ISO. It does **not** deploy configuration to
any real router, and isn't wired to any specific firewall setup. Pick up the
built artifact and use it however you like.

## Pinned version

- Branch: `sagitta` (VyOS 1.4 LTS)
- Docker build image: `vyos/vyos-build:sagitta` (official, published by
  VyOS, updated periodically — see [Docker Hub tags](https://hub.docker.com/r/vyos/vyos-build/tags))

To move to a newer LTS (e.g. 1.5 `circinus` once released), update
`VYOS_BRANCH` in `.github/workflows/build-and-test.yml` deliberately — this
is a manual decision, not something that happens on its own.

## Pipeline

1. **`build`** — clones `vyos/vyos-build` at the pinned branch, runs the
   official `build-vyos-image iso` command inside the official
   `vyos/vyos-build:sagitta` container, uploads the resulting ISO as a
   workflow artifact.
2. **`smoketest`** — downloads the built ISO and runs VyOS's own official
   `scripts/check-qemu-install` against it (installs the ISO into a QEMU
   disk image, boots it, logs in, runs VyOS's built-in smoketest/config-test
   suites). This step needs KVM (`/dev/kvm`) on the runner — GitHub-hosted
   `ubuntu-latest` runners have this by default; if you move this to a
   self-hosted runner, verify with `ls /dev/kvm` first, or it'll silently
   fall back to (much slower) software emulation.
3. **`candidate-config-test`** — **experimental, first draft.** VyOS's own
   `check-qemu-install` validates the *build itself* (does it boot, do
   VyOS's own smoketests pass) but does not load an arbitrary candidate
   configuration you supply. This job is a custom `pexpect`-driven script
   (`scripts/test-candidate-config.py`) that boots the installed image,
   logs in over the QEMU serial console, loads `config/candidate.txt` (a
   plain set of VyOS `set` commands — see that file for the current
   placeholder example), commits it, and checks the output. This part
   hasn't been exercised against a real boot yet — expect to need a few
   iterations against actual CI runs to get the serial-console interaction
   right, the same way you'd debug any expect-style script.

## Requirements to actually build/test

- A CI runner with KVM available for the `smoketest` and
  `candidate-config-test` jobs (see above).
- Nothing else — no VyOS subscription, no external credentials. The `build`
  job needs no secrets.

## Non-goals (for now)

- Not wired to any real router or firewall config.
- Not a general-purpose config management tool — it validates one candidate
  config file at a time, it doesn't diff/track state the way Terraform does.
- No commercial LTS subscription used or required anywhere in this pipeline.
