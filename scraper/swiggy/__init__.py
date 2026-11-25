from scraper.swiggy.models import Catalogue
from scraper.swiggy.parser import parse_swiggy_catalogue
from scraper.swiggy.scraper import collect_local_source, collect_swiggy_source

__all__ = ["Catalogue", "parse_swiggy_catalogue", "collect_local_source", "collect_swiggy_source"]
