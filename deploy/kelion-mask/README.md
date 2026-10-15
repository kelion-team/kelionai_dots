# Verified file deployment and rollback
Status: tested in temporary directories on kelion-nou; NOT applied to production.
Owner: Kelion. Independent reviewer: Claude.

## Contract
Run deploy_files.py with apply --root ROOT --source SOURCE --manifest MANIFEST --backup NEW_BACKUP.
Manifest is a nonempty JSON array. Every entry has path, source_sha256 and expected_current_sha256 (null for a new file).
Paths are relative to both ROOT and SOURCE. Environment files and symlinks are rejected.
All source bytes and destination preconditions are checked before any destination write.
Existing modes and ownership are retained. Each file is replaced atomically and read back.
The whole multi-file operation is NOT atomic. The transaction journal reports partial failure.
The CLI takes a nonblocking exclusive lock; other editors must respect the same ownership.

Rollback: deploy_files.py rollback --root ROOT --backup BACKUP.
It verifies backup hashes and refuses unexpected LIVE drift. It restores original bytes, modes and ownership.
New files are removed during rollback; empty parent directories can remain.
Never blindly repeat an ambiguous apply: read transaction.json and current hashes first.
Backup data must remain on the server, outside the repository.

## Scope
This tool does not generate credentials, restart services, change frontend symlinks or run inference.
Service installation and frontend activation require a separately reviewed procedure after the final frontend commit.
No automatic rollback is attempted if a file changes concurrently.
Trusted administrator-owned roots and manifest are required; this is not a sandbox for hostile filesystem writers.

## Evidence
python3 -m unittest test_deploy_files -v
Observed on kelion-nou: 9/9 passed, rc 0, 0.113 seconds.
The initial pre-implementation run failed on missing deploy_files module.
Independent review and a production deployment remain pending.
