<p align="center">
  <a href="https://github.com/wuwangzhang1216/museDB">
    <img loading="lazy" alt="MuseDB" src="https://github.com/wuwangzhang1216/museDB/raw/main/docs/assets/musedb-banner.svg" width="100%"/>
  </a>
</p>

<p align="center">
  <strong>The file database built for AI agents.</strong><br/>
  Parse once, query forever. <code>cat</code> + <code>grep</code> for any file format.
</p>

<p align="center">
  <a href="https://pypi.org/project/musedb/"><img src="https://img.shields.io/pypi/v/musedb" alt="PyPI version"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"/></a>
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/License-AGPL%20v3-blue.svg" alt="License: AGPL v3"/></a>
  <a href="https://github.com/wuwangzhang1216/museDB/stargazers"><img src="https://img.shields.io/github/stars/wuwangzhang1216/museDB" alt="GitHub stars"/></a>
</p>

---

MuseDB turns any file — code, PDF, DOCX, PPTX, XLSX, CSV, images — into instantly searchable plain text. 4 MCP tools give LLM agents full read/search access without writing parsing scripts.

## Why MuseDB?

Without MuseDB, agents write inline parsing code for every document:

```python
# Agent writes this every time — 500+ tokens, often fails
run_command("""python -c "
import PyMuPDF; doc = PyMuPDF.open('report.pdf')
for page in doc: print(page.get_text())
" """)
```

With MuseDB:

```python
read_file("report.pdf")  # 50 tokens, always works
```

**Benchmarked across 4 LLMs on 24 document tasks:**

| Metric | Without MuseDB | With MuseDB |
|--------|---------------|-------------|
| Tokens used | 100% | **27-45%** (55-73% saved) |
| Task speed | 100% | **36-58%** faster |
| Answer quality | 2.4-3.2 / 5 | **3.4-3.9 / 5** |
| Success rate | 79% | **100%** |

**MuseDB FTS vs RAG vector retrieval (25-325 documents):**

| Scale | FTS Tokens Saved | FTS Quality | RAG Quality |
|-------|-----------------|------------|------------|
| 25 docs | **47%** | 3.9/5 | 4.2/5 |
| 125 docs | **44%** | **4.7/5** | 4.0/5 |
| 325 docs | **45%** | **4.6/5** | 3.5/5 |

FTS quality **improves with scale** while RAG degrades from distractor noise. See [benchmark/REPORT.md](benchmark/REPORT.md) for methodology.

## Quick Start

```bash
pip install musedb[cli]
musedb index ./my_workspace       # parse & index everything
musedb serve-mcp                  # start MCP server (stdio)
```

Configure in your agent (Claude Code, Cursor, etc.):

```yaml
mcp:
  musedb:
    transport: stdio
    command: musedb
    args: ["serve-mcp", "--workspace", "/path/to/workspace"]
```

That's it. Your agent now has `musedb_read`, `musedb_search`, `musedb_glob`, and `musedb_info`.

## MCP Tools

### `musedb_info` — Workspace overview

Get file counts, type distribution, and recent activity. Use as the first step in a new workspace.

```
musedb_info()
→ Workspace: 47 files (ready: 45, processing: 1, failed: 1)
  By type:  Python (.py) 20 | PDF 12 | Excel (.xlsx) 5 | ...
  Recently updated:  config.yaml (2 min ago) | main.py (1 hr ago)
```

### `musedb_read` — Read any file

Code with line numbers, documents as plain text, spreadsheets as structured JSON.

```
musedb_read(filename="main.py")                            # Code with line numbers
musedb_read(filename="report.pdf", pages="1-3")            # PDF pages
musedb_read(filename="report.pdf", grep="revenue+growth")  # Search within file
musedb_read(filename="budget.xlsx", format="json")          # Structured spreadsheet
musedb_read(filename="app.py", offset=50, limit=31)         # Lines 50-80
```

### `musedb_search` — Search across code and documents

Regex grep for code, full-text search for documents. Auto-detects mode.

```
musedb_search(query="def main", path="/workspace", glob="*.py")   # Grep code
musedb_search(query="quarterly revenue")                           # FTS documents
musedb_search(query="TODO", path="/src", case_insensitive=True)    # Case insensitive
```

Search results include `updated_at` timestamps so agents can judge information freshness.

### `musedb_glob` — Find files

Glob pattern matching, sorted by modification time (newest first).

```
musedb_glob(pattern="**/*.py", path="/workspace")
musedb_glob(pattern="src/**/*.{ts,tsx}", path="/workspace")
```

## Python Library

```bash
pip install musedb[cli]
```

```python
from musedb import MuseDB

db = MuseDB.open("./my_workspace")
await db.init()
await db.index()

stats   = await db.info()                                # workspace overview
text    = await db.read("report.pdf", pages="1-3")       # read any file
results = await db.search("quarterly revenue")            # full-text search

await db.close()
```

For server mode (PostgreSQL) or agent framework integration, see [docs/python-library.md](docs/python-library.md).

## REST API

MuseDB also exposes a full HTTP API. Run with `musedb serve` (embedded) or `docker-compose up` (PostgreSQL).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/info` | `GET` | Workspace statistics (file counts, types, recent files) |
| `/read/{filename}` | `GET` | Read file (`?pages=`, `?lines=`, `?grep=`, `?format=json`, `?numbered=true`) |
| `/search` | `POST` | Full-text search or regex grep (`{"query", "mode", "path", "glob", ...}`) |
| `/glob` | `GET` | Find files by glob pattern (`?pattern=`, `?path=`) |
| `/index` | `POST` | Index a directory and start watching (`?path=`) |
| `/files` | `POST` | Upload a single file |
| `/files` | `GET` | List files with metadata |
| `/files/{id}` | `GET`/`DELETE` | File details / delete |
| `/watch` | `GET` | List active watchers |
| `/watch/{id}` | `GET`/`DELETE` | Watcher details / stop |
| `/health` | `GET` | Health check |

## Supported Formats

| Format | Extensions | Features |
|--------|-----------|----------|
| PDF | `.pdf` | Pages, tables, OCR for scanned docs |
| Word | `.docx` | Page breaks, tables, headings |
| PowerPoint | `.pptx` | Slides, speaker notes, tables |
| Excel | `.xlsx` | Multiple sheets, structured JSON output |
| CSV | `.csv` | Auto-encoding detection, structured JSON |
| Code | `.py` `.js` `.ts` `.go` `.rs` `.java` ... | Line-numbered output |
| Text | `.txt` `.md` `.html` `.json` `.xml` | Paragraph chunking |
| Images | `.png` `.jpg` `.tiff` `.bmp` | OCR (English + Chinese) |

## Key Features

- **Dual-mode** — Embedded (SQLite, zero-config) or Server (PostgreSQL, shared access); same API
- **4 MCP tools** — `read`, `search`, `glob`, `info` — replace an agent's built-in file tools
- **Real-time sync** — Directories are watched via OS-native events after indexing
- **Full-text search** — FTS5 (SQLite) / tsvector (PostgreSQL) + CJK substring fallback
- **Structured output** — Spreadsheets as `{sheets: [{columns, rows}]}` for direct analysis
- **Fuzzy filename resolution** — Find files by exact name, partial match, path, or UUID
- **Duplicate detection** — SHA-256 deduplication across uploads and directory scans
- **Search provenance** — Results include `updated_at` timestamps for freshness judgment

## Configuration

Environment variables (`FILEDB_` prefix):

| Variable | Default | Description |
|----------|---------|-------------|
| `FILEDB_BACKEND` | `postgres` | `postgres` or `sqlite` |
| `FILEDB_DATABASE_URL` | `postgresql://...` | PostgreSQL connection |
| `FILEDB_OCR_ENABLED` | `true` | Enable Tesseract OCR |
| `FILEDB_OCR_LANGUAGES` | `eng+chi_sim+chi_tra` | OCR languages |
| `FILEDB_MAX_FILE_SIZE` | `104857600` | Max file size (100MB) |
| `FILEDB_INDEX_EXCLUDE_PATTERNS` | `[]` | Exclude patterns for indexing |
| `MUSEDB_URL` | `http://localhost:8000` | MCP server → REST API URL |

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

[AGPL-3.0](LICENSE) — Source code must be shared when running as a network service.
