#!/usr/bin/env python3
"""
RIS Converter
=============
Converts standardized metadata dictionaries to RIS format.
Supports multiple content types with appropriate RIS type mappings.

Date: 2024-12-13
"""

import re
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

class RISConverter:
    """Convert metadata dictionaries to RIS format"""

    # RIS type mappings based on content type
    TYPE_MAP = {
        # Articles
        'article': 'BLOG',
        'blog': 'BLOG',
        'blogposting': 'BLOG',
        'newsarticle': 'NEWS',
        'news': 'NEWS',

        # Web content
        'webpage': 'ELEC',
        'documentation': 'ELEC',
        'howto': 'ELEC',
        'tutorial': 'ELEC',

        # Software
        'software': 'COMP',
        'softwaresourcecode': 'COMP',
        'repository': 'COMP',

        # Multimedia
        'video': 'VIDEO',
        'videoobject': 'VIDEO',

        # Data
        'dataset': 'DATA',
        'data': 'DATA',

        # Academic
        'scholarlyarticle': 'JOUR',
        'techarticle': 'RPRT',

        # Default
        'default': 'ELEC',
    }

    # RIS field descriptions for reference:
    # TY  - Type
    # ID  - Reference ID
    # AU  - Author
    # TI  - Title
    # T2  - Secondary Title (journal, website name)
    # PY  - Publication Year
    # DA  - Date
    # AB  - Abstract
    # UR  - URL
    # DO  - DOI
    # KW  - Keywords
    # PB  - Publisher
    # LA  - Language
    # N1  - Notes
    # ER  - End of Reference

    def convert(self, metadata: Dict[str, Any]) -> str:
        """
        Convert metadata dict to RIS format string.

        Args:
            metadata: Dictionary with keys like title, authors, url, etc.

        Returns:
            RIS formatted string
        """
        ris_lines = []

        # Determine RIS type
        content_type = metadata.get('content_type', 'webpage').lower()
        ris_type = self.TYPE_MAP.get(content_type, self.TYPE_MAP['default'])
        ris_lines.append(f"TY  - {ris_type}")

        # Generate ID from URL or title
        ref_id = self._generate_id(metadata)
        ris_lines.append(f"ID  - {ref_id}")

        # Authors
        authors = metadata.get('authors', [])
        if isinstance(authors, str):
            authors = [authors]
        for author in authors:
            formatted = self._format_author(author)
            if formatted:
                ris_lines.append(f"AU  - {formatted}")

        # If no authors, try twitter_creator or site_name
        if not authors:
            if metadata.get('twitter_creator'):
                ris_lines.append(f"AU  - {metadata['twitter_creator']}")
            elif metadata.get('publisher'):
                ris_lines.append(f"AU  - {metadata['publisher']}")
            elif metadata.get('site_name'):
                ris_lines.append(f"AU  - {metadata['site_name']}")

        # Title
        title = metadata.get('title', '')
        if title:
            ris_lines.append(f"TI  - {self._clean_text(title)}")

        # Secondary title (website/publication name)
        site_name = metadata.get('site_name', '')
        publisher = metadata.get('publisher', '')
        if site_name:
            ris_lines.append(f"T2  - {site_name}")
        elif publisher:
            ris_lines.append(f"T2  - {publisher}")

        # Year and Date
        year = metadata.get('year', '')
        if year:
            ris_lines.append(f"PY  - {year}")

        date = metadata.get('date_published', '') or metadata.get('date_modified', '')
        if date:
            ris_lines.append(f"DA  - {date}")

        # Abstract/Description
        description = metadata.get('description', '')
        if description:
            # Truncate very long descriptions
            desc_clean = self._clean_text(description)[:2000]
            ris_lines.append(f"AB  - {desc_clean}")

        # URL
        url = metadata.get('url', '') or metadata.get('source_url', '')
        if url:
            ris_lines.append(f"UR  - {url}")

        # DOI
        doi = metadata.get('doi', '')
        if doi:
            ris_lines.append(f"DO  - {doi}")

        # Keywords
        keywords = metadata.get('keywords', [])
        if keywords:
            if isinstance(keywords, str):
                keywords = [keywords]
            kw_str = '; '.join(keywords[:10])  # Limit to 10 keywords
            ris_lines.append(f"KW  - {kw_str}")

        # Publisher
        if publisher and publisher != site_name:
            ris_lines.append(f"PB  - {publisher}")

        # Language
        language = metadata.get('language', '') or metadata.get('locale', '')
        if language:
            # Extract language code
            lang_code = language.split('_')[0].split('-')[0]
            ris_lines.append(f"LA  - {lang_code}")

        # Notes - content type and access date
        notes = []
        if content_type and content_type != 'webpage':
            notes.append(f"Content type: {content_type}")
        if metadata.get('generator'):
            notes.append(f"Generator: {metadata['generator']}")

        if notes:
            ris_lines.append(f"N1  - {'; '.join(notes)}")

        # End of reference
        ris_lines.append("ER  - ")
        ris_lines.append("")

        return '\n'.join(ris_lines)

    def _generate_id(self, metadata: Dict) -> str:
        """Generate a reference ID from metadata"""
        # Try URL-based ID
        url = metadata.get('url', '') or metadata.get('source_url', '')
        if url:
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '').replace('.', '_')
            path = parsed.path.strip('/').replace('/', '_')[:50]
            return f"WEB_{domain}_{path}".replace('-', '_')

        # Fallback to title-based ID
        title = metadata.get('title', 'unknown')
        safe_title = re.sub(r'[^a-zA-Z0-9]', '_', title)[:50]
        return f"WEB_{safe_title}"

    def _format_author(self, author: str) -> str:
        """
        Format author name for RIS.
        RIS prefers "Last, First" format.
        """
        if not author:
            return ''

        author = author.strip()

        # Already in "Last, First" format
        if ',' in author:
            return author

        # Handle "First Last" format
        parts = author.split()
        if len(parts) >= 2:
            # Assume last word is surname
            return f"{parts[-1]}, {' '.join(parts[:-1])}"

        return author

    def _clean_text(self, text: str) -> str:
        """Clean text for RIS format"""
        if not text:
            return ''

        # Replace newlines with spaces
        text = re.sub(r'\s+', ' ', text)

        # Remove control characters
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)

        return text.strip()

class RISBuilder:
    """Builder pattern for constructing RIS entries field by field"""

    def __init__(self, ris_type: str = 'ELEC'):
        self.lines = [f"TY  - {ris_type}"]
        self._id_set = False

    def set_id(self, ref_id: str) -> 'RISBuilder':
        self.lines.append(f"ID  - {ref_id}")
        self._id_set = True
        return self

    def add_author(self, name: str) -> 'RISBuilder':
        if name:
            self.lines.append(f"AU  - {name}")
        return self

    def set_title(self, title: str) -> 'RISBuilder':
        if title:
            self.lines.append(f"TI  - {title}")
        return self

    def set_secondary_title(self, title: str) -> 'RISBuilder':
        if title:
            self.lines.append(f"T2  - {title}")
        return self

    def set_year(self, year: str) -> 'RISBuilder':
        if year:
            self.lines.append(f"PY  - {year}")
        return self

    def set_date(self, date: str) -> 'RISBuilder':
        if date:
            self.lines.append(f"DA  - {date}")
        return self

    def set_abstract(self, abstract: str) -> 'RISBuilder':
        if abstract:
            self.lines.append(f"AB  - {abstract[:2000]}")
        return self

    def set_url(self, url: str) -> 'RISBuilder':
        if url:
            self.lines.append(f"UR  - {url}")
        return self

    def set_doi(self, doi: str) -> 'RISBuilder':
        if doi:
            self.lines.append(f"DO  - {doi}")
        return self

    def set_keywords(self, keywords: List[str]) -> 'RISBuilder':
        if keywords:
            self.lines.append(f"KW  - {'; '.join(keywords[:10])}")
        return self

    def set_publisher(self, publisher: str) -> 'RISBuilder':
        if publisher:
            self.lines.append(f"PB  - {publisher}")
        return self

    def set_journal(self, journal: str) -> 'RISBuilder':
        """For journal articles"""
        if journal:
            self.lines.append(f"JO  - {journal}")
        return self

    def set_volume(self, volume: str) -> 'RISBuilder':
        if volume:
            self.lines.append(f"VL  - {volume}")
        return self

    def set_issue(self, issue: str) -> 'RISBuilder':
        if issue:
            self.lines.append(f"IS  - {issue}")
        return self

    def set_start_page(self, page: str) -> 'RISBuilder':
        if page:
            self.lines.append(f"SP  - {page}")
        return self

    def set_end_page(self, page: str) -> 'RISBuilder':
        if page:
            self.lines.append(f"EP  - {page}")
        return self

    def set_language(self, lang: str) -> 'RISBuilder':
        if lang:
            self.lines.append(f"LA  - {lang}")
        return self

    def add_note(self, note: str) -> 'RISBuilder':
        if note:
            self.lines.append(f"N1  - {note}")
        return self

    def set_misc(self, value: str) -> 'RISBuilder':
        """M1 field for miscellaneous info"""
        if value:
            self.lines.append(f"M1  - {value}")
        return self

    def build(self) -> str:
        """Build the final RIS string"""
        self.lines.append("ER  - ")
        self.lines.append("")
        return '\n'.join(self.lines)

def main():
    """Test the converter"""
    converter = RISConverter()

    test_metadata = {
        'title': 'AlphaEarth Foundations helps map our planet',
        'authors': ['Google DeepMind'],
        'description': 'AlphaEarth Foundations is a new AI model for geospatial mapping.',
        'url': 'https://deepmind.google/discover/blog/alphaearth-foundations/',
        'site_name': 'Google DeepMind',
        'date_published': '2024-12-10',
        'year': '2024',
        'content_type': 'blog',
        'keywords': ['AI', 'geospatial', 'mapping'],
    }

    ris = converter.convert(test_metadata)
    print("Generated RIS:")
    print(ris)

if __name__ == "__main__":
    main()
