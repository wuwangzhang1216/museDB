"""MuseDB client — direct Python library access (no HTTP).

Supports two modes:

**Embedded mode** (SQLite, zero-config, no PostgreSQL needed)::

    db = MuseDBClient(workspace_path="./my_workspace")
    await db.init()
    text = await db.read_file("report.pdf", pages="1-3")
    await db.close()

**Server mode** (PostgreSQL, backward-compatible)::

    db = MuseDBClient("postgresql://musedb:musedb@localhost:5432/musedb")
    await db.init()
    text = await db.read_file("report.pdf", pages="1-3")
    await db.close()
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MuseDBClient:
    """Direct Python client for MuseDB.

    Calls MuseDB service functions directly — no HTTP, no port.
    Supports both PostgreSQL (server mode) and SQLite (embedded mode).
    """

    def __init__(
        self,
        database_url: str | None = None,
        file_storage_path: str = "./data",
        pool_min: int = 2,
        pool_max: int = 10,
        *,
        workspace_path: str | Path | None = None,
    ):
        """
        Args:
            database_url: PostgreSQL DSN. If provided (and ``workspace_path``
                is not), uses server/PostgreSQL mode.
            file_storage_path: Where to store uploaded file blobs (server mode).
            pool_min / pool_max: asyncpg pool sizes (server mode).
            workspace_path: Path to a local workspace root. When provided,
                activates **embedded mode** (SQLite) and overrides
                ``database_url``.
        """
        if workspace_path is not None:
            self._mode = "embedded"
            self._workspace_path = Path(workspace_path)
        else:
            self._mode = "postgres"
            self._database_url = (
                database_url
                or "postgresql://musedb:musedb@localhost:5432/musedb"
            )
            self._file_storage_path = Path(file_storage_path)
            self._pool_min = pool_min
            self._pool_max = pool_max

        self._initialized = False
        self._available: bool | None = None

    async def init(self) -> None:
        """Initialize the client."""
        if self._initialized:
            return

        if self._mode == "embedded":
            await self._init_embedded()
        else:
            await self._init_postgres()

    async def _init_embedded(self) -> None:
        try:
            from app.workspace import Workspace
            self._workspace = Workspace.open(self._workspace_path)
            await self._workspace.init()
            self._initialized = True
            self._available = True
            logger.info("MuseDB initialised (embedded mode) — %s", self._workspace_path)
        except Exception as e:
            logger.warning("MuseDB embedded init failed: %s", e)
            self._available = False

    async def _init_postgres(self) -> None:
        try:
            from app.database import init_pool
            from app.config import settings
            from app.storage import init_backend

            settings.database_url = self._database_url
            settings.db_pool_min = self._pool_min
            settings.db_pool_max = self._pool_max
            settings.file_storage_path = self._file_storage_path

            await init_pool()
            await init_backend("postgres")
            self._file_storage_path.mkdir(parents=True, exist_ok=True)
            self._initialized = True
            self._available = True
            logger.info("MuseDB initialised (postgres mode) — %s", self._database_url)
        except Exception as e:
            logger.warning("MuseDB postgres init failed: %s", e)
            self._available = False

    async def is_available(self) -> bool:
        """Check if MuseDB is initialized and the backend is reachable."""
        if not self._initialized:
            try:
                await self.init()
            except Exception:
                return False
        if not self._available:
            return False

        if self._mode == "postgres":
            try:
                from app.database import get_pool
                pool = await get_pool()
                await pool.fetchval("SELECT 1")
                return True
            except Exception:
                self._available = False
                return False

        return True  # embedded SQLite is always available once initialised

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def read_file(
        self,
        filename: str,
        numbered: bool = False,
        pages: str | None = None,
        lines: str | None = None,
        grep: str | None = None,
        format: str | None = None,
    ) -> str | None:
        """Read a file by filename. Returns None if unavailable."""
        if not await self.is_available():
            return None
        try:
            from app.services.read_service import (
                resolve_filename,
                read_file_text,
                read_structured_spreadsheet,
                FileNotFoundError,
            )
            from app.utils.text import format_with_line_numbers

            file_id = await resolve_filename(filename)

            if format == "json":
                data = await read_structured_spreadsheet(file_id, pages=pages)
                return json.dumps(data, indent=2, ensure_ascii=False)

            text, info = await read_file_text(
                file_id, pages=pages, lines=lines, grep=grep
            )

            if numbered and not grep:
                start_line = 1
                if lines:
                    parts = lines.strip().split("-")
                    start_line = int(parts[0])
                text = format_with_line_numbers(text, start=start_line)

            return text
        except Exception as e:
            logger.debug("MuseDB read_file failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        mode: str = "fts",
        path: str | None = None,
        glob: str | None = None,
        case_insensitive: bool = False,
        context: int = 0,
        limit: int = 20,
        offset: int = 0,
        max_results: int = 100,
    ) -> dict | None:
        """Search files. Returns None if unavailable."""
        if not await self.is_available():
            return None
        try:
            if mode == "grep" or (mode == "auto" and (path or glob)):
                from app.services.grep_service import grep_files
                return await grep_files(
                    query=query,
                    path=path or ".",
                    glob=glob,
                    case_insensitive=case_insensitive,
                    context=context,
                    max_results=max_results,
                )
            else:
                from app.services.search_service import search_files
                return await search_files(query=query, limit=limit, offset=offset)
        except Exception as e:
            logger.debug("MuseDB search failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Glob
    # ------------------------------------------------------------------

    async def glob_files(self, pattern: str, path: str | None = None) -> dict | None:
        """Find files matching glob pattern. Returns None if unavailable."""
        if path is None:
            return None
        try:
            root = Path(path)
            if not root.is_dir():
                return None

            matches = []
            for p in root.glob(pattern):
                if p.is_file():
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    matches.append((p, mtime))

            matches.sort(key=lambda x: x[1], reverse=True)
            truncated = len(matches) > 500
            matches = matches[:500]

            files = []
            for p, _ in matches:
                try:
                    files.append(str(p.relative_to(root)).replace(os.sep, "/"))
                except ValueError:
                    files.append(str(p).replace(os.sep, "/"))

            return {"count": len(files), "truncated": truncated, "files": files}
        except Exception as e:
            logger.debug("MuseDB glob failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    async def index_directory(
        self, path: str, tags: list[str] | None = None
    ) -> dict | None:
        """Index a directory. Returns None if unavailable."""
        if not await self.is_available():
            return None
        try:
            from app.services.index_service import index_directory
            return await index_directory(
                dir_path=Path(path),
                tags=tags or [],
                metadata={},
                max_concurrent=4,
            )
        except Exception as e:
            logger.debug("MuseDB index_directory failed: %s", e)
            return None

    async def upload_file(self, file_path: str | Path) -> dict | None:
        """Ingest a single file. Returns None if unavailable."""
        if not await self.is_available():
            return None
        fp = Path(file_path)
        if not fp.exists():
            return None
        try:
            from app.services.ingest_service import ingest_local_file
            return await ingest_local_file(source_path=fp, tags=[], metadata={})
        except Exception as e:
            logger.debug("MuseDB upload_file failed: %s", e)
            return None

    async def list_watchers(self) -> list[dict] | None:
        """List active directory watchers."""
        try:
            from app.services.watch_service import list_watches
            return list_watches()
        except Exception as e:
            logger.debug("MuseDB list_watchers failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the backend."""
        if not self._initialized:
            return
        try:
            if self._mode == "embedded":
                await self._workspace.close()
            else:
                from app.storage import close_backend
                from app.database import close_pool
                await close_backend()
                await close_pool()
        except Exception:
            pass
        self._initialized = False
        self._available = False
