# Registry repair is disabled pending source contracts

The three legacy entry points (`repara-registru.sh`,
`repara_registru_procedura.py`, `inchide_pasi_orfani.py`) now fail before any
server read, download, candidate generation, installation or journal connection.
There is no enable flag. This prevents unsafe mutations; it does not implement
queue recovery or certify R5/R17/R20/R32/R33/A12.

Offline review of revision `5e900371d3b4b3b3089112e59b0ddd2cecebbb4e`
(identical target files on initial base `b7a9c9c`) showed:

- The shell could print GATA and return zero after SQLite backup or cleanup
  failed, with code/registry already installed. The two-file copy/rollback
  sequence did not coordinate with queue writers or the journal transaction.
- Cleanup selected all running rows based on numeric PID existence. It lacked
  a verified process identity and replaced original `dovada` values.
- The A12 patch returned an OPRESTE instruction, not an execution barrier.
  The complete caller and exception-handling contract is absent. A replacement
  exception at the same anchor is also not a demonstrated stop guarantee.
- Registry text matches were rewritten and described as verified requirements.
  Text matches cannot prove event delivery, retry bounds, role behavior or
  isolation. This repair no longer changes any requirement, including A4.

During review, PR #85 landed at `43ebf507e6cc385c781be0c62749abc6d54bf216`.
It preserves previous evidence, checks age and a PID prefix in `amprenta`, and
returns nonzero for partial failure. This PR is rebased onto that revision.
Those changes do not supply the missing ownership/schema/writer contract:
installation still precedes journal backup, the PID prefix does not verify the
remaining fingerprint, and the registry/A12 patch is unchanged. The refusal
supersedes the recovery path; it does not restore its earlier unsafe behavior.

The safe correction is refusal before mutation rather than inventing a new
journal schema, shared lock protocol or recovery algorithm. No rollback is
attempted: the disabled entry points make no changes to roll back. Old pinned
commits remain unchanged, and this patch cannot undo a previously run installer.
Whether the user ran that installer is unknown.

## Offline evidence

Run from the repository root:

```sh
python3 -B -m unittest deploy/test_repara_registru_procedura.py deploy/test_inchide_pasi_orfani.py -v
bash -n deploy/repara-registru.sh
python3 -m py_compile deploy/repara_registru_procedura.py deploy/inchide_pasi_orfani.py
```

The replacement regression suite on the old production files: 10 tests,
18 assertion failures including subtests, 0.259 seconds. On the corrected
files: 10 tests passed, 0.158 seconds. Syntax and diff whitespace checks passed.
After rebasing onto PR #85 and extending the synthetic fixture with its
`amprenta`/`t_start` columns, the 10-test suite again fails on that main revision
(18 assertion failures including subtests, 0.242 seconds) and pass on the
corrected files (0.116 seconds). CI runs these tests in the existing `teste` job.

Fixtures are synthetic. Shell tests intercept external commands and redirect
only the test copy's destination into a temporary directory; they inject
backup, cleanup, install, compile and download failure conditions. Database
tests cover missing/unknown data, missing/present PID observations, original
evidence, no connection/creation, and concurrent attempts while a fixture
writer holds a lock. Registry tests cover missing/empty/present procedure,
unchanged source/criteria, absent output, and repeated/concurrent attempts.
These establish non-mutation/refusal, not functioning recovery or repaired
live tasks. No network, live processes or real queue are used by the tests.

## Required before designing a replacement

Authorized repository copies of the complete queue, worker/callers and canonical
requirements; the actual schema/version and transition rules; process identity
provenance and namespace semantics; the writers' coordination/atomicity contract;
and sanitized traces/fixtures for the failing scenarios. Those inputs must
support an actual A12 execution barrier and scoped, evidence-preserving recovery.
Do not substitute unreviewed live access or weaker registry criteria.
