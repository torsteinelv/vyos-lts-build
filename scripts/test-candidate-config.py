#!/usr/bin/env python3
"""
Boot a VyOS ISO live in QEMU, load a candidate configuration, commit it,
and print the resulting `show configuration commands` output.

This is a production gate (the release job requires it to pass), not an
advisory check - a `set` command that VyOS silently rejects but doesn't
hang on (e.g. "Invalid command", printed then the prompt returns
normally) must fail this script, not just be waited past. Every prompt
match is followed by an explicit scan of the output for known VyOS error
strings.

Boots the ISO live (no install step) - enough to test whether the
candidate config is syntactically valid and commits cleanly. VyOS's own
official scripts/check-qemu-install (used in the smoketest job) is what
validates the actual installed system.
"""
import argparse
import re
import sys
import time

import pexpect

LOGIN_PROMPT = "vyos login:"
PASSWORD_PROMPT = "Password:"
OPERATIONAL_PROMPT = r"vyos@vyos:~\$"
CONFIG_PROMPT = r"vyos@vyos#"

# VyOS prints these inline and then returns to a normal prompt - a naive
# expect(CONFIG_PROMPT) alone would treat that as success.
ERROR_PATTERNS = [
    "Invalid command",
    "Configuration path",
    "is not valid",
    "Error:",
    "%%",
]


def check_no_errors(output, context):
    for pattern in ERROR_PATTERNS:
        if pattern in output:
            print(f"CANDIDATE CONFIG: error detected after {context} (matched {pattern!r})", file=sys.stderr)
            print(output, file=sys.stderr)
            sys.exit(1)


def verify_eth0_runtime_address(child, attempts=6, delay=5):
    # "commit succeeded" and the line appearing in "show configuration
    # commands" only prove the config tree accepted it - not that the
    # interface actually came up with a working address at runtime.
    # QEMU's usermode networking (-netdev user) has a built-in DHCP
    # server, so a genuinely working DHCP client should show a real
    # leased IPv4 address here - retried a few times since DHCP
    # negotiation timing can vary and a single immediate check could
    # flake on a system that's actually fine, just not done negotiating
    # yet.
    for attempt in range(1, attempts + 1):
        child.sendline("run show interfaces ethernet eth0 | no-more")
        child.expect(CONFIG_PROMPT, timeout=30)
        output = child.before
        check_no_errors(output, "show interfaces ethernet eth0")
        if re.search(r"inet \d+\.\d+\.\d+\.\d+/\d+", output):
            return
        print(f"CANDIDATE CONFIG: no IPv4 address on eth0 yet (attempt {attempt}/{attempts}), retrying...")
        time.sleep(delay)

    print("CANDIDATE CONFIG: eth0 never got an IPv4 address in its runtime state - "
          "the config was accepted, but DHCP apparently never actually "
          "completed (config-tree acceptance alone doesn't prove this)",
          file=sys.stderr)
    print(output, file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso")
    parser.add_argument("candidate_config")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    qemu_cmd = (
        "qemu-system-x86_64 -M q35 -m 2048 -enable-kvm "
        f"-cdrom {args.iso} -boot d -nographic -serial mon:stdio "
        "-netdev user,id=net0 -device virtio-net-pci,netdev=net0"
    )

    child = pexpect.spawn(qemu_cmd, timeout=args.timeout, encoding="utf-8")
    child.logfile = sys.stdout  # echo everything - this IS the CI log

    child.expect(LOGIN_PROMPT)
    child.sendline("vyos")
    child.expect(PASSWORD_PROMPT)
    child.sendline("vyos")
    child.expect(OPERATIONAL_PROMPT)

    child.sendline("configure")
    child.expect(CONFIG_PROMPT)
    check_no_errors(child.before, "entering configure mode")

    applied_commands = []
    with open(args.candidate_config) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            applied_commands.append(line)
            child.sendline(line)
            child.expect(CONFIG_PROMPT)
            check_no_errors(child.before, f"command {line!r}")

    child.sendline("commit")
    outcome = child.expect(["commit succeeded", "Commit failed", CONFIG_PROMPT], timeout=60)
    if outcome == 1:
        print("CANDIDATE CONFIG: commit failed", file=sys.stderr)
        print(child.before, file=sys.stderr)
        sys.exit(1)
    check_no_errors(child.before, "commit")

    # Still in configure mode here - "show configuration commands" without
    # "run" is parsed as a candidate-config path lookup (there's no top
    # -level node called "configuration"), not the operational show
    # command, and fails with "Configuration path: [configuration] is not
    # valid" - confirmed via a real CI failure. "run" dispatches it as an
    # operational-mode command from within configure mode instead.
    # "| no-more" disables the pager - without it, output long enough to
    # fill the terminal leaves the session stuck at a "---More---"-style
    # ":" prompt instead of returning to CONFIG_PROMPT, which pexpect then
    # times out waiting for - confirmed via a real CI timeout.
    child.sendline("run show configuration commands | no-more")
    child.expect(CONFIG_PROMPT)
    committed = child.before
    check_no_errors(committed, "show configuration commands")
    print(committed)

    # "commit succeeded" only means VyOS accepted the syntax and applied
    # SOMETHING - it doesn't prove each line ended up in the committed
    # config exactly as intended (VyOS could in principle normalize,
    # dedupe, or silently drop a line under some edge case). Assert every
    # applied command is actually present in the post-commit config, not
    # just that commit didn't error.
    missing = [cmd for cmd in applied_commands if cmd not in committed]
    if missing:
        print("CANDIDATE CONFIG: commit succeeded but expected line(s) missing from "
              "'show configuration commands':", file=sys.stderr)
        for cmd in missing:
            print(f"  MISSING: {cmd}", file=sys.stderr)
        sys.exit(1)

    # Runtime verification (#18) - proves eth0 actually came up with a
    # real address, not just that its config was accepted into the tree.
    verify_eth0_runtime_address(child)
    print("CANDIDATE CONFIG: eth0 runtime state verified (real IPv4 address present)")

    child.sendline("exit")
    child.close(force=True)
    print(f"CANDIDATE CONFIG: committed successfully, all {len(applied_commands)} "
          f"command(s) verified present, no errors detected")


if __name__ == "__main__":
    main()
