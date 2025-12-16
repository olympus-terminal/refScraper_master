#!/usr/bin/env python3
"""
YouTube Handler
===============
Fetches citation metadata for YouTube videos using oEmbed API.
"""

import re
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

from .base_handler import BaseHandler

class YouTubeHandler(BaseHandler):
    """Handler for YouTube URLs"""

    DOMAINS = ['youtube.com', 'youtu.be', 'youtube-nocookie.com']
    RIS_TYPE = 'VIDEO'

    OEMBED_URL = 'https://www.youtube.com/oembed'

    def fetch(self, url: str) -> Optional[str]:
        """Fetch RIS citation for YouTube URL"""
        metadata = self.extract_metadata(url)
        if not metadata or metadata.get('error'):
            return None
        return self._build_ris(metadata)

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract metadata from YouTube URL"""
        # Normalize URL and extract video ID
        video_id = self._extract_video_id(url)
        if not video_id:
            return {'error': 'Could not extract video ID', 'url': url}

        canonical_url = f'https://www.youtube.com/watch?v={video_id}'

        # Use oEmbed API
        oembed_data = self._fetch_oembed(canonical_url)
        if not oembed_data:
            # Fallback to HTML parsing
            return self._extract_from_html(canonical_url, video_id)

        metadata = {
            'id': f'YouTube_{video_id}',
            'title': oembed_data.get('title', ''),
            'authors': [oembed_data.get('author_name', 'Unknown')],
            'url': canonical_url,
            'site_name': 'YouTube',
            'publisher': 'YouTube',
            'content_type': 'video',
            'video_id': video_id,
        }

        # Try to get additional metadata from the watch page
        extra = self._extract_from_html(canonical_url, video_id)
        if extra:
            if not metadata.get('description') and extra.get('description'):
                metadata['description'] = extra['description']
            if not metadata.get('date') and extra.get('date'):
                metadata['date'] = extra['date']
                metadata['year'] = self._extract_year(extra['date'])
            if extra.get('keywords'):
                metadata['keywords'] = extra['keywords']

        return metadata

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats"""
        parsed = urlparse(url)

        # youtu.be/VIDEO_ID
        if 'youtu.be' in parsed.netloc:
            return parsed.path.strip('/')

        # youtube.com/watch?v=VIDEO_ID
        if 'youtube.com' in parsed.netloc:
            if '/watch' in parsed.path:
                query = parse_qs(parsed.query)
                if 'v' in query:
                    return query['v'][0]

            # youtube.com/embed/VIDEO_ID
            if '/embed/' in parsed.path:
                parts = parsed.path.split('/embed/')
                if len(parts) > 1:
                    return parts[1].split('/')[0].split('?')[0]

            # youtube.com/v/VIDEO_ID
            if '/v/' in parsed.path:
                parts = parsed.path.split('/v/')
                if len(parts) > 1:
                    return parts[1].split('/')[0].split('?')[0]

            # youtube.com/shorts/VIDEO_ID
            if '/shorts/' in parsed.path:
                parts = parsed.path.split('/shorts/')
                if len(parts) > 1:
                    return parts[1].split('/')[0].split('?')[0]

        return None

    def _fetch_oembed(self, url: str) -> Optional[Dict]:
        """Fetch oEmbed data"""
        params = {
            'url': url,
            'format': 'json',
        }
        return self._api_request(self.OEMBED_URL, params=params)

    def _extract_from_html(self, url: str, video_id: str) -> Dict[str, Any]:
        """Extract metadata from YouTube watch page HTML"""
        metadata = {}

        html = self._fetch_html(url)
        if not html:
            return metadata

        soup = BeautifulSoup(html, 'lxml')

        # Title from meta tags
        title_tag = soup.find('meta', property='og:title')
        if title_tag and title_tag.get('content'):
            metadata['title'] = title_tag['content']

        # Description
        desc_tag = soup.find('meta', property='og:description')
        if desc_tag and desc_tag.get('content'):
            metadata['description'] = desc_tag['content']

        # Channel name (author)
        link_tag = soup.find('link', itemprop='name')
        if link_tag and link_tag.get('content'):
            metadata['authors'] = [link_tag['content']]

        # Date published - look in meta tags
        date_tag = soup.find('meta', itemprop='datePublished')
        if date_tag and date_tag.get('content'):
            metadata['date'] = date_tag['content'][:10]

        # Upload date from meta
        upload_tag = soup.find('meta', itemprop='uploadDate')
        if upload_tag and upload_tag.get('content'):
            metadata['date'] = upload_tag['content'][:10]

        # Keywords
        keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        if keywords_tag and keywords_tag.get('content'):
            metadata['keywords'] = [k.strip() for k in keywords_tag['content'].split(',')]

        # Duration (for notes)
        duration_tag = soup.find('meta', itemprop='duration')
        if duration_tag and duration_tag.get('content'):
            metadata['duration'] = duration_tag['content']

        return metadata

    def _build_ris(self, metadata: Dict[str, Any]) -> str:
        """Build RIS with YouTube-specific formatting"""
        from ris_converter import RISBuilder

        builder = RISBuilder('VIDEO')

        builder.set_id(metadata.get('id', 'YouTube'))

        # Authors (channel name)
        for author in metadata.get('authors', []):
            builder.add_author(author)

        builder.set_title(metadata.get('title', ''))
        builder.set_secondary_title('YouTube')
        builder.set_year(metadata.get('year', ''))
        builder.set_date(metadata.get('date', ''))
        builder.set_abstract(metadata.get('description', ''))
        builder.set_url(metadata.get('url', ''))
        builder.set_publisher('YouTube')

        if metadata.get('keywords'):
            builder.set_keywords(metadata['keywords'])

        # Add video ID and duration to misc
        misc_parts = []
        if metadata.get('video_id'):
            misc_parts.append(f"Video ID: {metadata['video_id']}")
        if metadata.get('duration'):
            misc_parts.append(f"Duration: {metadata['duration']}")
        if misc_parts:
            builder.set_misc('; '.join(misc_parts))

        return builder.build()
