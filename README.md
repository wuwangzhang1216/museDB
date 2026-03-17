<p align="center">
  <a href="https://github.com/wuwangzhang1216/museDB">
    <img loading="lazy" alt="MuseDB" src="https://github.com/wuwangzhang1216/museDB/raw/main/docs/assets/musedb-banner.svg" width="100%"/>
  </a>
</p>

# MuseDB

<p align="center">
  <strong>The AI-Native File Database</strong><br/>
  <code>cat</code> + <code>grep</code> for any file format. Parse once, query forever.
</p>

<p align="center">
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/License-AGPL%20v3-blue.svg" alt="License: AGPL v3"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"/></a>
  <a href="https://pypi.org/project/musedb/"><img src="https://img.shields.io/pypi/v/musedb" alt="PyPI version"/></a>
  <a href="https://github.com/wuwangzhang1216/museDB/stargazers"><img src="https://img.shields.io/github/stars/wuwangzhang1216/museDB" alt="GitHub stars"/></a>
</p>

MuseDB turns any document — PDF, DOCX, PPTX, XLSX, CSV, images — into instantly-searchable plain text through 3 HTTP endpoints. Built for LLM agents that need to read files without writing parsing scripts.

## Quick Start

```bash
git clone https://github.com/wuwangzhang1216/museDB.git
cd museDB
docker-compose up -d
```

MuseDB is now running at `http://localhost:8000`.

## Agent Quick Start

Give your agent these 3 tools and it can read any file format:

### Tool 1: Upload a file

```bash
curl -X POST http://localhost:8000/files -F "file=@report.pdf"
```
```json
{"id": "a1b2c3...", "filename": "report.pdf", "status": "ready", "total_pages": 12, "total_lines": 847}
```

### Tool 2: Read a file

```bash
# Read the whole file
curl http://localhost:8000/read/report.pdf

# Read pages 1-3 only
curl "http://localhost:8000/read/report.pdf?pages=1-3"

# Read lines 50-80
curl "http://localhost:8000/read/report.pdf?lines=50-80"

# Grep for a pattern
curl "http://localhost:8000/read/report.pdf?grep=revenue"

# Multi-term search (AND logic)
curl "http://localhost:8000/read/report.pdf?grep=revenue+growth"
```

Returns plain text. No JSON parsing needed. Just like `cat` and `grep`.

### Tool 3: Search across all files

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "quarterly revenue"}'
```
```json
{
  "total": 3,
  "results": [
    {"filename": "report.pdf", "page_number": 4, "highlight": "...quarterly revenue grew 23%...", "relevance_score": 0.89},
    {"filename": "slides.pptx", "page_number": 2, "highlight": "...quarterly revenue target...", "relevance_score": 0.71}
  ]
}
```

That's the entire API an agent needs. Upload, read, search.

---

## Agent Tool Definitions

Copy-paste these tool definitions into your agent:

```python
MUSEDB = "http://localhost:8000"

def upload_file(filepath: str) -> dict:
    """Upload a file to MuseDB. Supports PDF, DOCX, PPTX, XLSX, CSV, TXT, images."""
    import httpx
    with open(filepath, "rb") as f:
        return httpx.post(f"{MUSEDB}/files", files={"file": f}).json()

def read_file(filename: str, pages: str = "", lines: str = "", grep: str = "") -> str:
    """Read a file as plain text. Like cat + grep for any format.

    Args:
        filename: Exact filename, partial match, or file UUID.
        pages: Optional. Page range like "1-3", "5", or sheet name like "Revenue".
        lines: Optional. Line range like "50-80".
        grep: Optional. Search pattern. Use + for AND: "revenue+growth".
    """
    import httpx
    params = {k: v for k, v in {"pages": pages, "lines": lines, "grep": grep}.items() if v}
    return httpx.get(f"{MUSEDB}/read/{filename}", params=params).text

def search(query: str, limit: int = 10) -> dict:
    """Full-text search across all uploaded files.

    Args:
        query: Search query. Supports English full-text search and CJK substring matching.
        limit: Max results to return.
    """
    import httpx
    return httpx.post(f"{MUSEDB}/search", json={"query": query, "limit": limit}).json()
```

### OpenAI Function Calling Format

```json
[
  {
    "name": "upload_file",
    "description": "Upload a document to MuseDB. Supports PDF, DOCX, PPTX, XLSX, CSV, TXT, and images.",
    "parameters": {
      "type": "object",
      "properties": {
        "filepath": {"type": "string", "description": "Path to the file to upload"}
      },
      "required": ["filepath"]
    }
  },
  {
    "name": "read_file",
    "description": "Read a file as plain text. Like cat + grep for any file format. Returns plain text, not JSON.",
    "parameters": {
      "type": "object",
      "properties": {
        "filename": {"type": "string", "description": "Filename, partial match, or UUID"},
        "pages": {"type": "string", "description": "Page range: '1-3', '5', or sheet name"},
        "lines": {"type": "string", "description": "Line range: '50-80'"},
        "grep": {"type": "string", "description": "Search pattern. Use + for AND: 'revenue+growth'"}
      },
      "required": ["filename"]
    }
  },
  {
    "name": "search",
    "description": "Full-text search across all uploaded documents. Returns matching snippets with relevance scores.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "Search query"},
        "limit": {"type": "integer", "description": "Max results (default 10)"}
      },
      "required": ["query"]
    }
  }
]
```

---

## Why MuseDB?

Without MuseDB, agents write inline parsing scripts for every file:

```python
# Agent writes this for every PDF — 500+ tokens, often fails
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
| Success rate | 79% (19/24) | **100% (24/24)** |

See [benchmark/REPORT.md](benchmark/REPORT.md) for full methodology.

---

## All Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/files` | `POST` | Upload a file (multipart form) |
| `/files` | `GET` | List files (`?tags=`, `?mime_type=`, `?filename=`) |
| `/files/{id}` | `GET` | Get file metadata |
| `/files/{id}` | `DELETE` | Delete a file |
| `/read/{filename}` | `GET` | Read as plain text (`?pages=`, `?lines=`, `?grep=`, `?toc=`) |
| `/search` | `POST` | Full-text search (`{"query": "...", "limit": 20}`) |
| `/health` | `GET` | Health check |

## Supported Formats

| Format | Extensions | Features |
|--------|-----------|----------|
| PDF | `.pdf` | Pages, tables, OCR for scanned docs, metadata |
| Word | `.docx` | Page breaks, tables, headings, metadata |
| PowerPoint | `.pptx` | Slides, speaker notes, tables, metadata |
| Excel | `.xlsx` | Multiple sheets, column-value formatting |
| CSV | `.csv` | Auto-encoding detection, chunked output |
| Text | `.txt` `.md` `.html` `.json` | Paragraph chunking, heading detection |
| Images | `.png` `.jpg` `.tiff` `.bmp` | OCR via Tesseract (English + Chinese) |

## Configuration

Environment variables with `FILEDB_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `FILEDB_DATABASE_URL` | `postgresql://musedb:musedb@localhost:5432/musedb` | PostgreSQL connection |
| `FILEDB_FILE_STORAGE_PATH` | `./data` | File storage directory |
| `FILEDB_MAX_FILE_SIZE` | `104857600` | Max upload size (100MB) |
| `FILEDB_OCR_ENABLED` | `true` | Enable OCR for images |
| `FILEDB_OCR_LANGUAGES` | `eng+chi_sim+chi_tra` | Tesseract languages |

## Manual Setup

```bash
pip install -e .
createdb musedb && psql musedb < sql/schema.sql
uvicorn app.main:app --reload
```

Requires Python 3.11+, PostgreSQL 16+, Tesseract OCR (optional).

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

[AGPL-3.0](LICENSE) — Source code must be shared when running as a network service.
