#!/usr/bin/env python3
"""
Web Metadata Extractor
======================
Extracts citation metadata from any web page using multiple strategies:
1. JSON-LD (Schema.org) - highest priority
2. Open Graph meta tags
3. Twitter Card meta tags
4. Dublin Core meta tags
5. Standard HTML meta tags
6. Fallback: page content parsing

Date: 2024-12-13
"""

import re
import json
import requests
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from datetime import datetime

class WebMetadataExtractor:
    """Extract citation metadata from any web page"""

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def extract(self, url: str) -> Dict[str, Any]:
        """
        Extract metadata from a URL.
        Returns standardized metadata dict.
        """
        try:
            response = self.session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            html = response.text
            final_url = response.url  # After redirects
        except Exception as e:
            print(f"[ERROR] Failed to fetch {url}: {e}")
            return {'url': url, 'error': str(e)}

        soup = BeautifulSoup(html, 'lxml')

        # Extract metadata using priority-ordered strategies
        metadata = {
            'url': final_url,
            'source_url': url,
        }

        # Strategy 1: JSON-LD (Schema.org) - highest quality
        json_ld = self._extract_json_ld(soup)
        if json_ld:
            metadata.update(json_ld)

        # Strategy 2: Open Graph meta tags
        og = self._extract_open_graph(soup)
        self._merge_metadata(metadata, og)

        # Strategy 3: Twitter Card meta tags
        twitter = self._extract_twitter_cards(soup)
        self._merge_metadata(metadata, twitter)

        # Strategy 4: Dublin Core meta tags
        dc = self._extract_dublin_core(soup)
        self._merge_metadata(metadata, dc)

        # Strategy 5: Standard HTML meta tags
        html_meta = self._extract_html_meta(soup)
        self._merge_metadata(metadata, html_meta)

        # Strategy 6: Fallback parsing
        fallback = self._extract_fallback(soup, final_url)
        self._merge_metadata(metadata, fallback)

        # Normalize and clean up
        return self._normalize(metadata)

    def _merge_metadata(self, base: Dict, update: Dict) -> None:
        """Merge update into base, only filling empty fields"""
        for key, value in update.items():
            if key not in base or not base[key]:
                base[key] = value

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Schema.org JSON-LD structured data"""
        metadata = {}

        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)

                # Handle array of objects
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

        obj_type = data.get('@type', '')

        # Handle @graph structure
        if '@graph' in data:
            for item in data['@graph']:
                self._parse_json_ld_object(item, metadata)
            return

        # Article, BlogPosting, NewsArticle, etc.
        if obj_type in ['Article', 'BlogPosting', 'NewsArticle', 'TechArticle',
                        'WebPage', 'CreativeWork', 'SoftwareSourceCode',
                        'Dataset', 'VideoObject', 'HowTo']:

            if 'headline' in data:
                metadata['title'] = data['headline']
            elif 'name' in data:
                metadata['title'] = data['name']

            if 'description' in data:
                metadata['description'] = data['description']

            if 'datePublished' in data:
                metadata['date_published'] = data['datePublished']

            if 'dateModified' in data:
                metadata['date_modified'] = data['dateModified']

            if 'dateCreated' in data:
                metadata['date_created'] = data['dateCreated']

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

            # Keywords
            keywords = data.get('keywords', [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',')]
            if keywords:
                metadata['keywords'] = keywords

            # Content type
            metadata['content_type'] = obj_type.lower()

            # URL
            if 'url' in data:
                metadata['canonical_url'] = data['url']

    def _extract_open_graph(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Open Graph meta tags"""
        metadata = {}

        og_tags = {
            'og:title': 'title',
            'og:description': 'description',
            'og:url': 'canonical_url',
            'og:site_name': 'site_name',
            'og:type': 'og_type',
            'og:image': 'image',
            'og:locale': 'locale',
            'article:published_time': 'date_published',
            'article:modified_time': 'date_modified',
            'article:author': 'author_url',
            'article:tag': 'tags',
            'video:duration': 'duration',
        }

        for og_prop, field in og_tags.items():
            tag = soup.find('meta', property=og_prop)
            if tag and tag.get('content'):
                content = tag['content'].strip()
                if field == 'tags':
                    # Collect all article:tag values
                    all_tags = soup.find_all('meta', property='article:tag')
                    metadata['keywords'] = [t['content'] for t in all_tags if t.get('content')]
                else:
                    metadata[field] = content

        return metadata

    def _extract_twitter_cards(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Twitter Card meta tags"""
        metadata = {}

        twitter_tags = {
            'twitter:title': 'title',
            'twitter:description': 'description',
            'twitter:site': 'twitter_site',
            'twitter:creator': 'twitter_creator',
            'twitter:image': 'image',
        }

        for tw_name, field in twitter_tags.items():
            tag = soup.find('meta', attrs={'name': tw_name})
            if tag and tag.get('content'):
                metadata[field] = tag['content'].strip()

        return metadata

    def _extract_dublin_core(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Dublin Core meta tags"""
        metadata = {}

        dc_tags = {
            'DC.title': 'title',
            'DC.creator': 'authors',
            'DC.description': 'description',
            'DC.date': 'date_published',
            'DC.publisher': 'publisher',
            'DC.subject': 'keywords',
            'DC.identifier': 'identifier',
            'DC.type': 'content_type',
            'DC.language': 'language',
            'DCTERMS.created': 'date_created',
            'DCTERMS.modified': 'date_modified',
        }

        for dc_name, field in dc_tags.items():
            tag = soup.find('meta', attrs={'name': dc_name})
            if not tag:
                tag = soup.find('meta', attrs={'name': dc_name.lower()})
            if tag and tag.get('content'):
                content = tag['content'].strip()
                if field == 'authors':
                    # DC.creator might be repeated
                    all_creators = soup.find_all('meta', attrs={'name': dc_name})
                    if not all_creators:
                        all_creators = soup.find_all('meta', attrs={'name': dc_name.lower()})
                    metadata['authors'] = [c['content'] for c in all_creators if c.get('content')]
                elif field == 'keywords':
                    metadata['keywords'] = [k.strip() for k in content.split(',')]
                else:
                    metadata[field] = content

        return metadata

    def _extract_html_meta(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract standard HTML meta tags"""
        metadata = {}

        # Title
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text().strip()

        # Standard meta tags
        meta_mappings = {
            'author': 'authors',
            'description': 'description',
            'keywords': 'keywords',
            'date': 'date_published',
            'last-modified': 'date_modified',
            'generator': 'generator',
            'copyright': 'copyright',
        }

        for meta_name, field in meta_mappings.items():
            tag = soup.find('meta', attrs={'name': meta_name})
            if tag and tag.get('content'):
                content = tag['content'].strip()
                if field == 'authors':
                    metadata['authors'] = [content]
                elif field == 'keywords':
                    metadata['keywords'] = [k.strip() for k in content.split(',')]
                else:
                    metadata[field] = content

        # Canonical URL
        canonical = soup.find('link', rel='canonical')
        if canonical and canonical.get('href'):
            metadata['canonical_url'] = canonical['href']

        return metadata

    def _extract_fallback(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Fallback extraction from page content"""
        metadata = {}

        # Try to find author from common patterns
        author_patterns = [
            ('class', re.compile(r'author|byline|writer', re.I)),
            ('itemprop', 'author'),
            ('rel', 'author'),
        ]

        for attr, value in author_patterns:
            elements = soup.find_all(attrs={attr: value})
            for elem in elements:
                text = elem.get_text().strip()
                # Clean up common prefixes
                text = re.sub(r'^(by|written by|author:?)\s*', '', text, flags=re.I)
                if text and len(text) < 100:  # Reasonable author name length
                    if 'authors' not in metadata:
                        metadata['authors'] = []
                    if text not in metadata['authors']:
                        metadata['authors'].append(text)
                    break
            if 'authors' in metadata:
                break

        # Try to find date from common patterns
        date_patterns = [
            ('class', re.compile(r'date|time|published|posted', re.I)),
            ('itemprop', re.compile(r'datePublished|dateCreated', re.I)),
        ]

        for attr, value in date_patterns:
            elements = soup.find_all(attrs={attr: value})
            for elem in elements:
                # Check datetime attribute first
                dt = elem.get('datetime') or elem.get('content')
                if dt:
                    metadata['date_published'] = dt
                    break
                # Try text content
                text = elem.get_text().strip()
                if text and len(text) < 50:
                    metadata['date_published'] = text
                    break
            if 'date_published' in metadata:
                break

        # Site name from domain
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '')
        metadata['site_name'] = domain

        return metadata

    def _normalize(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and clean up metadata"""
        # Ensure authors is a list
        if 'authors' in metadata and isinstance(metadata['authors'], str):
            metadata['authors'] = [metadata['authors']]

        # Clean up title
        if 'title' in metadata:
            title = metadata['title']
            # Remove site name suffix (e.g., "Article Title | Site Name")
            if 'site_name' in metadata and metadata['site_name']:
                site = metadata['site_name']
                for sep in [' | ', ' - ', ' :: ', ' ~ ']:
                    if sep + site in title:
                        title = title.split(sep + site)[0].strip()
                    if site + sep in title:
                        title = title.split(site + sep)[-1].strip()
            metadata['title'] = title.strip()

        # Parse and normalize dates
        for date_field in ['date_published', 'date_modified', 'date_created']:
            if date_field in metadata:
                metadata[date_field] = self._parse_date(metadata[date_field])

        # Extract year
        for date_field in ['date_published', 'date_modified', 'date_created']:
            if date_field in metadata and metadata[date_field]:
                year_match = re.search(r'\b(19|20)\d{2}\b', str(metadata[date_field]))
                if year_match:
                    metadata['year'] = year_match.group(0)
                    break

        # Determine content type if not set
        if 'content_type' not in metadata or not metadata['content_type']:
            metadata['content_type'] = self._infer_content_type(metadata)

        # Use canonical URL if available
        if 'canonical_url' in metadata:
            metadata['url'] = metadata['canonical_url']

        return metadata

    def _parse_date(self, date_str: str) -> str:
        """Parse date string to ISO format"""
        if not date_str:
            return ''

        # Already ISO format
        if re.match(r'^\d{4}-\d{2}-\d{2}', date_str):
            return date_str[:10]  # Just the date part

        # Common formats
        formats = [
            '%B %d, %Y',      # December 13, 2024
            '%b %d, %Y',      # Dec 13, 2024
            '%d %B %Y',       # 13 December 2024
            '%d %b %Y',       # 13 Dec 2024
            '%Y/%m/%d',       # 2024/12/13
            '%m/%d/%Y',       # 12/13/2024
            '%d/%m/%Y',       # 13/12/2024
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        # Return original if parsing fails
        return date_str

    def _infer_content_type(self, metadata: Dict) -> str:
        """Infer content type from available metadata"""
        url = metadata.get('url', '')
        og_type = metadata.get('og_type', '')

        # Check OG type
        if og_type:
            if 'video' in og_type:
                return 'video'
            if 'article' in og_type:
                return 'article'

        # Check URL patterns
        url_lower = url.lower()
        if '/blog/' in url_lower or 'blog.' in url_lower:
            return 'blog'
        if '/docs/' in url_lower or '/documentation/' in url_lower:
            return 'documentation'
        if '/news/' in url_lower:
            return 'news'
        if 'github.com' in url_lower:
            return 'software'

        return 'webpage'

def main():
    """Test the extractor"""
    extractor = WebMetadataExtractor()

    test_urls = [
        "https://deepmind.google/discover/blog/alphaearth-foundations-helps-map-our-planet/",
    ]

    for url in test_urls:
        print(f"\n{'='*70}")
        print(f"URL: {url}")
        print('='*70)

        metadata = extractor.extract(url)
        for key, value in sorted(metadata.items()):
            print(f"  {key}: {value}")

if __name__ == "__main__":
    main()
