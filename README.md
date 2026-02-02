# Universal Citation Fetcher

Fetch RIS citations from any web URL or academic identifier with a plain text query - like frontier models, but accurate. Automatically extracts metadata from web pages, APIs, and academic databases to generate properly formatted RIS citations for import into reference managers like Endnote and Zotero.

## Features

- **Academic Sources**: PubMed (PMID), CrossRef (DOI), arXiv, bioRxiv/medRxiv, Zenodo, DataCite, NASA Technical Reports
- **Web Platforms**: GitHub, YouTube, Medium, Stack Overflow, Twitter/X, Google properties
- **Generic URLs**: Any web page via metadata extraction (JSON-LD, Open Graph, Dublin Core, HTML meta tags)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Fetch from any URL

```bash
# Single URL
python universal_citation_fetcher.py "https://github.com/google/earthengine-api"

# Batch file (one URL per line)
python universal_citation_fetcher.py urls.txt
```

### Fetch academic citations

```bash
python ris_fetcher_expanded.py citations.txt
```

Input file format:
```
PMID:12345678
DOI:10.1234/example
ARXIV:2311.17179
BIORXIV:10.1101/2023.01.01.123456
ZENODO:10.5281/zenodo.1234567
NASA:20150000001
URL:https://example.com/article
https://github.com/owner/repo
```

## Output

```
web_citations/
  - Individual .ris files
  - bibliography_combined.ris  # Import this into Endnote/Zotero
```

## Supported Platforms

| Platform | Handler | Data Source |
|----------|---------|-------------|
| GitHub | `GitHubHandler` | GitHub API |
| YouTube | `YouTubeHandler` | oEmbed API |
| Medium | `MediumHandler` | Page metadata |
| Stack Overflow | `StackOverflowHandler` | Stack Exchange API |
| Twitter/X | `TwitterHandler` | Page metadata |
| Google (DeepMind, AI, Cloud, Earth Engine) | `GoogleHandler` | Page metadata |
| Any URL | `WebMetadataExtractor` | JSON-LD, Open Graph, Dublin Core |

## RIS Types Generated

| Content Type | RIS Type |
|--------------|----------|
| Journal Article | JOUR |
| Preprint | UNPB |
| Blog Post | BLOG |
| News Article | NEWS |
| Software/Repository | COMP |
| Video | VIDEO |
| Dataset | DATA |
| Web Page | ELEC |
| Report | RPRT |

## Architecture

```
URL/Identifier Input
        |
        v
+------------------+
| Source Detection |
+------------------+
        |
        v
+----------------------------------+
| Platform-Specific Handlers       |
| (GitHub, YouTube, Medium, etc.)  |
+----------------------------------+
        |
        | (fallback)
        v
+----------------------------------+
| Generic Web Metadata Extractor   |
| - JSON-LD (Schema.org)           |
| - Open Graph meta tags           |
| - Twitter Card meta tags         |
| - Dublin Core meta tags          |
| - HTML meta tags                 |
+----------------------------------+
        |
        v
+------------------+
| RIS Converter    |
+------------------+
        |
        v
    .ris Output
```

## Open Access PDF Fetcher

Download PDFs for academic papers using DOIs with multi-source fallback:

```bash
# Single DOI
python open_access_pdf_fetcher.py --doi "10.1038/nature12373" -o paper.pdf

# Batch download from JSON
python open_access_pdf_fetcher.py -i papers.json -d ./pdfs

# Retry failed downloads
python open_access_pdf_fetcher.py -i papers.json -d ./pdfs --retry-failed
```

### PDF Sources (in fallback order)

| Source | Coverage | Notes |
|--------|----------|-------|
| PubMed Central | ~8M papers | NIH-funded, always free |
| Europe PMC | ~9M papers | Includes EU-funded |
| Semantic Scholar | ~200M papers | AI-curated links |
| Unpaywall | Legal OA | Multiple locations per paper |
| Publisher patterns | Major journals | PNAS, Nature, Cell, Frontiers, etc. |
| DOI negotiation | Universal | Content-type based |

### Input JSON format

```json
[
  {"doi": "10.1038/nature12373", "title": "Paper Title", "venue": "Nature"},
  {"doi": "10.1126/science.xxx", "title": "Another Paper", "venue": "Science"}
]
```

## License

MIT
