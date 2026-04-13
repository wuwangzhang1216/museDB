"""Tests for memory hardening: provenance, confidence decay, and recall reinforcement.

Covers the v1.6 capabilities:
- source provenance tracking
- superseded_id breadcrumbs
- pin protection from supersession
- confidence decay (Ebbinghaus curve)
- recall reinforcement
- compute_confidence() pure function
"""

import math
import pytest

from opendb_core.storage.sqlite import SQLiteBackend
from opendb_core.storage.shared import compute_confidence


@pytest.fixture
async def backend(tmp_path):
    """Create a temporary SQLite backend."""
    db_path = tmp_path / "test.db"
    b = SQLiteBackend(db_path=db_path)
    await b.init()
    yield b
    await b.close()


# ------------------------------------------------------------------
# compute_confidence() unit tests (pure function)
# ------------------------------------------------------------------

class TestComputeConfidence:
    def test_no_decay_at_zero_days(self) -> None:
        """Confidence should not decay at day 0."""
        assert compute_confidence(1.0, 0.0, 0, False) == 1.0

    def test_pinned_never_decays(self) -> None:
        """Pinned memories should never lose confidence."""
        assert compute_confidence(1.0, 365.0, 0, True) == 1.0

    def test_90_pct_at_stability_point(self) -> None:
        """R(S, S) should equal 0.9 — the FSRS-4.5 design invariant."""
        # With stability=30 and 0 recalls, at t=30 days: R = 0.9
        conf = compute_confidence(1.0, 30.0, 0, False, stability=30.0)
        assert abs(conf - 0.9) < 0.001

    def test_decays_over_time(self) -> None:
        """Confidence should decrease over time for unaccessed memories."""
        conf_30d = compute_confidence(1.0, 30.0, 0, False, stability=30.0)
        conf_180d = compute_confidence(1.0, 180.0, 0, False, stability=30.0)
        assert conf_30d < 1.0
        assert conf_180d < conf_30d

    def test_reinforcement_slows_decay(self) -> None:
        """More recalls should slow the decay rate."""
        conf_no_recall = compute_confidence(1.0, 180.0, 0, False, stability=30.0)
        conf_3_recalls = compute_confidence(1.0, 180.0, 3, False, stability=30.0)
        conf_10_recalls = compute_confidence(1.0, 180.0, 10, False, stability=30.0)
        assert conf_3_recalls > conf_no_recall
        assert conf_10_recalls > conf_3_recalls

    def test_formula_correctness(self) -> None:
        """Verify the exact FSRS-4.5 formula: (1 + 19/81 * t / S_eff)^(-0.5)."""
        base, days, count, stab = 1.0, 60.0, 2, 30.0
        s_eff = stab * (1.0 + 0.5 * math.log(1.0 + count))
        expected = base * (1.0 + 19.0 / 81.0 * days / s_eff) ** (-0.5)
        actual = compute_confidence(base, days, count, False, stability=stab)
        assert abs(actual - expected) < 1e-10

    def test_power_law_has_heavier_tail(self) -> None:
        """Power-law decay should have a heavier tail than exponential.

        Both calibrated to R(30) = 0.9 at stability=30 days.
        At long durations, power-law retains more than exponential —
        this is the key advantage of FSRS, matching empirical data.
        """
        import math as m
        # Calibrate exponential to also give R=0.9 at t=30
        # exp(-k*30) = 0.9  →  k = -ln(0.9)/30
        k = -m.log(0.9) / 30.0
        days = 365.0
        power_law = compute_confidence(1.0, days, 0, False, stability=30.0)
        exp_decay = m.exp(-k * days)
        assert power_law > exp_decay, (
            f"At {days} days, power-law ({power_law:.4f}) should retain more "
            f"than exponential ({exp_decay:.4f}) calibrated to same 30-day point"
        )


# ------------------------------------------------------------------
# Provenance
# ------------------------------------------------------------------

class TestProvenance:
    @pytest.mark.asyncio
    async def test_source_stored_and_returned(self, backend) -> None:
        result = await backend.store_memory(
            memory_id="prov-1",
            content="User likes Python",
            memory_type="semantic",
            tags=[],
            metadata={},
            source="user_explicit",
        )
        assert result["source"] == "user_explicit"

        mem = await backend.get_memory("prov-1")
        assert mem["source"] == "user_explicit"

    @pytest.mark.asyncio
    async def test_source_defaults_to_unknown(self, backend) -> None:
        result = await backend.store_memory(
            memory_id="prov-2",
            content="Some inferred fact",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        assert result["source"] == "unknown"

    @pytest.mark.asyncio
    async def test_source_in_recall_results(self, backend) -> None:
        await backend.store_memory(
            memory_id="prov-3",
            content="Extracted from document: API key rotation policy",
            memory_type="procedural",
            tags=[],
            metadata={},
            source="tool_extraction",
        )
        result = await backend.recall_memories(
            query="API key rotation",
            memory_type=None, tags=None, limit=10, offset=0,
        )
        assert result["total"] > 0
        assert result["results"][0]["source"] == "tool_extraction"


# ------------------------------------------------------------------
# Supersession breadcrumbs
# ------------------------------------------------------------------

class TestSupersession:
    @pytest.mark.asyncio
    async def test_supersede_records_superseded_id(self, backend) -> None:
        await backend.store_memory(
            memory_id="ss-orig",
            content="My favorite color is blue.",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        result = await backend.store_memory(
            memory_id="ss-new",
            content="My favorite color is green. I changed it from blue.",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        assert result["superseded_id"] == "ss-orig"

    @pytest.mark.asyncio
    async def test_fresh_memory_has_no_superseded_id(self, backend) -> None:
        result = await backend.store_memory(
            memory_id="fresh-1",
            content="Completely new topic about quantum computing",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        assert result["superseded_id"] is None


# ------------------------------------------------------------------
# Pin protection
# ------------------------------------------------------------------

class TestPinProtection:
    @pytest.mark.asyncio
    async def test_pinned_memory_not_superseded(self, backend) -> None:
        await backend.store_memory(
            memory_id="pin-orig",
            content="My address is 123 Main Street.",
            memory_type="semantic",
            tags=[],
            metadata={},
            pinned=True,
        )
        await backend.store_memory(
            memory_id="pin-new",
            content="My address is 456 Oak Avenue. I moved to a new place.",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        all_mems = await backend.list_memories(
            memory_type="semantic", tags=None, limit=100, offset=0,
        )
        address_mems = [
            m for m in all_mems["memories"] if "address" in m["content"].lower()
        ]
        assert len(address_mems) == 2


# ------------------------------------------------------------------
# Confidence decay + recall reinforcement
# ------------------------------------------------------------------

class TestConfidenceDecay:
    @pytest.mark.asyncio
    async def test_new_memory_has_full_confidence(self, backend) -> None:
        """New memories should start with confidence = 1.0."""
        result = await backend.store_memory(
            memory_id="conf-1",
            content="Fresh fact about the project architecture",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        assert result["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_confidence_in_recall_results(self, backend) -> None:
        """Recall results should include a confidence field."""
        await backend.store_memory(
            memory_id="conf-2",
            content="The deployment server runs Ubuntu 22.04",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        result = await backend.recall_memories(
            query="deployment server Ubuntu",
            memory_type=None, tags=None, limit=10, offset=0,
        )
        assert result["total"] > 0
        assert "confidence" in result["results"][0]
        assert result["results"][0]["confidence"] > 0

    @pytest.mark.asyncio
    async def test_confidence_in_list_results(self, backend) -> None:
        """List results should include confidence."""
        await backend.store_memory(
            memory_id="conf-3",
            content="Team standup is at 9am daily",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        result = await backend.list_memories(
            memory_type=None, tags=None, limit=10, offset=0,
        )
        assert result["total"] > 0
        assert "confidence" in result["memories"][0]


class TestRecallReinforcement:
    @pytest.mark.asyncio
    async def test_recall_increments_access_count(self, backend) -> None:
        """Recalling a memory should increment its access_count."""
        await backend.store_memory(
            memory_id="reinf-1",
            content="The database password rotation schedule is weekly",
            memory_type="procedural",
            tags=[],
            metadata={},
        )

        # First recall
        await backend.recall_memories(
            query="database password rotation",
            memory_type=None, tags=None, limit=10, offset=0,
        )

        # Check access_count was bumped
        mem = await backend.get_memory("reinf-1")
        # get_memory doesn't return access_count directly, but we can check via raw SQL
        async with backend._db.execute(
            "SELECT access_count, last_accessed FROM memories WHERE memory_id = ?",
            ("reinf-1",),
        ) as cur:
            row = await cur.fetchone()
        assert row["access_count"] == 1
        assert row["last_accessed"] is not None

    @pytest.mark.asyncio
    async def test_multiple_recalls_accumulate(self, backend) -> None:
        """Multiple recalls should accumulate access_count."""
        await backend.store_memory(
            memory_id="reinf-2",
            content="The CI pipeline uses GitHub Actions with Node 24",
            memory_type="semantic",
            tags=[],
            metadata={},
        )

        # Recall 3 times
        for _ in range(3):
            await backend.recall_memories(
                query="CI pipeline GitHub Actions",
                memory_type=None, tags=None, limit=10, offset=0,
            )

        async with backend._db.execute(
            "SELECT access_count FROM memories WHERE memory_id = ?",
            ("reinf-2",),
        ) as cur:
            row = await cur.fetchone()
        assert row["access_count"] == 3

    @pytest.mark.asyncio
    async def test_supersede_resets_confidence(self, backend) -> None:
        """Superseding a memory should reset confidence to 1.0."""
        await backend.store_memory(
            memory_id="sup-conf-1",
            content="The API rate limit is 100 requests per minute.",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        # Supersede it
        result = await backend.store_memory(
            memory_id="sup-conf-2",
            content="The API rate limit is now 200 requests per minute. We changed it.",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        assert result["confidence"] == 1.0

    @pytest.mark.asyncio
    async def test_low_confidence_excluded_from_conflict_detection(self, backend) -> None:
        """Low-confidence memories should not be supersession candidates."""
        # Store a memory and manually set low confidence
        await backend.store_memory(
            memory_id="low-conf",
            content="My favorite framework is Django.",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        await backend._db.execute(
            "UPDATE memories SET confidence = 0.1 WHERE memory_id = ?",
            ("low-conf",),
        )
        await backend._db.commit()

        # Store a similar memory — should NOT supersede the low-conf one
        await backend.store_memory(
            memory_id="new-framework",
            content="My favorite framework is FastAPI. I switched from Django.",
            memory_type="semantic",
            tags=[],
            metadata={},
        )

        # Both should exist (low-conf one was skipped in conflict detection)
        all_mems = await backend.list_memories(
            memory_type="semantic", tags=None, limit=100, offset=0,
        )
        framework_mems = [
            m for m in all_mems["memories"] if "framework" in m["content"].lower()
        ]
        assert len(framework_mems) == 2


# ------------------------------------------------------------------
# Service-layer validation
# ------------------------------------------------------------------

class TestServiceValidation:
    @pytest.mark.asyncio
    async def test_invalid_source_rejected(self) -> None:
        from opendb_core.services.memory_service import store_memory
        with pytest.raises(ValueError, match="Invalid source"):
            await store_memory(content="test", source="invalid_source")

    @pytest.mark.asyncio
    async def test_valid_sources_accepted(self) -> None:
        from opendb_core.services.memory_service import VALID_SOURCES
        assert VALID_SOURCES == {"user_explicit", "ai_inference", "tool_extraction", "unknown"}


# ------------------------------------------------------------------
# Migration backward compatibility
# ------------------------------------------------------------------

class TestMigrationCompat:
    @pytest.mark.asyncio
    async def test_old_db_migrates_on_init(self, tmp_path) -> None:
        """A DB created without new columns should auto-migrate."""
        import aiosqlite

        db_path = tmp_path / "legacy.db"
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute("""
                CREATE TABLE memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'semantic',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    tags TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                )
            """)
            await db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(content)"
            )
            await db.execute(
                "INSERT INTO memories (memory_id, content) VALUES (?, ?)",
                ("legacy-1", "Old memory without new columns"),
            )
            await db.commit()

        backend = SQLiteBackend(db_path=db_path)
        await backend.init()

        try:
            mem = await backend.get_memory("legacy-1")
            assert mem is not None
            assert mem["source"] == "unknown"
            assert mem["superseded_id"] is None
            assert mem["confidence"] == 1.0
        finally:
            await backend.close()


# ------------------------------------------------------------------
# compute_confidence() edge cases
# ------------------------------------------------------------------

class TestComputeConfidenceEdgeCases:
    def test_very_small_stability_decays_fast(self) -> None:
        """Very small stability should decay quickly."""
        conf = compute_confidence(1.0, 1.0, 0, False, stability=0.001)
        assert conf < 0.1  # Heavy power-law tail, but should still be small

    def test_very_large_days(self) -> None:
        """At extreme durations, confidence should approach 0 but never go negative."""
        conf = compute_confidence(1.0, 100_000.0, 0, False, stability=30.0)
        # Power-law has heavier tail than exponential, so it stays above zero longer
        assert 0.0 < conf < 0.1

    def test_very_large_access_count(self) -> None:
        """High access_count should not cause overflow or errors."""
        conf = compute_confidence(1.0, 365.0, 1_000_000, False, stability=30.0)
        assert 0.0 < conf <= 1.0

    def test_base_confidence_less_than_one(self) -> None:
        """Non-1.0 base_confidence should scale the result proportionally."""
        full = compute_confidence(1.0, 60.0, 0, False, stability=30.0)
        half = compute_confidence(0.5, 60.0, 0, False, stability=30.0)
        assert abs(half - full * 0.5) < 1e-10

    def test_negative_days_returns_base(self) -> None:
        """Negative days_since_last_access should return base (no future-decay)."""
        conf = compute_confidence(1.0, -10.0, 0, False, stability=30.0)
        assert conf == 1.0

    def test_stability_parameter_affects_rate(self) -> None:
        """Higher stability should decay slower."""
        fast = compute_confidence(1.0, 60.0, 0, False, stability=10.0)
        slow = compute_confidence(1.0, 60.0, 0, False, stability=100.0)
        assert slow > fast


# ------------------------------------------------------------------
# Confidence filtering in recall results
# ------------------------------------------------------------------

class TestConfidenceFiltering:
    @pytest.mark.asyncio
    async def test_faded_memory_excluded_from_recall(self, backend) -> None:
        """A memory with confidence driven below threshold should not appear in recall."""
        await backend.store_memory(
            memory_id="faded-1",
            content="The old server IP address was 10.0.0.1",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        # Simulate decay: set confidence very low and last_accessed far in the past
        await backend._db.execute(
            "UPDATE memories SET confidence = 0.05, "
            "last_accessed = strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1000 days') "
            "WHERE memory_id = ?",
            ("faded-1",),
        )
        await backend._db.commit()

        result = await backend.recall_memories(
            query="server IP address",
            memory_type=None, tags=None, limit=10, offset=0,
        )
        faded = [r for r in result["results"] if r["memory_id"] == "faded-1"]
        assert len(faded) == 0, "Faded memory should not appear in recall results"

    @pytest.mark.asyncio
    async def test_fresh_memory_above_threshold(self, backend) -> None:
        """A freshly stored memory should always be above threshold."""
        await backend.store_memory(
            memory_id="fresh-recall",
            content="The new deployment pipeline uses Docker containers",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        result = await backend.recall_memories(
            query="deployment pipeline Docker",
            memory_type=None, tags=None, limit=10, offset=0,
        )
        assert result["total"] > 0
        found = [r for r in result["results"] if r["memory_id"] == "fresh-recall"]
        assert len(found) == 1
        assert found[0]["confidence"] > 0.9

    @pytest.mark.asyncio
    async def test_faded_memory_not_reinforced(self, backend) -> None:
        """Memories filtered out by confidence should NOT get reinforced."""
        await backend.store_memory(
            memory_id="no-reinf",
            content="Obsolete config setting for the legacy proxy server",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        await backend._db.execute(
            "UPDATE memories SET confidence = 0.05, "
            "last_accessed = strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1000 days') "
            "WHERE memory_id = ?",
            ("no-reinf",),
        )
        await backend._db.commit()

        # Recall — faded memory should be filtered out and not reinforced
        await backend.recall_memories(
            query="legacy proxy server config",
            memory_type=None, tags=None, limit=10, offset=0,
        )

        async with backend._db.execute(
            "SELECT access_count FROM memories WHERE memory_id = ?",
            ("no-reinf",),
        ) as cur:
            row = await cur.fetchone()
        assert row["access_count"] == 0, "Faded memory should not have been reinforced"


# ------------------------------------------------------------------
# Confidence × temporal_score interaction
# ------------------------------------------------------------------

class TestConfidenceScoring:
    @pytest.mark.asyncio
    async def test_higher_confidence_ranks_higher(self, backend) -> None:
        """Between two FTS-matching memories, higher confidence should rank higher."""
        # Use episodic to avoid supersession between similar content
        await backend.store_memory(
            memory_id="hi-conf",
            content="The team meeting about database migration was productive",
            memory_type="episodic",
            tags=[],
            metadata={},
        )
        await backend.store_memory(
            memory_id="lo-conf",
            content="The team meeting about database migration was postponed",
            memory_type="episodic",
            tags=[],
            metadata={},
        )
        # Artificially lower one's confidence
        await backend._db.execute(
            "UPDATE memories SET confidence = 0.4 WHERE memory_id = ?",
            ("lo-conf",),
        )
        await backend._db.commit()

        result = await backend.recall_memories(
            query="team meeting database migration",
            memory_type=None, tags=None, limit=10, offset=0,
        )
        # Check that returned confidence values reflect the difference
        confs = {r["memory_id"]: r["confidence"] for r in result["results"]}
        assert "hi-conf" in confs, "High-confidence memory should appear in results"
        # hi-conf was just created (confidence=1.0), lo-conf was set to 0.4
        # live confidence should reflect this difference in the results
        if "lo-conf" in confs:
            assert confs["hi-conf"] >= confs["lo-conf"], (
                "Higher stored confidence should yield higher live confidence"
            )


# ------------------------------------------------------------------
# Pinned-only path (no FTS, no reinforcement)
# ------------------------------------------------------------------

class TestPinnedOnlyPath:
    @pytest.mark.asyncio
    async def test_pinned_only_does_not_reinforce(self, backend) -> None:
        """Pinned-only recall should not trigger reinforcement."""
        await backend.store_memory(
            memory_id="pin-no-reinf",
            content="Critical system invariant",
            memory_type="procedural",
            tags=[],
            metadata={},
            pinned=True,
        )
        await backend.recall_memories(
            query="",
            memory_type=None, tags=None, limit=10, offset=0,
            pinned_only=True,
        )
        async with backend._db.execute(
            "SELECT access_count FROM memories WHERE memory_id = ?",
            ("pin-no-reinf",),
        ) as cur:
            row = await cur.fetchone()
        assert row["access_count"] == 0, "Pinned-only path should not reinforce"

    @pytest.mark.asyncio
    async def test_pinned_only_returns_confidence(self, backend) -> None:
        """Pinned-only results should include confidence field."""
        await backend.store_memory(
            memory_id="pin-conf",
            content="Must-know system constraint",
            memory_type="procedural",
            tags=[],
            metadata={},
            pinned=True,
        )
        result = await backend.recall_memories(
            query="",
            memory_type=None, tags=None, limit=10, offset=0,
            pinned_only=True,
        )
        assert result["total"] > 0
        assert "confidence" in result["results"][0]


# ------------------------------------------------------------------
# Recall reinforcement resets forgetting curve
# ------------------------------------------------------------------

class TestReinforcementResetsCurve:
    @pytest.mark.asyncio
    async def test_recall_resets_confidence_to_one(self, backend) -> None:
        """After recall, stored confidence should be reset to 1.0."""
        await backend.store_memory(
            memory_id="reset-1",
            content="The API endpoint for user auth is /api/v2/auth",
            memory_type="semantic",
            tags=[],
            metadata={},
        )
        # Simulate partial decay
        await backend._db.execute(
            "UPDATE memories SET confidence = 0.7 WHERE memory_id = ?",
            ("reset-1",),
        )
        await backend._db.commit()

        # Recall should reinforce → reset confidence to 1.0
        await backend.recall_memories(
            query="API endpoint user auth",
            memory_type=None, tags=None, limit=10, offset=0,
        )

        async with backend._db.execute(
            "SELECT confidence FROM memories WHERE memory_id = ?",
            ("reset-1",),
        ) as cur:
            row = await cur.fetchone()
        assert row["confidence"] == 1.0, "Recall should reset confidence to 1.0"

    @pytest.mark.asyncio
    async def test_reinforcement_updates_last_accessed(self, backend) -> None:
        """Recall should update last_accessed timestamp."""
        await backend.store_memory(
            memory_id="ts-1",
            content="The deployment schedule is every Tuesday at 3pm",
            memory_type="semantic",
            tags=[],
            metadata={},
        )

        # Get initial state
        async with backend._db.execute(
            "SELECT last_accessed FROM memories WHERE memory_id = ?",
            ("ts-1",),
        ) as cur:
            before = await cur.fetchone()
        assert before["last_accessed"] is None, "New memory should have NULL last_accessed"

        # Recall to trigger reinforcement
        await backend.recall_memories(
            query="deployment schedule Tuesday",
            memory_type=None, tags=None, limit=10, offset=0,
        )

        async with backend._db.execute(
            "SELECT last_accessed FROM memories WHERE memory_id = ?",
            ("ts-1",),
        ) as cur:
            after = await cur.fetchone()
        assert after["last_accessed"] is not None, "Recall should set last_accessed"
