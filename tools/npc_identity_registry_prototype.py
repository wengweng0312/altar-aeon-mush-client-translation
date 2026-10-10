"""Isolated SQLite prototype for confirmed NPC identities and safe markers."""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path


MARKER = re.compile(r"ZXQNPC(\d{4})QXZ")


class IdentityRegistry:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(str(path))
        self.db.execute("""CREATE TABLE IF NOT EXISTS npc_identity_candidates(
            identity TEXT PRIMARY KEY,
            state TEXT NOT NULL CHECK(state IN ('candidate','confirmed')),
            chinese_name TEXT NOT NULL DEFAULT '',
            evidence_count INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS npc_identity_variants(
            identity TEXT NOT NULL,
            variant TEXT NOT NULL,
            PRIMARY KEY(identity, variant)
        )""")
        self.db.commit()

    def close(self):
        self.db.close()

    def observe(self, identity: str, variant: str, strong: bool = False):
        key = identity.strip().lower()
        now = int(time.time())
        row = self.db.execute(
            "SELECT state,evidence_count FROM npc_identity_candidates WHERE identity=?", (key,),
        ).fetchone()
        count = (row[1] if row else 0) + 1
        state = row[0] if row else "candidate"
        # Observation alone never invents a Chinese spelling.  It may only
        # strengthen a candidate; explicit confirmation supplies the name.
        self.db.execute("""INSERT OR REPLACE INTO npc_identity_candidates
            (identity,state,chinese_name,evidence_count,created_at,updated_at)
            VALUES(?,?,COALESCE((SELECT chinese_name FROM npc_identity_candidates WHERE identity=?),''),?,
                   COALESCE((SELECT created_at FROM npc_identity_candidates WHERE identity=?),?),?)""",
            (key, state, key, count, key, now, now),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO npc_identity_variants(identity,variant) VALUES(?,?)",
            (key, variant.strip()),
        )
        self.db.commit()
        return state, count, strong

    def confirm(self, identity: str, chinese_name: str, variants=()):
        key = identity.strip().lower()
        chinese_name = chinese_name.strip()
        if not chinese_name or len(chinese_name) > 40 or re.search(r"[\r\n，。！？,:：；;]", chinese_name):
            raise ValueError("invalid Chinese NPC name")
        now = int(time.time())
        row = self.db.execute(
            "SELECT created_at,evidence_count FROM npc_identity_candidates WHERE identity=?", (key,),
        ).fetchone()
        created, count = row if row else (now, 1)
        self.db.execute("""INSERT OR REPLACE INTO npc_identity_candidates
            (identity,state,chinese_name,evidence_count,created_at,updated_at)
            VALUES(?,'confirmed',?,?,?,?)""",
            (key, chinese_name, count, created, now),
        )
        for variant in (identity, *variants):
            self.db.execute(
                "INSERT OR IGNORE INTO npc_identity_variants(identity,variant) VALUES(?,?)",
                (key, str(variant).strip()),
            )
        self.db.commit()

    def confirmed(self):
        rows = self.db.execute("""SELECT c.identity,c.chinese_name,v.variant
            FROM npc_identity_candidates c
            JOIN npc_identity_variants v ON v.identity=c.identity
            WHERE c.state='confirmed' AND c.chinese_name<>''
            ORDER BY LENGTH(v.variant) DESC, v.variant COLLATE NOCASE""").fetchall()
        return rows

    def protect(self, source: str):
        """Replace confirmed English names; every occurrence gets one marker."""
        protected = str(source)
        occurrences = []
        # Work from the original variants in longest-first order.  A marker
        # contains no whitespace and cannot match a later English variant.
        for identity, chinese_name, variant in self.confirmed():
            pattern = re.compile(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(variant), re.I)

            def replace(match):
                index = len(occurrences)
                marker = "ZXQNPC%04dQXZ" % index
                occurrences.append({
                    "marker": marker,
                    "identity": identity,
                    "variant": match.group(0),
                    "chinese_name": chinese_name,
                })
                return marker

            protected = pattern.sub(replace, protected)
        return protected, occurrences

    @staticmethod
    def restore(translated: str, occurrences):
        result = str(translated)
        expected = {item["marker"] for item in occurrences}
        found = set(MARKER.findall(result))
        found_markers = {"ZXQNPC%sQXZ" % value for value in found}
        if found_markers != expected:
            raise RuntimeError("NPC_MARKER_SET_MISMATCH")
        for item in occurrences:
            marker = item["marker"]
            if result.count(marker) != 1:
                raise RuntimeError("NPC_MARKER_COUNT_MISMATCH")
            result = result.replace(marker, item["chinese_name"])
        if MARKER.search(result):
            raise RuntimeError("NPC_MARKER_REMAINS")
        return result

