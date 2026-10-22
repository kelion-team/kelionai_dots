"""Refuse the legacy registry/prompt patch before reading or writing files.

The complete queue and its callers are not in this repository. Returning an
OPRESTE prompt does not programmatically stop a job, and raising inside the
snippet may be swallowed by an unknown enclosing handler. Neither is a verified
A12 fix. File/string matches cannot establish fulfillment of the requirements.

Keep this entry point explicitly disabled until those contracts and behavioral
regressions are available. Do not modify registry criteria, including A4, or
produce a candidate that an older installer could mistake for a verified repair.
"""
import sys

REFUSAL = (
    'OPRIT: reparația nu poate fi pregătită fără sursele complete ale cozii și '
    'contractul de oprire A12. Registrul și criteriile rămân neschimbate; '
    'nu s-a generat niciun candidat.'
)


def main():
    print(REFUSAL, file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
