import asyncio
import json
import os
from typing import List, Dict, Any
import sys
import re
from typing import List, Dict, Any, Optional  # Make sure Optional is imported

print(sys.stdout.encoding)
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    from apify import Actor
except ImportError:
    print("Warning: apify package not found. Install with: pip install apify")

    # Mock Actor for local testing
    class MockActor:
        class log:
            @staticmethod
            def info(msg):
                print(f"INFO: {msg}")

            @staticmethod
            def warning(msg):
                print(f"WARNING: {msg}")

            @staticmethod
            def error(msg):
                print(f"ERROR: {msg}")

        @staticmethod
        async def get_input():
            # Return default input for local testing
            return {
                "municipalities": [
                    "Αθηναίων", "Θεσσαλονίκης", "Αλεξανδρούπολης"
                ]
            }

        @staticmethod
        async def push_data(data):
            print(f"Would push {len(data)} records to dataset")
            # For local testing, you could save to JSON file
            with open('antenna_ids.json', 'a', encoding='utf-8') as f:
                for item in data:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

        def __aenter__(self):
            return self

        def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    Actor = MockActor()

from bs4 import BeautifulSoup
import aiohttp
from aiohttp import ClientSession, ClientTimeout

class GreekAntennaScraper:
    def __init__(self):
        self.base_url = "https://keraies.eett.gr"
        self.search_url = f"{self.base_url}/getData.php"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
            "Accept-Language": "el-gr,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://keraies.eett.gr",
            "DNT": "1",
            "Sec-GPC": "1",
            "Connection": "keep-alive",
            "Referer": "https://keraies.eett.gr/anazhthsh.php",
            "Cookie": "cookielawinfo-checkbox-functional=yes; cookielawinfo-checkbox-necessary=yes; viewed_cookie_policy=yes",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i"
        }

    async def make_request_with_retry(self, session: ClientSession, url: str, data: Dict, max_retries: int = 6) -> Any:
        """Make HTTP request with retry mechanism."""
        for attempt in range(max_retries):
            try:
                timeout = ClientTimeout(total=600)
                async with session.post(url, headers=self.headers, data=data, timeout=timeout) as response:
                    if response.status == 200:
                        content = await response.read()
                        response._content = content
                        return response
                    else:
                        Actor.log.warning(f"HTTP {response.status} on attempt {attempt + 1}")
            except Exception as e:
                Actor.log.warning(f"Request failed on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        return None

    def extract_antenna_id(self, row) -> Optional[str]:
        """Extract antenna ID from table row."""
        cells = row.find_all("td")
        if len(cells) >= 7:
            # Extract antenna ID from onclick attribute
            pattern = r"document\.myform2\.appId\.value=(\d+);"
            match = re.search(pattern, str(cells[6]))
            if match:
                return match.group(1)
        return None

    async def collect_antenna_ids_from_page(self, session: ClientSession, soup: BeautifulSoup) -> List[str]:
        """Collect antenna IDs from a single page."""
        table = soup.find("table", class_="table table-striped table-condensed table-responsive")
        if not table:
            return []

        antenna_ids = []
        for row in table.find_all("tr")[1:]:  # Skip header row
            antenna_id = self.extract_antenna_id(row)
            if antenna_id:
                antenna_ids.append(antenna_id)

        return antenna_ids

    async def collect_all_antenna_ids_from_municipality(self, session: ClientSession, municipality: str) -> List[str]:
        """Collect all antenna IDs from all pages of a municipality."""
        all_antenna_ids = []
        page = 1

        data = {
            "address": "",
            "municipality": municipality,
            "siteId": "",
            "myLat": "",
            "myLng": "",
            "myDistance": "",
            "startPage": str(page),
            "myAction": "first"
        }

        Actor.log.info(f"Starting to collect antenna IDs from {municipality}")

        while True:
            Actor.log.info(f"Collecting antenna IDs from {municipality}, page {page}")

            response = await self.make_request_with_retry(session, self.search_url, data)
            if not response:
                Actor.log.error(f"Failed to get page {page} for {municipality}")
                break

            soup = BeautifulSoup(response._content, 'html.parser')

            # Check if no results found
            no_results_div = soup.find('div', class_='well')
            if no_results_div and 'Δεν βρέθηκαν αποτελέσματα' in no_results_div.text:
                Actor.log.info(f"No results found for {municipality}")
                break

            # Collect antenna IDs from current page
            page_antenna_ids = await self.collect_antenna_ids_from_page(session, soup)
            all_antenna_ids.extend(page_antenna_ids)
            Actor.log.info(f"Found {len(page_antenna_ids)} antennas on page {page}")

            # Check for next page
            next_page_li = soup.find('li', title='Επόμενη Σελίδα')
            if not next_page_li:
                Actor.log.info(f"No more pages for {municipality}, stopping at page {page}")
                break

            next_page_link = next_page_li.find('a', onclick=True)
            if not next_page_link:
                Actor.log.info(f"No next page link found for {municipality}")
                break

            # Extract next page number
            match = re.search(r"document.myform.startPage.value='(\d+)';", next_page_link['onclick'])
            if not match:
                Actor.log.info(f"Could not extract next page number for {municipality}")
                break

            page = int(match.group(1))
            data["startPage"] = str(page)
            data["myAction"] = "next"

        Actor.log.info(f"Collected {len(all_antenna_ids)} antenna IDs from {municipality}")
        return all_antenna_ids

    async def load_municipalities_from_input(self) -> List[str]:
        """Load municipalities from Actor input."""
        actor_input = await Actor.get_input() or {}
        Actor.log.info(f"Actor input: {actor_input}")

        municipalities = actor_input.get('municipalities', [])
        if isinstance(municipalities, str):
            # If it's a string, treat as comma-separated
            municipalities = [m.strip() for m in municipalities.split(',')]
            Actor.log.info(f"Municipalities from comma-separated string: {municipalities}")

        if not isinstance(municipalities, list):
            Actor.log.warning(f"Expected a list of municipalities, but got {type(municipalities)}")
            municipalities = []

        if not municipalities:
            Actor.log.info("No municipalities provided, using default list")
            municipalities = [
                "Αλμωπίας", "Αμαρουσίου", "Αλεξανδρούπολης",
                "Θεσσαλονίκης", "Αθηναίων", "Αίγινας"
            ]

        return municipalities

async def main_scrape_antennaidsonly():
    async with Actor:
        Actor.log.info("Starting Greek Antenna Scraper - Simplified Version")

        scraper = GreekAntennaScraper()

        # Get municipalities from input
        municipalities = await scraper.load_municipalities_from_input()
        Actor.log.info(f"Will scrape {len(municipalities)} municipalities: {municipalities}")

        async with aiohttp.ClientSession() as session:
            all_antenna_ids = []

            for municipality in municipalities:
                Actor.log.info(f"Collecting antenna IDs from municipality: {municipality}")
                municipality_antenna_ids = await scraper.collect_all_antenna_ids_from_municipality(session, municipality)
                all_antenna_ids.extend(municipality_antenna_ids)
                Actor.log.info(f"Completed collecting from {municipality}: {len(municipality_antenna_ids)} antennas found")

                # Small delay between municipalities
                await asyncio.sleep(2)

            Actor.log.info(f"=== SCRAPING COMPLETE: Collected {len(all_antenna_ids)} unique antenna IDs ===")

            # Push all antenna IDs to dataset
            await Actor.push_data([{"antenna_id": antenna_id} for antenna_id in all_antenna_ids])

if __name__ == "__main__":
    asyncio.run(main_scrape_antennaidsonly())
