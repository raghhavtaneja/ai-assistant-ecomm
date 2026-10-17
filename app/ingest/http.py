"""Shared HTTP client and robots.txt check for everything that fetches store data."""

import logging
from urllib.robotparser import RobotFileParser

import httpx

from app.config import settings

log = logging.getLogger(__name__)


def make_client() -> httpx.Client:
    """One client per crawl so connections are reused and every request is identified."""
    return httpx.Client(
        headers={"User-Agent": settings.crawl_user_agent},
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
    )


def load_robots(client: httpx.Client, base_url: str) -> RobotFileParser:
    """Fetch and parse robots.txt. A missing file means everything is allowed."""
    robots = RobotFileParser()
    try:
        response = client.get(f"{base_url}/robots.txt")
    except httpx.HTTPError as exc:
        # Can't tell what's allowed, so be conservative and allow nothing.
        log.warning("Could not fetch robots.txt for %s: %s", base_url, exc)
        robots.disallow_all = True
        return robots
    if response.status_code == 404:
        robots.allow_all = True
    else:
        robots.parse(response.text.splitlines())
    return robots


def is_allowed(robots: RobotFileParser, url: str) -> bool:
    return robots.can_fetch(settings.crawl_user_agent, url)
