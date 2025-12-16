"""
Platform-specific handlers for web citation fetching.
"""

from .base_handler import BaseHandler
from .github_handler import GitHubHandler
from .youtube_handler import YouTubeHandler
from .medium_handler import MediumHandler
from .stackoverflow_handler import StackOverflowHandler
from .twitter_handler import TwitterHandler
from .google_handler import GoogleHandler

__all__ = [
    'BaseHandler',
    'GitHubHandler',
    'YouTubeHandler',
    'MediumHandler',
    'StackOverflowHandler',
    'TwitterHandler',
    'GoogleHandler',
]
