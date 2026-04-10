"""Scraper implementations."""

from jobpipe.scrapers.base import JobScraper
from jobpipe.scrapers.builtin import BuiltInScraper, BuiltInScraperConfig
from jobpipe.scrapers.hiringcafe import HiringCafeScraper, HiringCafeScraperConfig
from jobpipe.scrapers.wellfound import WellfoundScraper, WellfoundScraperConfig

__all__ = [
	"BuiltInScraper",
	"BuiltInScraperConfig",
	"HiringCafeScraper",
	"HiringCafeScraperConfig",
	"JobScraper",
	"WellfoundScraper",
	"WellfoundScraperConfig",
]
