#!/usr/bin/env python3
"""
Google Handler
==============
Fetches citation metadata for Google properties:
- blog.google
- deepmind.google
- ai.google
- cloud.google.com
- developers.google.com
- colab.research.google.com
- Google Earth Engine documentation

Uses Open Graph metadata and page-specific parsing.
"""

import re
import json
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from .base_handler import BaseHandler

class GoogleHandler(BaseHandler):
    """Handler for Google property URLs"""

    DOMAINS = [
        'google.com',
        'google.co.uk',
        'deepmind.google',
        'deepmind.com',
        'blog.google',
        'ai.google',
        'cloud.google.com',
        'developers.google.com',
        'colab.research.google.com',
        'earthengine.google.com',
        'source.coop',  # Source Cooperative (Google Earth data)
    ]

    RIS_TYPE = 'ELEC'  # Electronic resource (will be BLOG for blog posts)

    def fetch(self, url: str) -> Optional[str]:
        """Fetch RIS citation for Google URL"""
        metadata = self.extract_metadata(url)
        if not metadata or metadata.get('error'):
            return None
        return self._build_ris(metadata)

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract metadata from Google URL"""
        html = self._fetch_html(url)
        if not html:
            return {'error': 'Failed to fetch page', 'url': url}

        soup = BeautifulSoup(html, 'lxml')
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Base metadata
        metadata = {
            'url': url,
            'site_name': self._get_site_name(domain),
            'publisher': 'Google',
        }

        # Extract from JSON-LD first (highest quality)
        json_ld = self._extract_json_ld(soup)
        if json_ld:
            metadata.update(json_ld)

        # Extract from Open Graph
        og = self._extract_open_graph(soup)
        self._merge_metadata(metadata, og)

        # Extract from standard HTML
        html_meta = self._extract_html_meta(soup)
        self._merge_metadata(metadata, html_meta)

        # Domain-specific extraction
        if 'deepmind' in domain:
            dm = self._extract_deepmind(soup, url)
            self._merge_metadata(metadata, dm)
        elif 'blog.google' in domain:
            blog = self._extract_google_blog(soup)
            self._merge_metadata(metadata, blog)
        elif 'earthengine' in domain or 'earth-engine' in parsed.path:
            ee = self._extract_earth_engine(soup, url)
            self._merge_metadata(metadata, ee)
        elif 'source.coop' in domain:
            sc = self._extract_source_coop(soup, url)
            self._merge_metadata(metadata, sc)

        # Generate ID
        metadata['id'] = self._generate_id(url, metadata)

        # Determine content type
        if '/blog/' in url or 'blog.' in domain:
            metadata['content_type'] = 'blog'
        elif '/docs/' in url or '/documentation/' in url:
            metadata['content_type'] = 'documentation'
        else:
            metadata['content_type'] = metadata.get('content_type', 'webpage')

        # Extract year
        if metadata.get('date_published'):
            metadata['year'] = self._extract_year(metadata['date_published'])
        elif metadata.get('date'):
            metadata['year'] = self._extract_year(metadata['date'])

        return metadata

    def _merge_metadata(self, base: Dict, update: Dict) -> None:
        """Merge update into base, only filling empty fields"""
        for key, value in update.items():
            if key not in base or not base[key]:
                base[key] = value

    def _get_site_name(self, domain: str) -> str:
        """Get human-readable site name from domain"""
        if 'deepmind' in domain:
            return 'Google DeepMind'
        elif 'blog.google' in domain:
            return 'Google Blog'
        elif 'ai.google' in domain:
            return 'Google AI'
        elif 'cloud.google' in domain:
            return 'Google Cloud'
        elif 'developers.google' in domain:
            return 'Google Developers'
        elif 'earthengine' in domain:
            return 'Google Earth Engine'
        elif 'source.coop' in domain:
            return 'Source Cooperative'
        else:
            return 'Google'

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Schema.org JSON-LD structured data"""
        metadata = {}

        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)

                if isinstance(data, list):
                    for item in data:
                        self._parse_json_ld_object(item, metadata)
                else:
                    self._parse_json_ld_object(data, metadata)

            except (json.JSONDecodeError, TypeError):
                continue

        return metadata

    def _parse_json_ld_object(self, data: Dict, metadata: Dict) -> None:
        """Parse a single JSON-LD object"""
        if not isinstance(data, dict):
            return

        if '@graph' in data:
            for item in data['@graph']:
                self._parse_json_ld_object(item, metadata)
            return

        # Title
        if 'headline' in data:
            metadata['title'] = data['headline']
        elif 'name' in data and not metadata.get('title'):
            metadata['title'] = data['name']

        # Description
        if 'description' in data:
            metadata['description'] = data['description']

        # Date
        if 'datePublished' in data:
            metadata['date_published'] = data['datePublished'][:10]
        if 'dateModified' in data:
            metadata['date_modified'] = data['dateModified'][:10]

        # Authors
        authors = data.get('author', [])
        if isinstance(authors, dict):
            authors = [authors]
        elif isinstance(authors, str):
            authors = [{'name': authors}]

        author_names = []
        for author in authors:
            if isinstance(author, dict):
                name = author.get('name', '')
                if name:
                    author_names.append(name)
            elif isinstance(author, str):
                author_names.append(author)

        if author_names:
            metadata['authors'] = author_names

        # Publisher
        publisher = data.get('publisher', {})
        if isinstance(publisher, dict):
            metadata['publisher'] = publisher.get('name', '')
        elif isinstance(publisher, str):
            metadata['publisher'] = publisher

    def _extract_open_graph(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Open Graph meta tags"""
        metadata = {}

        og_mappings = {
            'og:title': 'title',
            'og:description': 'description',
            'og:url': 'canonical_url',
            'og:site_name': 'site_name',
            'og:type': 'og_type',
            'article:published_time': 'date_published',
            'article:modified_time': 'date_modified',
            'article:author': 'author_url',
        }

        for og_prop, field in og_mappings.items():
            tag = soup.find('meta', property=og_prop)
            if tag and tag.get('content'):
                metadata[field] = tag['content'].strip()

        return metadata

    def _extract_html_meta(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract standard HTML meta tags"""
        metadata = {}

        # Title
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            # Clean up title suffixes
            for suffix in [' | Google DeepMind', ' - Google', ' | Google']:
                if title.endswith(suffix):
                    title = title[:-len(suffix)]
            metadata['title'] = title

        # Description
        desc_tag = soup.find('meta', attrs={'name': 'description'})
        if desc_tag and desc_tag.get('content'):
            metadata['description'] = desc_tag['content']

        # Author
        author_tag = soup.find('meta', attrs={'name': 'author'})
        if author_tag and author_tag.get('content'):
            metadata['authors'] = [author_tag['content']]

        return metadata

    def _extract_deepmind(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """DeepMind-specific extraction"""
        metadata = {}

        # Look for blog post date
        date_elem = soup.find(class_=re.compile(r'date|time|published'))
        if date_elem:
            date_text = date_elem.get_text().strip()
            metadata['date_published'] = date_text

        # DeepMind is the author for blog posts
        if not metadata.get('authors'):
            metadata['authors'] = ['Google DeepMind']

        return metadata

    def _extract_google_blog(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Google Blog specific extraction"""
        metadata = {}

        # Look for author byline
        byline = soup.find(class_=re.compile(r'byline|author'))
        if byline:
            author_text = byline.get_text().strip()
            # Clean up "By Author Name"
            author_text = re.sub(r'^by\s+', '', author_text, flags=re.I)
            if author_text:
                metadata['authors'] = [author_text]

        return metadata

    def _extract_earth_engine(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Google Earth Engine documentation extraction"""
        metadata = {
            'content_type': 'documentation',
            'publisher': 'Google',
            'site_name': 'Google Earth Engine',
        }

        if not metadata.get('authors'):
            metadata['authors'] = ['Google Earth Engine Team']

        return metadata

    def _extract_source_coop(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Source Cooperative dataset extraction"""
        metadata = {
            'content_type': 'dataset',
            'publisher': 'Source Cooperative',
        }

        # Look for dataset title
        h1 = soup.find('h1')
        if h1:
            metadata['title'] = h1.get_text().strip()

        return metadata

    def _generate_id(self, url: str, metadata: Dict) -> str:
        """Generate a unique ID"""
        parsed = urlparse(url)
        domain = parsed.netloc.replace('.', '_').replace('www_', '')
        path = self._safe_id(parsed.path[:30])
        return f"{domain}_{path}"

    def _build_ris(self, metadata: Dict[str, Any]) -> str:
        """Build RIS with Google-specific formatting"""
        from ris_converter import RISBuilder

        # Determine RIS type
        content_type = metadata.get('content_type', 'webpage')
        if content_type == 'blog':
            ris_type = 'BLOG'
        elif content_type == 'dataset':
            ris_type = 'DATA'
        elif content_type == 'documentation':
            ris_type = 'ELEC'
        else:
            ris_type = 'ELEC'

        builder = RISBuilder(ris_type)

        builder.set_id(metadata.get('id', 'Google'))

        # Authors
        authors = metadata.get('authors', [])
        if isinstance(authors, str):
            authors = [authors]
        for author in authors:
            builder.add_author(author)

        # If still no authors, use publisher
        if not authors and metadata.get('publisher'):
            builder.add_author(metadata['publisher'])

        builder.set_title(metadata.get('title', ''))
        builder.set_secondary_title(metadata.get('site_name', ''))
        builder.set_year(metadata.get('year', ''))

        date = metadata.get('date_published', '') or metadata.get('date', '')
        builder.set_date(date)

        builder.set_abstract(metadata.get('description', ''))
        builder.set_url(metadata.get('url', ''))
        builder.set_publisher(metadata.get('publisher', 'Google'))

        if metadata.get('keywords'):
            builder.set_keywords(metadata['keywords'])

        return builder.build()
