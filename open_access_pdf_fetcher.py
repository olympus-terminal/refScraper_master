#!/usr/bin/env python3
"""
Open Access PDF Fetcher - Multi-source academic paper downloader

Downloads open access PDFs using multiple fallback strategies:
1. PubMed Central (PMC) - NIH free archive
2. Europe PMC - European mirror with additional content
3. Semantic Scholar - AI-curated PDF links
4. Unpaywall - Legal OA location finder
5. Publisher-specific patterns - Direct PDF URLs
6. DOI content negotiation - Standard resolution

Supports downloading from DOIs, with automatic source discovery and
fallback chains to maximize retrieval success.

Usage:
    # Download single paper by DOI
    python open_access_pdf_fetcher.py --doi "10.1038/nature12373" --output paper.pdf

    # Batch download from JSON file
    python open_access_pdf_fetcher.py --input papers.json --output-dir pdfs/

    # Retry failed downloads
    python open_access_pdf_fetcher.py --input papers.json --output-dir pdfs/ --retry-failed

Input JSON format:
    [
        {"doi": "10.1038/xxx", "title": "Paper Title", "venue": "Nature"},
        ...
    ]

Requirements:
    pip install requests

Author: olympus-terminal
License: MIT
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
import argparse

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)

# ============================================================================
# Configuration
# ============================================================================

# Rate limiting (be respectful to APIs)
REQUEST_DELAY = 1.5  # seconds between API requests
DOWNLOAD_DELAY = 2.0  # seconds between PDF downloads

# Browser-like headers for better compatibility
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

PDF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ============================================================================
# PDF Downloader Class
# ============================================================================

class OpenAccessPDFFetcher:
    """
    Multi-source PDF fetcher with fallback strategies.

    Tries multiple sources in order of reliability:
    1. PMC (PubMed Central)
    2. Europe PMC
    3. Publisher direct URLs
    4. Semantic Scholar
    5. Unpaywall locations
    6. DOI content negotiation
    """

    def __init__(self, email: str = "researcher@example.edu", verbose: bool = True):
        """
        Initialize the fetcher.

        Args:
            email: Email for API identification (helps with rate limits)
            verbose: Print progress messages
        """
        self.email = email
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)

    def log(self, message: str):
        """Print message if verbose mode is enabled."""
        if self.verbose:
            print(message)

    # ------------------------------------------------------------------------
    # Source: PubMed Central (PMC)
    # ------------------------------------------------------------------------

    def get_pmcid_from_doi(self, doi: str) -> Optional[str]:
        """Look up PMCID from DOI using NCBI ID converter."""
        url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        params = {
            "ids": doi,
            "format": "json",
            "tool": "open_access_pdf_fetcher",
            "email": self.email
        }
        try:
            resp = self.session.get(url, params=params, timeout=30)
            data = resp.json()
            records = data.get("records", [])
            if records and records[0].get("pmcid"):
                return records[0]["pmcid"]
        except Exception as e:
            self.log(f"    PMC lookup error: {e}")
        return None

    def try_pmc(self, doi: str) -> Optional[str]:
        """Try to get PDF URL from PubMed Central."""
        pmcid = self.get_pmcid_from_doi(doi)
        if pmcid:
            return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
        return None

    # ------------------------------------------------------------------------
    # Source: Europe PMC
    # ------------------------------------------------------------------------

    def try_europe_pmc(self, doi: str) -> Optional[str]:
        """Try Europe PMC for PDF URL."""
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            "query": f'DOI:"{doi}"',
            "format": "json",
            "resultType": "core"
        }
        try:
            resp = self.session.get(url, params=params, timeout=30)
            data = resp.json()
            results = data.get("resultList", {}).get("result", [])
            if results:
                pmcid = results[0].get("pmcid")
                if pmcid:
                    return f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
        except Exception as e:
            self.log(f"    Europe PMC error: {e}")
        return None

    # ------------------------------------------------------------------------
    # Source: Semantic Scholar
    # ------------------------------------------------------------------------

    def try_semantic_scholar(self, doi: str) -> Optional[str]:
        """Try Semantic Scholar for PDF URL."""
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        params = {"fields": "openAccessPdf"}
        try:
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                oa_pdf = data.get("openAccessPdf")
                if oa_pdf and oa_pdf.get("url"):
                    return oa_pdf["url"]
        except Exception as e:
            self.log(f"    Semantic Scholar error: {e}")
        return None

    # ------------------------------------------------------------------------
    # Source: Unpaywall
    # ------------------------------------------------------------------------

    def try_unpaywall(self, doi: str) -> List[str]:
        """Get all OA locations from Unpaywall."""
        url = f"https://api.unpaywall.org/v2/{doi}"
        params = {"email": self.email}
        urls = []
        try:
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for loc in data.get("oa_locations", []):
                    if loc.get("url_for_pdf"):
                        urls.append(loc["url_for_pdf"])
                    elif loc.get("url"):
                        urls.append(loc["url"])
        except Exception:
            pass
        return urls

    # ------------------------------------------------------------------------
    # Source: DOI Content Negotiation
    # ------------------------------------------------------------------------

    def try_doi_negotiation(self, doi: str) -> Optional[str]:
        """Use DOI content negotiation to request PDF directly."""
        url = f"https://doi.org/{doi}"
        headers = {
            "Accept": "application/pdf",
            "User-Agent": BROWSER_HEADERS["User-Agent"]
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=30, allow_redirects=True)
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                if "pdf" in content_type.lower():
                    return resp.url
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------------
    # Source: Publisher-specific patterns
    # ------------------------------------------------------------------------

    def get_publisher_url(self, doi: str, venue: str = "") -> Optional[str]:
        """Generate direct PDF URL based on known publisher patterns."""
        doi_lower = doi.lower()
        venue_lower = venue.lower()

        # PNAS
        if "pnas" in venue_lower or "10.1073/pnas" in doi_lower:
            return f"https://www.pnas.org/doi/pdf/{doi}"

        # Science/AAAS
        if "science" in venue_lower and "10.1126" in doi:
            return f"https://www.science.org/doi/pdf/{doi}"

        # Nature journals
        if "nature" in venue_lower and "10.1038" in doi:
            match = re.search(r'10\.1038/([a-z0-9-]+)', doi)
            if match:
                return f"https://www.nature.com/articles/{match.group(1)}.pdf"

        # Cell Press
        if "cell" in venue_lower and "10.1016/j.cell" in doi:
            return f"https://www.cell.com/cell/pdf/{doi.replace('10.1016/j.cell.', 'S0092-8674')}.pdf"

        # ISME Journal
        if "isme" in venue_lower and "10.1038" in doi:
            match = re.search(r'10\.1038/([a-z0-9-]+)', doi)
            if match:
                return f"https://www.nature.com/articles/{match.group(1)}.pdf"

        # PLoS
        if "plos" in venue_lower:
            return f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable"

        # Frontiers
        if "frontiers" in venue_lower:
            return f"https://www.frontiersin.org/articles/{doi}/pdf"

        # Scientific Reports
        if "scientific reports" in venue_lower and "10.1038" in doi:
            match = re.search(r'10\.1038/([a-z0-9-]+)', doi)
            if match:
                return f"https://www.nature.com/articles/{match.group(1)}.pdf"

        # BMC
        if "bmc" in venue_lower:
            return f"https://link.springer.com/content/pdf/{doi}.pdf"

        # eLife
        if "elife" in venue_lower:
            match = re.search(r'10\.7554/eLife\.(\d+)', doi)
            if match:
                article_id = match.group(1)
                return f"https://elifesciences.org/articles/{article_id}"

        # Wiley
        if "10.1111/" in doi or "10.1002/" in doi:
            return f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi}"

        return None

    # ------------------------------------------------------------------------
    # PDF Download
    # ------------------------------------------------------------------------

    def download_pdf(self, url: str, output_path: Path, referer: str = None) -> bool:
        """
        Download PDF from URL with validation.

        Args:
            url: URL to download from
            output_path: Where to save the PDF
            referer: Optional referer header

        Returns:
            True if successful, False otherwise
        """
        headers = PDF_HEADERS.copy()
        if referer:
            headers["Referer"] = referer

        try:
            resp = self.session.get(url, headers=headers, timeout=60, stream=True, allow_redirects=True)

            if resp.status_code == 200:
                # Read first bytes to verify PDF magic number
                first_bytes = b""
                for chunk in resp.iter_content(chunk_size=1024):
                    first_bytes += chunk
                    if len(first_bytes) >= 1024:
                        break

                if first_bytes.startswith(b'%PDF'):
                    # Valid PDF, save it
                    with open(output_path, 'wb') as f:
                        f.write(first_bytes)
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)

                    # Verify minimum file size
                    if output_path.stat().st_size > 10000:
                        return True
                    else:
                        output_path.unlink()

        except Exception as e:
            self.log(f"    Download error: {e}")
            if output_path.exists():
                output_path.unlink()

        return False

    # ------------------------------------------------------------------------
    # Main Fetch Method
    # ------------------------------------------------------------------------

    def fetch(self, doi: str, output_path: Path, venue: str = "",
              existing_url: str = None) -> Dict[str, Any]:
        """
        Attempt to download PDF using all available strategies.

        Args:
            doi: DOI of the paper
            output_path: Where to save the PDF
            venue: Journal/venue name (helps with publisher patterns)
            existing_url: Previously known URL to try as fallback

        Returns:
            Dict with 'success', 'source', and 'path' keys
        """
        result = {"success": False, "source": None, "path": None}

        if not doi:
            self.log("  No DOI provided")
            return result

        if output_path.exists() and output_path.stat().st_size > 10000:
            self.log("  Already downloaded")
            result["success"] = True
            result["source"] = "cached"
            result["path"] = str(output_path)
            return result

        strategies = [
            ("PMC", lambda: self.try_pmc(doi), "https://www.ncbi.nlm.nih.gov"),
            ("Europe PMC", lambda: self.try_europe_pmc(doi), "https://europepmc.org"),
            ("Publisher", lambda: self.get_publisher_url(doi, venue), None),
            ("Semantic Scholar", lambda: self.try_semantic_scholar(doi), None),
            ("Unpaywall", lambda: self.try_unpaywall(doi), None),
            ("DOI negotiation", lambda: self.try_doi_negotiation(doi), None),
        ]

        for name, get_url, referer in strategies:
            self.log(f"  Trying {name}...")

            urls = get_url()
            if urls is None:
                continue

            # Handle single URL or list of URLs
            if isinstance(urls, str):
                urls = [urls]

            for url in urls[:5]:  # Try up to 5 URLs per source
                self.log(f"    URL: {url[:70]}...")
                if self.download_pdf(url, output_path, referer):
                    self.log(f"  SUCCESS via {name}!")
                    result["success"] = True
                    result["source"] = name
                    result["path"] = str(output_path)
                    return result

            time.sleep(REQUEST_DELAY)

        # Try existing URL as last resort
        if existing_url:
            self.log(f"  Trying existing URL: {existing_url[:60]}...")
            if self.download_pdf(existing_url, output_path):
                self.log("  SUCCESS via existing URL!")
                result["success"] = True
                result["source"] = "existing"
                result["path"] = str(output_path)
                return result

        self.log("  FAILED - No source worked")
        return result

# ============================================================================
# CLI Interface
# ============================================================================

def sanitize_filename(title: str, max_length: int = 80) -> str:
    """Create safe filename from title."""
    safe = re.sub(r'[^\w\s-]', '', title)
    safe = re.sub(r'\s+', '_', safe)
    return safe[:max_length]

def main():
    parser = argparse.ArgumentParser(
        description="Download open access PDFs from DOIs using multiple sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single DOI
  python open_access_pdf_fetcher.py --doi "10.1038/nature12373" --output paper.pdf

  # Batch from JSON
  python open_access_pdf_fetcher.py --input papers.json --output-dir ./pdfs

  # Retry failed downloads
  python open_access_pdf_fetcher.py --input papers.json --output-dir ./pdfs --retry-failed

Input JSON format:
  [{"doi": "10.1038/xxx", "title": "Title", "venue": "Nature"}, ...]
        """
    )

    parser.add_argument("--doi", help="Single DOI to download")
    parser.add_argument("--output", "-o", help="Output path for single DOI")
    parser.add_argument("--input", "-i", help="Input JSON file with paper list")
    parser.add_argument("--output-dir", "-d", default="pdfs", help="Output directory for batch")
    parser.add_argument("--retry-failed", action="store_true", help="Only retry failed papers")
    parser.add_argument("--limit", type=int, help="Limit number of papers to process")
    parser.add_argument("--email", default="researcher@example.edu",
                        help="Email for API identification")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")

    args = parser.parse_args()

    fetcher = OpenAccessPDFFetcher(email=args.email, verbose=not args.quiet)

    # Single DOI mode
    if args.doi:
        output = Path(args.output or f"{sanitize_filename(args.doi)}.pdf")
        result = fetcher.fetch(args.doi, output)
        if result["success"]:
            print(f"Downloaded: {result['path']} (source: {result['source']})")
            sys.exit(0)
        else:
            print("Failed to download PDF")
            sys.exit(1)

    # Batch mode
    if not args.input:
        parser.print_help()
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path) as f:
        papers = json.load(f)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Filter papers
    if args.retry_failed:
        papers_to_process = [p for p in papers if not p.get("downloaded") and p.get("doi")]
    else:
        papers_to_process = [p for p in papers if p.get("doi")]

    if args.limit:
        papers_to_process = papers_to_process[:args.limit]

    print(f"Processing {len(papers_to_process)} papers...")

    success = 0
    failed = 0

    for i, paper in enumerate(papers_to_process, 1):
        doi = paper.get("doi")
        title = paper.get("title", "unknown")[:60]
        venue = paper.get("venue", "")

        print(f"\n[{i}/{len(papers_to_process)}] {title}...")

        # Generate filename
        paper_id = paper.get("id", i)
        filename = f"{paper_id:03d}_{sanitize_filename(title)}.pdf"
        output_path = output_dir / filename

        result = fetcher.fetch(
            doi=doi,
            output_path=output_path,
            venue=venue,
            existing_url=paper.get("pdf_url")
        )

        if result["success"]:
            paper["downloaded"] = True
            paper["pdf_path"] = result["path"]
            paper["download_source"] = result["source"]
            success += 1
        else:
            failed += 1

        # Save progress
        with open(input_path, 'w') as f:
            json.dump(papers, f, indent=2)

        time.sleep(DOWNLOAD_DELAY)

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    total_downloaded = sum(1 for p in papers if p.get("downloaded"))
    print(f"This run: {success} succeeded, {failed} failed")
    print(f"Total downloaded: {total_downloaded}/{len(papers)} ({100*total_downloaded/len(papers):.1f}%)")

    # Source breakdown
    sources = {}
    for p in papers:
        if p.get("downloaded"):
            src = p.get("download_source", "unknown")
            sources[src] = sources.get(src, 0) + 1

    if sources:
        print("\nBy source:")
        for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"  {src}: {cnt}")

    print("="*60)

if __name__ == "__main__":
    main()
