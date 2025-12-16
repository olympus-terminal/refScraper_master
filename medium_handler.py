#!/usr/bin/env python3
"""
Medium Handler
==============
Fetches citation metadata for Medium articles and publications.
Uses meta tags and embedded JSON data.
"""

import re
import json
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from .base_handler import BaseHandler

class MediumHandler(BaseHandler):
    """Handler for Medium URLs"""

    DOMAINS = [
        'medium.com',
        'towardsdatascience.com',
        'betterprogramming.pub',
        'levelup.gitconnected.com',
        'blog.devgenius.io',
        'javascript.plainenglish.io',
        'aws.plainenglish.io',
        'python.plainenglish.io',
    ]

    RIS_TYPE = 'BLOG'

    def fetch(self, url: str) -> Optional[str]:
        """Fetch RIS citation for Medium URL"""
        metadata = self.extract_metadata(url)
        if not metadata or metadata.get('error'):
            return None
        return self._build_ris(metadata)

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract metadata from Medium URL"""
        html = self._fetch_html(url)
        if not html:
            return {'error': 'Failed to fetch page', 'url': url}

        soup = BeautifulSoup(html, 'lxml')

        metadata = {
            'url': url,
            'site_name': 'Medium',
            'content_type': 'blog',
        }

        # Try to extract from embedded Apollo state (Medium's internal data)
        apollo = self._extract_apollo_state(html)
        if apollo:
            metadata.update(apollo)

        # Extract from JSON-LD
        json_ld = self._extract_json_ld(soup)
        self._merge_metadata(metadata, json_ld)

        # Extract from Open Graph
        og = self._extract_open_graph(soup)
        self._merge_metadata(metadata, og)

        # Extract from standard meta
        html_meta = self._extract_html_meta(soup)
        self._merge_metadata(metadata, html_meta)

        # Get publication name from URL or meta
        publication = self._extract_publication(url, soup)
        if publication:
            metadata['site_name'] = publication

        # Generate ID
        metadata['id'] = self._generate_id(url, metadata)

        # Extract year
        if metadata.get('date'):
            metadata['year'] = self._extract_year(metadata['date'])

        return metadata

    def _merge_metadata(self, base: Dict, update: Dict) -> None:
        """Merge update into base, only filling empty fields"""
        for key, value in update.items():
            if key not in base or not base[key]:
                base[key] = value

    def _extract_apollo_state(self, html: str) -> Dict[str, Any]:
        """Extract data from Medium's Apollo state"""
        metadata = {}

        # Look for window.__APOLLO_STATE__ or similar
        patterns = [
            r'window\.__APOLLO_STATE__\s*=\s*({.*?});',
            r'"apolloState"\s*:\s*({.*?})\s*[,}]',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    # Parse the Apollo state structure
                    metadata.update(self._parse_apollo_data(data))
                    break
                except json.JSONDecodeError:
                    continue

        return metadata

    def _parse_apollo_data(self, data: Dict) -> Dict[str, Any]:
        """Parse Apollo state data structure"""
        metadata = {}

        # Medium stores data in a flat structure with references
        for key, value in data.items():
            if not isinstance(value, dict):
                continue

            # Look for Post type
            if value.get('__typename') == 'Post':
                if value.get('title'):
                    metadata['title'] = value['title']
                if value.get('previewContent', {}).get('subtitle'):
                    metadata['description'] = value['previewContent']['subtitle']
                if value.get('firstPublishedAt'):
                    # Convert timestamp to date
                    ts = value['firstPublishedAt']
                    if isinstance(ts, int):
                        from datetime import datetime
                        dt = datetime.fromtimestamp(ts / 1000)
                        metadata['date'] = dt.strftime('%Y-%m-%d')

            # Look for User type (author)
            if value.get('__typename') == 'User':
                if value.get('name'):
                    if 'authors' not in metadata:
                        metadata['authors'] = []
                    metadata['authors'].append(value['name'])

        return metadata

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract JSON-LD data"""
        metadata = {}

        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    data = data[0] if data else {}

                if data.get('headline'):
                    metadata['title'] = data['headline']
                if data.get('description'):
                    metadata['description'] = data['description']
                if data.get('datePublished'):
                    metadata['date'] = data['datePublished'][:10]

                # Author
                author = data.get('author', {})
                if isinstance(author, dict) and author.get('name'):
                    metadata['authors'] = [author['name']]
                elif isinstance(author, list):
                    metadata['authors'] = [a.get('name', '') for a in author if a.get('name')]

                # Publisher
                publisher = data.get('publisher', {})
                if isinstance(publisher, dict) and publisher.get('name'):
                    metadata['publisher'] = publisher['name']

            except (json.JSONDecodeError, TypeError):
                continue

        return metadata

    def _extract_open_graph(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Open Graph meta tags"""
        metadata = {}

        og_mappings = {
            'og:title': 'title',
            'og:description': 'description',
            'og:url': 'canonical_url',
            'og:site_name': 'publication',
            'article:published_time': 'date',
            'article:author': 'author_url',
        }

        for og_prop, field in og_mappings.items():
            tag = soup.find('meta', property=og_prop)
            if tag and tag.get('content'):
                metadata[field] = tag['content'].strip()
                if field == 'date':
                    metadata['date'] = metadata['date'][:10]

        return metadata

    def _extract_html_meta(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract standard HTML meta tags"""
        metadata = {}

        # Title
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            # Remove " | Medium" suffix
            if ' | Medium' in title:
                title = title.rsplit(' | Medium', 1)[0]
            if ' - Medium' in title:
                title = title.rsplit(' - Medium', 1)[0]
            metadata['title'] = title

        # Author meta
        author_tag = soup.find('meta', attrs={'name': 'author'})
        if author_tag and author_tag.get('content'):
            metadata['authors'] = [author_tag['content']]

        # Look for author in page content
        author_link = soup.find('a', attrs={'rel': 'author'})
        if author_link:
            author_name = author_link.get_text().strip()
            if author_name:
                metadata['authors'] = [author_name]

        return metadata

    def _extract_publication(self, url: str, soup: BeautifulSoup) -> Optional[str]:
        """Extract publication name"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check for known publications
        publication_map = {
            'towardsdatascience.com': 'Towards Data Science',
            'betterprogramming.pub': 'Better Programming',
            'levelup.gitconnected.com': 'Level Up Coding',
            'blog.devgenius.io': 'Dev Genius',
            'javascript.plainenglish.io': 'JavaScript in Plain English',
            'python.plainenglish.io': 'Python in Plain English',
        }

        if domain in publication_map:
            return publication_map[domain]

        # For medium.com URLs, look for publication in path
        if 'medium.com' in domain:
            path_parts = parsed.path.strip('/').split('/')
            if path_parts and path_parts[0].startswith('@'):
                # Personal blog: medium.com/@username/...
                return f"Medium - {path_parts[0]}"
            elif path_parts and not path_parts[0].startswith('p'):
                # Publication: medium.com/publication-name/...
                pub_name = path_parts[0].replace('-', ' ').title()
                return pub_name

        return 'Medium'

    def _generate_id(self, url: str, metadata: Dict) -> str:
        """Generate a unique ID"""
        parsed = urlparse(url)
        # Medium article IDs are in the URL
        path = parsed.path.strip('/')
        parts = path.split('-')
        if parts:
            # Last part is often the article ID
            article_id = parts[-1][:12]
            return f"Medium_{article_id}"
        return f"Medium_{self._safe_id(metadata.get('title', 'unknown'))}"

    def _build_ris(self, metadata: Dict[str, Any]) -> str:
        """Build RIS with Medium-specific formatting"""
        from ris_converter import RISBuilder

        builder = RISBuilder('BLOG')

        builder.set_id(metadata.get('id', 'Medium'))

        # Authors
        for author in metadata.get('authors', []):
            builder.add_author(author)

        builder.set_title(metadata.get('title', ''))
        builder.set_secondary_title(metadata.get('site_name', 'Medium'))
        builder.set_year(metadata.get('year', ''))
        builder.set_date(metadata.get('date', ''))
        builder.set_abstract(metadata.get('description', ''))
        builder.set_url(metadata.get('url', ''))
        builder.set_publisher('Medium')

        if metadata.get('keywords'):
            builder.set_keywords(metadata['keywords'])

        return builder.build()
