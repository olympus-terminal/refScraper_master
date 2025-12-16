#!/usr/bin/env python3
"""
Twitter/X Handler
=================
Fetches citation metadata for Twitter/X posts.
Uses meta tag parsing since API requires authentication.
"""

import re
import json
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from .base_handler import BaseHandler

class TwitterHandler(BaseHandler):
    """Handler for Twitter/X URLs"""

    DOMAINS = ['twitter.com', 'x.com', 'mobile.twitter.com']
    RIS_TYPE = 'ELEC'

    def fetch(self, url: str) -> Optional[str]:
        """Fetch RIS citation for Twitter URL"""
        metadata = self.extract_metadata(url)
        if not metadata or metadata.get('error'):
            return None
        return self._build_ris(metadata)

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract metadata from Twitter URL"""
        # Normalize URL
        url = self._normalize_url(url)

        # Parse URL to get username and tweet ID
        username, tweet_id = self._parse_url(url)

        metadata = {
            'url': url,
            'site_name': 'Twitter/X',
            'publisher': 'Twitter/X',
            'content_type': 'social',
        }

        if username:
            metadata['authors'] = [f"@{username}"]

        if tweet_id:
            metadata['id'] = f"Twitter_{tweet_id}"

        # Try to fetch page and extract meta tags
        html = self._fetch_html(url)
        if html:
            soup = BeautifulSoup(html, 'lxml')

            # Extract from meta tags
            og = self._extract_open_graph(soup)
            metadata.update(og)

            # Extract from Twitter-specific tags
            twitter_meta = self._extract_twitter_meta(soup)
            self._merge_metadata(metadata, twitter_meta)

            # Try to parse embedded JSON data
            json_data = self._extract_json_data(html)
            if json_data:
                self._merge_metadata(metadata, json_data)

        # Clean up title (often contains the full tweet text)
        if metadata.get('title'):
            title = metadata['title']
            # Remove "on Twitter/X:" prefix pattern
            title = re.sub(r'^.*?\s+on\s+(Twitter|X):\s*"?', '', title)
            title = re.sub(r'"?\s*$', '', title)
            metadata['title'] = title[:200]  # Truncate long tweets

        # Generate ID if not set
        if not metadata.get('id'):
            if tweet_id:
                metadata['id'] = f"Twitter_{tweet_id}"
            elif username:
                metadata['id'] = f"Twitter_{username}"
            else:
                metadata['id'] = "Twitter_unknown"

        return metadata

    def _normalize_url(self, url: str) -> str:
        """Normalize Twitter URL"""
        # Convert x.com to twitter.com for consistency
        url = url.replace('://x.com/', '://twitter.com/')
        url = url.replace('://mobile.twitter.com/', '://twitter.com/')
        return url

    def _parse_url(self, url: str) -> tuple:
        """Parse URL to extract username and tweet ID"""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        parts = path.split('/')

        username = None
        tweet_id = None

        if len(parts) >= 1:
            username = parts[0]

        if len(parts) >= 3 and parts[1] == 'status':
            tweet_id = parts[2]

        return username, tweet_id

    def _merge_metadata(self, base: Dict, update: Dict) -> None:
        """Merge update into base, only filling empty fields"""
        for key, value in update.items():
            if key not in base or not base[key]:
                base[key] = value

    def _extract_open_graph(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Open Graph meta tags"""
        metadata = {}

        og_mappings = {
            'og:title': 'title',
            'og:description': 'description',
            'og:url': 'canonical_url',
            'og:site_name': 'site_name',
        }

        for og_prop, field in og_mappings.items():
            tag = soup.find('meta', property=og_prop)
            if tag and tag.get('content'):
                metadata[field] = tag['content'].strip()

        return metadata

    def _extract_twitter_meta(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Twitter-specific meta tags"""
        metadata = {}

        twitter_mappings = {
            'twitter:title': 'title',
            'twitter:description': 'description',
            'twitter:creator': 'twitter_creator',
            'twitter:site': 'twitter_site',
        }

        for tw_name, field in twitter_mappings.items():
            tag = soup.find('meta', attrs={'name': tw_name})
            if not tag:
                tag = soup.find('meta', attrs={'property': tw_name})
            if tag and tag.get('content'):
                content = tag['content'].strip()
                if field == 'twitter_creator' and content.startswith('@'):
                    metadata['authors'] = [content]
                else:
                    metadata[field] = content

        return metadata

    def _extract_json_data(self, html: str) -> Dict[str, Any]:
        """Try to extract embedded JSON data"""
        metadata = {}

        # Look for JSON-LD
        ld_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
        matches = re.findall(ld_pattern, html, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, list):
                    data = data[0] if data else {}

                if data.get('datePublished'):
                    metadata['date'] = data['datePublished'][:10]
                    metadata['year'] = data['datePublished'][:4]

                if data.get('author'):
                    author = data['author']
                    if isinstance(author, dict):
                        name = author.get('name') or author.get('identifier')
                        if name:
                            metadata['authors'] = [name]
                    elif isinstance(author, str):
                        metadata['authors'] = [author]

            except (json.JSONDecodeError, TypeError):
                continue

        return metadata

    def _build_ris(self, metadata: Dict[str, Any]) -> str:
        """Build RIS with Twitter-specific formatting"""
        from ris_converter import RISBuilder

        builder = RISBuilder('ELEC')

        builder.set_id(metadata.get('id', 'Twitter'))

        # Authors
        authors = metadata.get('authors', [])
        if isinstance(authors, str):
            authors = [authors]
        for author in authors:
            builder.add_author(author)

        # Title (tweet text, truncated)
        title = metadata.get('title', '')
        if len(title) > 100:
            title = title[:97] + '...'
        builder.set_title(title)

        builder.set_secondary_title('Twitter/X')
        builder.set_year(metadata.get('year', ''))
        builder.set_date(metadata.get('date', ''))

        # Use full tweet as abstract if available
        if metadata.get('description'):
            builder.set_abstract(metadata['description'])

        builder.set_url(metadata.get('url', ''))
        builder.set_publisher('Twitter/X')

        return builder.build()
