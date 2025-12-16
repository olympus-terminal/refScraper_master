#!/usr/bin/env python3
"""
Stack Overflow Handler
======================
Fetches citation metadata for Stack Overflow questions and answers.
Uses Stack Exchange API for accurate metadata.
"""

import re
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import html

from .base_handler import BaseHandler

class StackOverflowHandler(BaseHandler):
    """Handler for Stack Overflow and Stack Exchange URLs"""

    DOMAINS = [
        'stackoverflow.com',
        'stackexchange.com',
        'superuser.com',
        'serverfault.com',
        'askubuntu.com',
        'mathoverflow.net',
        'stackapps.com',
    ]

    # Stack Exchange sites mapping
    SITE_NAMES = {
        'stackoverflow.com': 'Stack Overflow',
        'superuser.com': 'Super User',
        'serverfault.com': 'Server Fault',
        'askubuntu.com': 'Ask Ubuntu',
        'mathoverflow.net': 'MathOverflow',
        'stackapps.com': 'Stack Apps',
    }

    RIS_TYPE = 'ELEC'

    API_BASE = 'https://api.stackexchange.com/2.3'

    def fetch(self, url: str) -> Optional[str]:
        """Fetch RIS citation for Stack Overflow URL"""
        metadata = self.extract_metadata(url)
        if not metadata or metadata.get('error'):
            return None
        return self._build_ris(metadata)

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract metadata from Stack Overflow URL"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')

        # Determine site key for API
        site_key = self._get_site_key(domain)
        site_name = self.SITE_NAMES.get(domain, 'Stack Exchange')

        # Parse URL to get question/answer ID
        question_id, answer_id = self._parse_url(parsed.path)

        if not question_id:
            return {'error': 'Could not parse question ID', 'url': url}

        # Fetch from API
        api_data = self._fetch_question(question_id, site_key)
        if not api_data:
            # Fallback to basic metadata
            return self._fallback_metadata(url, question_id, site_name)

        metadata = {
            'id': f"SO_{question_id}",
            'url': url,
            'site_name': site_name,
            'content_type': 'qa',
        }

        # Extract from API response
        items = api_data.get('items', [])
        if items:
            q = items[0]

            # Title
            metadata['title'] = html.unescape(q.get('title', ''))

            # Author (question asker)
            owner = q.get('owner', {})
            if owner.get('display_name'):
                metadata['authors'] = [html.unescape(owner['display_name'])]

            # Date (creation date)
            creation_date = q.get('creation_date')
            if creation_date:
                from datetime import datetime
                dt = datetime.fromtimestamp(creation_date)
                metadata['date'] = dt.strftime('%Y-%m-%d')
                metadata['year'] = dt.strftime('%Y')

            # Tags as keywords
            tags = q.get('tags', [])
            if tags:
                metadata['keywords'] = tags

            # Score and answer count for notes
            score = q.get('score', 0)
            answer_count = q.get('answer_count', 0)
            is_answered = q.get('is_answered', False)

            notes = []
            notes.append(f"Score: {score}")
            notes.append(f"Answers: {answer_count}")
            if is_answered:
                notes.append("Has accepted answer")
            metadata['notes'] = '; '.join(notes)

            # Use body excerpt as description
            if q.get('body'):
                # Strip HTML and truncate
                body = re.sub(r'<[^>]+>', '', q['body'])
                body = html.unescape(body)
                metadata['description'] = body[:500]

        # If linking to specific answer
        if answer_id:
            answer_data = self._fetch_answer(answer_id, site_key)
            if answer_data and answer_data.get('items'):
                ans = answer_data['items'][0]
                ans_owner = ans.get('owner', {})
                if ans_owner.get('display_name'):
                    metadata['title'] = f"Answer by {html.unescape(ans_owner['display_name'])}: {metadata.get('title', '')}"
                    metadata['authors'] = [html.unescape(ans_owner['display_name'])]
                metadata['id'] = f"SO_{question_id}_a{answer_id}"

        return metadata

    def _get_site_key(self, domain: str) -> str:
        """Get API site key from domain"""
        if 'stackoverflow.com' in domain:
            return 'stackoverflow'
        elif 'superuser.com' in domain:
            return 'superuser'
        elif 'serverfault.com' in domain:
            return 'serverfault'
        elif 'askubuntu.com' in domain:
            return 'askubuntu'
        elif 'mathoverflow.net' in domain:
            return 'mathoverflow'
        elif 'stackapps.com' in domain:
            return 'stackapps'
        else:
            # For other SE sites, extract from subdomain
            parts = domain.split('.')
            if 'stackexchange.com' in domain and len(parts) > 2:
                return parts[0]
            return 'stackoverflow'

    def _parse_url(self, path: str) -> tuple:
        """Parse URL path to extract question and answer IDs"""
        question_id = None
        answer_id = None

        # /questions/12345/title-slug
        # /questions/12345/title-slug/67890 (answer)
        # /q/12345
        # /a/67890

        parts = path.strip('/').split('/')

        if 'questions' in parts:
            idx = parts.index('questions')
            if idx + 1 < len(parts):
                question_id = parts[idx + 1]
            # Check for answer ID (numeric after slug)
            if idx + 3 < len(parts) and parts[idx + 3].isdigit():
                answer_id = parts[idx + 3]

        elif 'q' in parts:
            idx = parts.index('q')
            if idx + 1 < len(parts):
                question_id = parts[idx + 1]

        elif 'a' in parts:
            idx = parts.index('a')
            if idx + 1 < len(parts):
                answer_id = parts[idx + 1]

        # Handle hash anchor for answers
        if '#' in path:
            anchor = path.split('#')[-1]
            if anchor.isdigit():
                answer_id = anchor

        return question_id, answer_id

    def _fetch_question(self, question_id: str, site: str) -> Optional[Dict]:
        """Fetch question data from API"""
        url = f"{self.API_BASE}/questions/{question_id}"
        params = {
            'site': site,
            'filter': 'withbody',  # Include body
        }
        return self._api_request(url, params=params)

    def _fetch_answer(self, answer_id: str, site: str) -> Optional[Dict]:
        """Fetch answer data from API"""
        url = f"{self.API_BASE}/answers/{answer_id}"
        params = {
            'site': site,
            'filter': 'withbody',
        }
        return self._api_request(url, params=params)

    def _fallback_metadata(self, url: str, question_id: str,
                           site_name: str) -> Dict[str, Any]:
        """Generate basic metadata when API fails"""
        return {
            'id': f"SO_{question_id}",
            'title': f"Question {question_id}",
            'url': url,
            'site_name': site_name,
            'publisher': 'Stack Exchange',
            'content_type': 'qa',
        }

    def _build_ris(self, metadata: Dict[str, Any]) -> str:
        """Build RIS with Stack Overflow-specific formatting"""
        from ris_converter import RISBuilder

        builder = RISBuilder('ELEC')

        builder.set_id(metadata.get('id', 'StackOverflow'))

        # Authors
        for author in metadata.get('authors', []):
            builder.add_author(author)

        builder.set_title(metadata.get('title', ''))
        builder.set_secondary_title(metadata.get('site_name', 'Stack Overflow'))
        builder.set_year(metadata.get('year', ''))
        builder.set_date(metadata.get('date', ''))
        builder.set_abstract(metadata.get('description', ''))
        builder.set_url(metadata.get('url', ''))
        builder.set_publisher('Stack Exchange')

        if metadata.get('keywords'):
            builder.set_keywords(metadata['keywords'])

        if metadata.get('notes'):
            builder.add_note(metadata['notes'])

        return builder.build()
