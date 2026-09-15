#!/usr/bin/env python3
"""
SCRATCH/THROWAWAY: verify the exact 'install image' prompt sequence by
actually driving it, instead of trusting documentation or memory. Not
part of the real pipeline - used once to design build-vyos-template.py
in terraform-infra, then this file and its throwaway workflow get deleted.
"""
import argparse
import sys

import pexpect

LOGIN_PROMPT = "vyos login:"
PASSWORD_PROMPT = "Password:"
OPERATIONAL_PROMPT = r"vyos@vyos:~\$"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("iso")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    qemu_cmd = (
        "qemu-system-x86_64 -M q35 -m 2048 -enable-kvm "
        f"-cdrom {args.iso} -boot d -nographic -serial mon:stdio "
        "-netdev user,id=net0 -device virtio-net-pci,netdev=net0"
    )

    child = pexpect.spawn(qemu_cmd, timeout=args.timeout, encoding="utf-8")
    child.logfile = sys.stdout

    child.expect(LOGIN_PROMPT)
    child.sendline("vyos")
    child.expect(PASSWORD_PROMPT)
    child.sendline("vyos")
    child.expect(OPERATIONAL_PROMPT)

    child.sendline("install image")
    # Deliberately just print raw output for a long window instead of
    # matching specific prompts - this run is for OBSERVING the real
    # sequence, not yet automating it.
    for _ in range(40):
        try:
            child.expect(r"[\?:\]]\s*$", timeout=20)
        except pexpect.exceptions.TIMEOUT:
            print("--- TIMEOUT waiting for next prompt, dumping buffer ---")
            print(child.before)
            break
        except pexpect.exceptions.EOF:
            print("--- EOF, install process ended or crashed ---")
            break

    print("=== FINAL BUFFER ===")
    print(child.before)


if __name__ == "__main__":
    main()
