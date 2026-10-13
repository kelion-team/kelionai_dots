"""Durable reports for Kelion interfaces; delivery requires recipient acknowledgement.

The host must authenticate the caller and scope access to its owner/destination.
This module does not inject messages into ChatGPT or provision a server.
"""
import hashlib
import json
import sqlite3


class ReportOutbox:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS reports (
                owner TEXT NOT NULL, event_id TEXT NOT NULL, task_id TEXT NOT NULL,
                payload TEXT NOT NULL, digest TEXT NOT NULL,
                PRIMARY KEY(owner, event_id));
            CREATE TABLE IF NOT EXISTS recipients (
                owner TEXT NOT NULL, event_id TEXT NOT NULL, destination TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(owner, event_id, destination));
        ''')

    def publish(self, owner, event_id, task_id, payload, destinations):
        if isinstance(destinations, (str, bytes)):
            raise ValueError('Destinations must be a collection of nonblank strings')
        try:
            destinations = list(destinations)
        except TypeError as error:
            raise ValueError('Destinations must be a collection of nonblank strings') from error
        if not all(isinstance(v, str) and v.strip() for v in
                   [owner, event_id, task_id, *destinations]) or not destinations:
            raise ValueError('Explicit owner, event, task and destinations required')
        destinations = sorted(set(destinations))
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.db:
            # Start the write transaction before checking the stored report.
            self.db.execute('INSERT OR IGNORE INTO reports VALUES (?,?,?,?,?)',
                            (owner, event_id, task_id, encoded, digest))
            existing = self.db.execute(
                'SELECT task_id,payload FROM reports WHERE owner=? AND event_id=?',
                (owner, event_id)).fetchone()
            if existing and existing != (task_id, encoded):
                raise ValueError('Event ID already belongs to a different report')
            for destination in destinations:
                self.db.execute('INSERT OR IGNORE INTO recipients VALUES (?,?,?,0)',
                                (owner, event_id, destination))
        return digest

    def pending(self, owner, destination):
        rows = self.db.execute('''SELECT r.event_id,r.task_id,r.payload,r.digest
            FROM reports r JOIN recipients d
            ON r.owner=d.owner AND r.event_id=d.event_id
            WHERE d.owner=? AND d.destination=? AND d.acknowledged=0
            ORDER BY r.rowid''', (owner, destination)).fetchall()
        return [dict(event_id=e, task_id=t, payload=json.loads(p), sha256=h)
                for e, t, p, h in rows]

    def acknowledge(self, owner, destination, event_id, digest):
        with self.db:
            row = self.db.execute('''SELECT r.digest FROM reports r JOIN recipients d
                ON r.owner=d.owner AND r.event_id=d.event_id
                WHERE d.owner=? AND d.destination=? AND d.event_id=?''',
                (owner, destination, event_id)).fetchone()
            if not row or row[0] != digest:
                raise ValueError('Unknown recipient/event or mismatched report hash')
            self.db.execute('''UPDATE recipients SET acknowledged=1
                WHERE owner=? AND destination=? AND event_id=?''',
                (owner, destination, event_id))

    def close(self):
        self.db.close()
