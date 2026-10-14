# Server snapshot, 14 October 2026

This is an export for review, not a deployment or completed repair.

- ingress/: active current release observed on kelion-nou, prefix562af2586079.
- web/: actual /opt/kelion-app/web-v1 frontend and Google-auth gateway.
- EXPORT-MANIFEST.json: byte lengths and SHA256 for29 source files, including .gitignore.
- diagnostic/status.json: bounded observations and unchecked acceptance criteria.

The original export routine was adapted to a new unique temporary directory, to preserve prior exports, include web-v1, and avoid reading configuration values or broad logs. The server code and services were not changed.

No environment files, credentials, databases, user task data, sessions or private logs are included. Secret-pattern checks are heuristic, not a guarantee of absence. Runtime templates remain explicitly unverified. The old documented ingress-v2 location does not contain the web-v1 frontend.

No dependency installation, test rerun, server restart, merge or live activation is part of this PR. Existing activation denial is not bypassed.
