#!/usr/bin/env python3
"""
Boot a VyOS ISO live in QEMU, load a candidate configuration, commit it,
and print the resulting `show configuration commands` output.

FIRST DRAFT - not yet exercised against a real boot. The prompt regexes
below are my best understanding of VyOS's actual CLI prompts, not
confirmed against a live run. Expect to iterate against real CI logs the
same way you'd debug any expect-style script - if it hangs or fails at a
specific expect(), that tells you which prompt string needs adjusting.

Boots the ISO live (no install step) - enough to test whether the
candidate config is syntactically valid and commits cleanly. VyOS's own
official scripts/check-qemu-install (used in the smoketest job) is what
validates the actual installed system.
"""
import argparse
import sys

import pexpect

LOGIN_PROMPT = "vyos login:"
PASSWORD_PROMPT = "Password:"
OPERATIONAL_PROMPT = r"vyos@vyos:~\$"
CONFIG_PROMPT = r"vyos@vyos#"


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

    with open(args.candidate_config) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            child.sendline(line)
            child.expect(CONFIG_PROMPT)

    child.sendline("commit")
    outcome = child.expect(["commit succeeded", "Commit failed", CONFIG_PROMPT], timeout=60)
    if outcome == 1:
        print("CANDIDATE CONFIG: commit failed", file=sys.stderr)
        sys.exit(1)

    child.sendline("show configuration commands")
    child.expect(CONFIG_PROMPT)
    print(child.before)

    child.sendline("exit")
    child.close(force=True)
    print("CANDIDATE CONFIG: committed successfully")


if __name__ == "__main__":
    main()
