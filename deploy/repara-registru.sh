#!/usr/bin/env bash
# Disabled before any read/download/install: the repository does not contain the
# complete queue/caller contract or a verified journal/process identity contract.
# A pinned revision does not supply those missing preconditions. No override.
set -euo pipefail
printf '%s\n' 'OPRIT: reparația registrului și închiderea pașilor sunt dezactivate: lipsesc sursele complete ale cozii, schema verificată și identitatea proceselor. Nimic citit sau modificat pe server; nicio cerință declarată îndeplinită.' >&2
exit 1
