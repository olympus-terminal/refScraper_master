#!/usr/bin/env python3
"""
Base Handler
============
Abstract base class for platform-specific citation handlers.
"""

import re
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import sys
sys.path.insert(0, '..')
from ris_converter import RISBuilder

class BaseHandler(ABC):
    """Abstract base class for platform-specific handlers"""

    # Override in subclasses
    DOMAINS: List[str] = []
    RIS_TYPE: str = 'ELEC'

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 Citation Fetcher/1.0',
            'Accept': 'application/json, text/html, */*',
        })

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Check if this handler can process the given URL"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
        return any(d in domain for d in cls.DOMAINS)

    @abstractmethod
    def fetch(self, url: str) -> Optional[str]:
        """
        Fetch and return RIS citation for the given URL.
        Returns None if fetching fails.
        """
        pass

    @abstractmethod
    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """
        Extract metadata from URL.
        Returns standardized metadata dict.
        """
        pass

    def _api_request(self, url: str, params: Optional[Dict] = None,
                     headers: Optional[Dict] = None) -> Optional[Dict]:
        """Make an API request and return JSON response"""
        try:
            req_headers = dict(self.session.headers)
            if headers:
                req_headers.update(headers)

            response = self.session.get(
                url,
                params=params,
                headers=req_headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            print(f"[ERROR] API request failed: {e}")
            return None
        except ValueError as e:
            print(f"[ERROR] JSON parsing failed: {e}")
            return None

    def _fetch_html(self, url: str) -> Optional[str]:
        """Fetch HTML content from URL"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"[ERROR] HTML fetch failed: {e}")
            return None

    def _extract_year(self, date_str: str) -> str:
        """Extract year from date string"""
        if not date_str:
            return ''
        match = re.search(r'\b(19|20)\d{2}\b', date_str)
        return match.group(0) if match else ''

    def _safe_id(self, text: str) -> str:
        """Generate a safe ID from text"""
        safe = re.sub(r'[^a-zA-Z0-9]', '_', text)
        return safe[:50]

    def _build_ris(self, metadata: Dict[str, Any]) -> str:
        """Build RIS string from metadata using RISBuilder"""
        builder = RISBuilder(self.RIS_TYPE)

        # Generate ID
        ref_id = metadata.get('id', '')
        if not ref_id:
            ref_id = self._safe_id(metadata.get('title', 'unknown'))
        builder.set_id(ref_id)

        # Authors
        authors = metadata.get('authors', [])
        if isinstance(authors, str):
            authors = [authors]
        for author in authors:
            builder.add_author(author)

        # Basic fields
        builder.set_title(metadata.get('title', ''))
        builder.set_secondary_title(metadata.get('site_name', ''))
        builder.set_year(metadata.get('year', ''))
        builder.set_date(metadata.get('date', ''))
        builder.set_abstract(metadata.get('description', ''))
        builder.set_url(metadata.get('url', ''))
        builder.set_doi(metadata.get('doi', ''))
        builder.set_publisher(metadata.get('publisher', ''))

        # Keywords
        keywords = metadata.get('keywords', [])
        if keywords:
            builder.set_keywords(keywords)

        # Notes
        if metadata.get('notes'):
            builder.add_note(metadata['notes'])

        # Misc field
        if metadata.get('misc'):
            builder.set_misc(metadata['misc'])

        return builder.build()
