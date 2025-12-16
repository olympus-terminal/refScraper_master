#!/usr/bin/env python3
"""
Universal Citation Fetcher
==========================
Fetches RIS citations from any web URL using platform-specific handlers
and a generic metadata extractor as fallback.

Supported platforms:
- GitHub (repositories, gists, issues, PRs)
- YouTube (videos)
- Medium (articles)
- Stack Overflow (questions, answers)
- Twitter/X (posts)
- Google properties (DeepMind, AI, Cloud, Earth Engine)

For all other URLs, uses generic metadata extraction from:
- JSON-LD (Schema.org)
- Open Graph meta tags
- Twitter Card meta tags
- Dublin Core meta tags
- Standard HTML meta tags

Usage:
    python universal_citation_fetcher.py <input_file>

Input format (one URL per line):
    https://github.com/owner/repo
    https://deepmind.google/blog/post-name/
    URL:https://example.com/article

Output:
    Individual .ris files + combined bibliography.ris

Date: 2024-12-13
"""

import sys
import time
import requests
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from urllib.parse import urlparse

# Import handlers
from handlers import (
    GitHubHandler,
    YouTubeHandler,
    MediumHandler,
    StackOverflowHandler,
    TwitterHandler,
    GoogleHandler,
)

# Import generic extractor and converter
from web_metadata_extractor import WebMetadataExtractor
from ris_converter import RISConverter

class UniversalCitationFetcher:
    """Fetch RIS citations from any web URL"""

    def __init__(self, output_dir: str = "web_citations"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Shared session for all requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 Citation Fetcher/2.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })

        # Initialize handlers with shared session
        self.handlers = [
            GitHubHandler(self.session),
            YouTubeHandler(self.session),
            MediumHandler(self.session),
            StackOverflowHandler(self.session),
            TwitterHandler(self.session),
            GoogleHandler(self.session),
        ]

        # Generic fallback
        self.generic_extractor = WebMetadataExtractor(self.session)
        self.ris_converter = RISConverter()

    def fetch_citation(self, url: str) -> Tuple[str, Optional[str]]:
        """
        Fetch RIS citation for a URL.

        Args:
            url: The URL to fetch citation for

        Returns:
            Tuple of (safe_filename, ris_content) or (safe_filename, None) on failure
        """
        # Clean URL
        url = url.strip()
        if url.startswith('URL:'):
            url = url[4:].strip()

        # Ensure URL has scheme
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url

        print(f"[FETCHING] {url[:70]}...")

        # Try platform-specific handlers first
        for handler in self.handlers:
            if handler.can_handle(url):
                handler_name = handler.__class__.__name__
                print(f"  Using {handler_name}")
                ris = handler.fetch(url)
                if ris:
                    filename = self._generate_filename(url)
                    return filename, ris
                else:
                    print(f"  {handler_name} failed, trying generic extractor")
                    break

        # Fall back to generic extraction
        print(f"  Using generic extractor")
        metadata = self.generic_extractor.extract(url)

        if metadata and not metadata.get('error'):
            ris = self.ris_converter.convert(metadata)
            filename = self._generate_filename(url)
            return filename, ris

        # Failed
        filename = self._generate_filename(url)
        return filename, None

    def _generate_filename(self, url: str) -> str:
        """Generate safe filename from URL"""
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '').replace('.', '_')
        path = parsed.path.strip('/').replace('/', '_')[:50]
        safe = f"{domain}_{path}".replace('-', '_')
        # Remove any remaining unsafe characters
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe)
        return f"WEB_{safe}"

    def process_batch(self, input_file: str) -> None:
        """
        Process a batch of URLs from input file.

        Args:
            input_file: Path to file containing URLs (one per line)
        """
        input_path = Path(input_file)
        if not input_path.exists():
            print(f"[ERROR] Input file not found: {input_file}")
            return

        # Read URLs
        with open(input_path, 'r') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        # Filter to only URLs
        urls = [line for line in lines if
                line.startswith('http://') or
                line.startswith('https://') or
                line.startswith('URL:')]

        if not urls:
            print(f"[ERROR] No URLs found in {input_file}")
            return

        print(f"\n{'='*70}")
        print(f"UNIVERSAL CITATION FETCHER")
        print(f"{'='*70}")
        print(f"Input file: {input_file}")
        print(f"URLs to process: {len(urls)}")
        print(f"Output directory: {self.output_dir}")
        print(f"{'='*70}\n")

        combined_ris = []
        success_count = 0
        failed = []

        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] ", end='')

            filename, ris_content = self.fetch_citation(url)

            if ris_content:
                # Save individual file
                output_file = self.output_dir / f"{filename}.ris"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(ris_content)

                combined_ris.append(ris_content)
                success_count += 1
                print(f"  [SUCCESS] Saved: {output_file.name}")
            else:
                failed.append(url)
                print(f"  [FAILED] Could not fetch citation")

            # Rate limiting
            if i < len(urls):
                time.sleep(0.5)

        # Save combined bibliography
        if combined_ris:
            combined_file = self.output_dir / "bibliography_combined.ris"
            with open(combined_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(combined_ris))

            print(f"\n{'='*70}")
            print(f"[COMBINED] Combined bibliography: {combined_file}")
            print(f"{'='*70}")

        # Summary
        print(f"\n{'='*70}")
        print(f"SUMMARY")
        print(f"{'='*70}")
        print(f"[SUCCESS] Successfully fetched: {success_count}/{len(urls)}")

        if failed:
            print(f"[FAILED] Failed: {len(failed)}")
            for url in failed:
                print(f"   - {url[:60]}...")

        print(f"\n[INFO] Import {self.output_dir}/bibliography_combined.ris into Endnote/Zotero")
        print(f"{'='*70}\n")

    def fetch_single(self, url: str) -> Optional[str]:
        """
        Fetch a single URL and return RIS content.

        Args:
            url: The URL to fetch

        Returns:
            RIS content string or None
        """
        _, ris = self.fetch_citation(url)
        return ris

def main():
    """Main entry point"""

    if len(sys.argv) < 2:
        print("""
Universal Citation Fetcher
==========================

Fetches RIS citations from any web URL.

Usage:
    python universal_citation_fetcher.py <input_file>
    python universal_citation_fetcher.py <url>

Input file format (one URL per line):
    https://github.com/owner/repo
    https://deepmind.google/blog/post-name/
    https://www.youtube.com/watch?v=xxxxx
    URL:https://example.com/article

Supported platforms:
    - GitHub (repositories, gists, issues, PRs)
    - YouTube (videos)
    - Medium (articles)
    - Stack Overflow (questions, answers)
    - Twitter/X (posts)
    - Google properties (DeepMind, AI, Cloud, Earth Engine)
    - Any other URL (generic metadata extraction)

Output:
    web_citations/
      - Individual .ris files
      - bibliography_combined.ris

Examples:
    python universal_citation_fetcher.py urls.txt
    python universal_citation_fetcher.py "https://github.com/google/earthengine-api"
        """)
        sys.exit(1)

    arg = sys.argv[1]

    # Check if argument is a URL or a file
    if arg.startswith('http://') or arg.startswith('https://'):
        # Single URL
        fetcher = UniversalCitationFetcher()
        ris = fetcher.fetch_single(arg)
        if ris:
            print("\n" + ris)
        else:
            print("[ERROR] Failed to fetch citation")
            sys.exit(1)
    else:
        # File
        fetcher = UniversalCitationFetcher()
        fetcher.process_batch(arg)

if __name__ == "__main__":
    main()
