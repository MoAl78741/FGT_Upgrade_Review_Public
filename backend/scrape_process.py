import json
import sys
from .database import SessionLocal
from .models import ScrapeJob
from .scrape_worker import run_scrape
from .settings import settings

if __name__ == '__main__':
    if not settings.scraping:
        raise SystemExit('Scraping disabled')
    with SessionLocal() as db:
        job = db.get(ScrapeJob, sys.argv[1])
        args = json.loads(job.request_json)
        run_scrape(job.id, job.from_version, job.to_version, job.use_selenium,
                   settings.grid_url if job.use_selenium else None, args.get('force_rescrape', False),
                   include_from=args.get('include_from', False))
