"""Refuse orphan cleanup without a verified journal/worker identity contract.

A numeric PID (present, missing, reused or from a different process namespace)
is not an ownership proof. The available code has no verified schema/version,
process-start identity or coordination protocol with writers. Guessing any of
these would risk closing a valid step or overwriting its original evidence.

Preserve the callable entry point, but reject before connecting to SQLite,
probing /proc, or creating a missing database. No cleanup, retry or override is
provided. A future implementation needs the authorized source contracts first.
"""
import sys

REFUSAL = (
    'OPRIT: închiderea pașilor este dezactivată fără schema verificată, '
    'identitatea procesului și protocolul de concurență al cozii. '
    'Jurnalul și dovezile originale nu au fost modificate.'
)


def inchide(cale, acum=None):
    """Never mutate a journal whose recovery preconditions are unverified."""
    raise RuntimeError(REFUSAL)


def main():
    print(REFUSAL, file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
