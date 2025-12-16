#!/usr/bin/env python3
"""
GitHub Handler
==============
Fetches citation metadata for GitHub repositories, gists, issues, and PRs.
Uses GitHub API for accurate metadata extraction.
"""

import re
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from .base_handler import BaseHandler

class GitHubHandler(BaseHandler):
    """Handler for GitHub URLs"""

    DOMAINS = ['github.com']
    RIS_TYPE = 'COMP'  # Computer Program

    API_BASE = 'https://api.github.com'

    def fetch(self, url: str) -> Optional[str]:
        """Fetch RIS citation for GitHub URL"""
        metadata = self.extract_metadata(url)
        if not metadata or metadata.get('error'):
            return None
        return self._build_ris(metadata)

    def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract metadata from GitHub URL"""
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')

        if len(path_parts) < 2:
            return {'error': 'Invalid GitHub URL'}

        owner = path_parts[0]
        repo = path_parts[1]

        # Determine type of GitHub resource
        if len(path_parts) == 2:
            # Repository: github.com/owner/repo
            return self._fetch_repo_metadata(owner, repo, url)

        elif 'gist' in parsed.netloc or path_parts[0] == 'gist':
            # Gist
            return self._fetch_gist_metadata(url)

        elif len(path_parts) >= 4 and path_parts[2] == 'issues':
            # Issue: github.com/owner/repo/issues/123
            issue_num = path_parts[3]
            return self._fetch_issue_metadata(owner, repo, issue_num, url)

        elif len(path_parts) >= 4 and path_parts[2] == 'pull':
            # Pull Request: github.com/owner/repo/pull/123
            pr_num = path_parts[3]
            return self._fetch_pr_metadata(owner, repo, pr_num, url)

        elif len(path_parts) >= 4 and path_parts[2] == 'releases':
            # Release: github.com/owner/repo/releases/tag/v1.0
            return self._fetch_release_metadata(owner, repo, path_parts, url)

        else:
            # Default to repo metadata for other paths
            return self._fetch_repo_metadata(owner, repo, url)

    def _fetch_repo_metadata(self, owner: str, repo: str, url: str) -> Dict[str, Any]:
        """Fetch repository metadata"""
        api_url = f"{self.API_BASE}/repos/{owner}/{repo}"
        data = self._api_request(api_url)

        if not data:
            return {'error': 'API request failed', 'url': url}

        # Extract metadata
        metadata = {
            'id': f"GitHub_{owner}_{repo}",
            'title': data.get('name', repo),
            'description': data.get('description', ''),
            'url': data.get('html_url', url),
            'date': data.get('created_at', '')[:10] if data.get('created_at') else '',
            'year': self._extract_year(data.get('created_at', '')),
            'site_name': 'GitHub',
            'publisher': 'GitHub',
            'content_type': 'software',
        }

        # Authors - use owner, and optionally contributors
        owner_data = data.get('owner', {})
        owner_name = owner_data.get('login', owner)
        metadata['authors'] = [owner_name]

        # Get full name if available
        owner_url = owner_data.get('url')
        if owner_url:
            owner_info = self._api_request(owner_url)
            if owner_info and owner_info.get('name'):
                metadata['authors'] = [owner_info['name']]

        # Keywords from topics
        topics = data.get('topics', [])
        if topics:
            metadata['keywords'] = topics

        # Language
        if data.get('language'):
            metadata['keywords'] = metadata.get('keywords', []) + [data['language']]

        # License
        license_info = data.get('license', {})
        if license_info and license_info.get('name'):
            metadata['notes'] = f"License: {license_info['name']}"

        # Stars and forks for notes
        stars = data.get('stargazers_count', 0)
        forks = data.get('forks_count', 0)
        metadata['misc'] = f"Stars: {stars}, Forks: {forks}"

        return metadata

    def _fetch_gist_metadata(self, url: str) -> Dict[str, Any]:
        """Fetch gist metadata"""
        # Extract gist ID from URL
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        gist_id = path_parts[-1] if path_parts else ''

        api_url = f"{self.API_BASE}/gists/{gist_id}"
        data = self._api_request(api_url)

        if not data:
            return {'error': 'API request failed', 'url': url}

        # Get description or first filename as title
        description = data.get('description', '')
        files = data.get('files', {})
        first_file = list(files.keys())[0] if files else 'Gist'

        metadata = {
            'id': f"Gist_{gist_id}",
            'title': description or first_file,
            'description': description,
            'url': data.get('html_url', url),
            'date': data.get('created_at', '')[:10] if data.get('created_at') else '',
            'year': self._extract_year(data.get('created_at', '')),
            'site_name': 'GitHub Gist',
            'publisher': 'GitHub',
            'content_type': 'software',
        }

        # Author
        owner = data.get('owner', {})
        if owner.get('login'):
            metadata['authors'] = [owner['login']]

        return metadata

    def _fetch_issue_metadata(self, owner: str, repo: str,
                               issue_num: str, url: str) -> Dict[str, Any]:
        """Fetch issue metadata"""
        api_url = f"{self.API_BASE}/repos/{owner}/{repo}/issues/{issue_num}"
        data = self._api_request(api_url)

        if not data:
            return {'error': 'API request failed', 'url': url}

        metadata = {
            'id': f"GitHub_{owner}_{repo}_issue_{issue_num}",
            'title': f"Issue #{issue_num}: {data.get('title', '')}",
            'description': data.get('body', '')[:500] if data.get('body') else '',
            'url': data.get('html_url', url),
            'date': data.get('created_at', '')[:10] if data.get('created_at') else '',
            'year': self._extract_year(data.get('created_at', '')),
            'site_name': f"GitHub - {owner}/{repo}",
            'publisher': 'GitHub',
            'content_type': 'software',
        }

        # Author
        user = data.get('user', {})
        if user.get('login'):
            metadata['authors'] = [user['login']]

        # Labels as keywords
        labels = data.get('labels', [])
        if labels:
            metadata['keywords'] = [l.get('name', '') for l in labels if l.get('name')]

        return metadata

    def _fetch_pr_metadata(self, owner: str, repo: str,
                           pr_num: str, url: str) -> Dict[str, Any]:
        """Fetch pull request metadata"""
        api_url = f"{self.API_BASE}/repos/{owner}/{repo}/pulls/{pr_num}"
        data = self._api_request(api_url)

        if not data:
            return {'error': 'API request failed', 'url': url}

        metadata = {
            'id': f"GitHub_{owner}_{repo}_pr_{pr_num}",
            'title': f"PR #{pr_num}: {data.get('title', '')}",
            'description': data.get('body', '')[:500] if data.get('body') else '',
            'url': data.get('html_url', url),
            'date': data.get('created_at', '')[:10] if data.get('created_at') else '',
            'year': self._extract_year(data.get('created_at', '')),
            'site_name': f"GitHub - {owner}/{repo}",
            'publisher': 'GitHub',
            'content_type': 'software',
        }

        # Author
        user = data.get('user', {})
        if user.get('login'):
            metadata['authors'] = [user['login']]

        # State
        state = data.get('state', '')
        merged = data.get('merged', False)
        if merged:
            metadata['notes'] = 'Status: Merged'
        elif state:
            metadata['notes'] = f'Status: {state.capitalize()}'

        return metadata

    def _fetch_release_metadata(self, owner: str, repo: str,
                                 path_parts: list, url: str) -> Dict[str, Any]:
        """Fetch release metadata"""
        # Try to get tag name
        tag = ''
        if 'tag' in path_parts:
            tag_idx = path_parts.index('tag')
            if tag_idx + 1 < len(path_parts):
                tag = path_parts[tag_idx + 1]

        if tag:
            api_url = f"{self.API_BASE}/repos/{owner}/{repo}/releases/tags/{tag}"
        else:
            api_url = f"{self.API_BASE}/repos/{owner}/{repo}/releases/latest"

        data = self._api_request(api_url)

        if not data:
            # Fall back to repo metadata
            return self._fetch_repo_metadata(owner, repo, url)

        metadata = {
            'id': f"GitHub_{owner}_{repo}_release_{self._safe_id(tag or 'latest')}",
            'title': f"{repo} {data.get('name', tag)}",
            'description': data.get('body', '')[:500] if data.get('body') else '',
            'url': data.get('html_url', url),
            'date': data.get('published_at', '')[:10] if data.get('published_at') else '',
            'year': self._extract_year(data.get('published_at', '')),
            'site_name': f"GitHub - {owner}/{repo}",
            'publisher': 'GitHub',
            'content_type': 'software',
            'misc': f"Version: {data.get('tag_name', tag)}",
        }

        # Author
        author = data.get('author', {})
        if author.get('login'):
            metadata['authors'] = [author['login']]

        return metadata

    def _build_ris(self, metadata: Dict[str, Any]) -> str:
        """Build RIS with GitHub-specific formatting"""
        from ris_converter import RISBuilder

        builder = RISBuilder('COMP')

        builder.set_id(metadata.get('id', 'GitHub'))

        # Authors
        for author in metadata.get('authors', []):
            builder.add_author(author)

        builder.set_title(metadata.get('title', ''))
        builder.set_secondary_title(metadata.get('site_name', 'GitHub'))
        builder.set_year(metadata.get('year', ''))
        builder.set_date(metadata.get('date', ''))
        builder.set_abstract(metadata.get('description', ''))
        builder.set_url(metadata.get('url', ''))
        builder.set_publisher('GitHub')

        if metadata.get('keywords'):
            builder.set_keywords(metadata['keywords'])

        if metadata.get('notes'):
            builder.add_note(metadata['notes'])

        if metadata.get('misc'):
            builder.set_misc(metadata['misc'])

        return builder.build()
