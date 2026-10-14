# Rutina pentru Kelion: export site kelionai.app în GitHub

Scop: codul site-ului există doar pe serverul kelion-nou. Rutina îl copiază, împreună cu un diagnostic, în acest repository, fără secrete, ca reparațiile să se poată face din GitHub. Rutina doar citește și copiază; nu modifică și nu repornește nimic pe server.

## Cine o rulează

Un singur agent Kelion care are deja acces legitim la server (de ex. conectorul Desktop Commander al ChatGPT, legat la device-ul serverului). Nu se folosesc parole din Drive sau din chat. Nu se creează acces nou pe server.

## Pași

1. Pe server, din acest repository (sau copiind scriptul):
   `bash scripts/export_site_snapshot.sh /opt/kelion-app/ingress-v2 /tmp/kelion-site-export`
2. Dacă scriptul se oprește cu „OPRIT: … secret”, nu urca nimic; raportează lista de fișiere.
3. Dacă afișează „OK”, urcă conținutul `/tmp/kelion-site-export` în `kelion-team/kelionai_dots`, ramura nouă `site/ingress-v2`, în folderul `site-live/`, prin conectorul GitHub existent (ChatGPT Codex Connector). Deschide un PR către `main` cu titlul „Export site kelionai.app (fără secrete)”.
4. Raportează linkul PR-ului. Nu declara aplicația reparată: acest pas doar salvează codul.

## Ce urmează după export

Reparațiile (testul de izolare, worker-ul, login-ul) se fac prin PR-uri pe `site-live/`, apoi se aplică pe server de agentul cu acces, conform `orchestration/ACCES-SERVER.md`.
