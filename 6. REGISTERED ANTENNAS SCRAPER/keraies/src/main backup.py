#!/usr/bin/env python3

import asyncio
import re
import time
from typing import Dict, List, Optional, Any, Set

try:
    from apify import Actor
except ImportError:
    print("Warning: apify package not found. Install with: pip install apify")
    # Mock Actor for local testing
    class MockActor:
        class log:
            @staticmethod
            def info(msg): print(f"INFO: {msg}")
            @staticmethod
            def warning(msg): print(f"WARNING: {msg}")
            @staticmethod
            def error(msg): print(f"ERROR: {msg}")
        
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
            import json
            with open('scraped_data.json', 'a', encoding='utf-8') as f:
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
        self.details_url = f"{self.base_url}/getDetails.php"
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

    async def make_request_with_retry(self, session: ClientSession, url: str, data: Dict, max_retries: int = 6) -> Optional[aiohttp.ClientResponse]:
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

    def get_total_pages(self, soup: BeautifulSoup) -> int:
        """Extract total number of pages from pagination."""
        pagination = soup.find("nav")
        if not pagination:
            return 1

        last_page_link = pagination.find("a", title="Τελευταία Σελίδα")
        if last_page_link and "onclick" in last_page_link.attrs:
            try:
                page_num = int(last_page_link["onclick"].split("'")[1])
                Actor.log.info(f"Total pages found: {page_num}")
                return page_num
            except (IndexError, ValueError):
                return 1
        return 1

    def extract_document_data(self, row) -> Dict[str, Any]:
        """Extract data from document table row."""
        cells = row.find_all('td')
        if len(cells) >= 5:
            return {
                'document_number': cells[1].text.strip(),
                'protocol_number': cells[2].text.strip(),
                'type': cells[3].text.strip(),
                'file_url': cells[4].find('a')['href'] if cells[4].find('a') else None
            }
        return {}

    def extract_basic_antenna_data(self, row) -> Optional[Dict[str, Any]]:
        """Extract basic antenna data from table row and return antenna ID."""
        cells = row.find_all("td")
        if len(cells) >= 7:
            # Extract antenna ID from onclick attribute
            pattern = r"document\.myform2\.appId\.value=(\d+);"
            match = re.search(pattern, str(cells[6]))
            antenna_id = match.group(1) if match else None
            
            if antenna_id:
                return {
                    "antenna_id": antenna_id,
                    "serial_number": cells[0].text.strip(),
                    "code": cells[1].text.strip(),
                    "category": cells[2].text.strip(),
                    "company": cells[3].text.strip(),
                    "address": cells[4].text.strip(),
                    "municipality": cells[5].text.strip()
                }
        return None

    async def get_antenna_details(self, session: ClientSession, antenna_id: str) -> Dict[str, Any]:
        """Get detailed information for a specific antenna."""
        Actor.log.info(f"Getting details for antenna ID: {antenna_id}")
        
        data = {"appId": antenna_id}
        
        response = await self.make_request_with_retry(session, self.details_url, data)
        if not response:
            Actor.log.error(f"Failed to get details for antenna {antenna_id}")
            return {"antenna_id": antenna_id, "error": "Failed to fetch details"}

        soup = BeautifulSoup(response._content, 'html.parser')
        
        antenna_data = {
            'antenna_id': antenna_id,
            'address': "-",
            'position_code': 9999999999,
            'municipality': "-",
            'code_name': "-",
            'region': "-",
            'latitude': 0.0,
            'company': "-",
            'longitude': 0.0,
            'permit_status': "-",
            'measurements_eaee': "-",
            'documents': []
        }

        # Find antenna data divs
        antenna_divs = soup.find_all('div', class_='alert alert-info my-alert3')
        
        if antenna_divs:
            # Extract basic information from first div
            if antenna_divs[0].find_all('div', class_='row'):
                rows = antenna_divs[0].find_all('div', class_='row')
                for current_row in range(1, len(rows)):
                    row = rows[current_row]
                    for col in row.find_all('div'):
                        heading_elem = col.find('p', class_='list-group-item-heading')
                        value_elem = col.find('p', class_='list-group-item-heading2')
                        if heading_elem and value_elem:
                            heading = heading_elem.text.strip()
                            value = value_elem.text.strip()
                            
                            # Map Greek field names to English keys
                            field_mapping = {
                                'Διεύθυνση/ Περιγραφή θέσης': 'address',
                                'Κωδικός αριθμός θέσης': 'position_code',
                                'Δήμος': 'municipality',
                                'Κωδική ονομασία': 'code_name',
                                'Περιφέρεια': 'region',
                                'Γεωγρ. πλάτος (WGS84)': 'latitude',
                                'Εταιρία': 'company',
                                'Γεωγρ. μήκος (WGS84)': 'longitude'
                            }
                            
                            if heading in field_mapping:
                                key = field_mapping[heading]
                                if key in ['latitude', 'longitude']:
                                    try:
                                        antenna_data[key] = float(value)
                                    except ValueError:
                                        antenna_data[key] = 0.0
                                elif key == 'position_code':
                                    try:
                                        antenna_data[key] = int(value)
                                    except ValueError:
                                        antenna_data[key] = 9999999999
                                else:
                                    antenna_data[key] = value

            # Extract permit status from second div
            if len(antenna_divs) > 1:
                mytext_elem = antenna_divs[1].find('div', class_='mytext')
                if mytext_elem:
                    antenna_data['permit_status'] = mytext_elem.text.strip()
                
                measurements_elem = antenna_divs[1].find('div', class_='list-group-item-heading2')
                if measurements_elem:
                    antenna_data['measurements_eaee'] = str(measurements_elem)

            # Extract documents from third div
            if len(antenna_divs) > 2:
                tables = antenna_divs[2].find_all('table', class_='my-table')
                documents_list = []
                for table in tables:
                    document_rows = table.find_all('tr')[1:]  # Skip header
                    for doc_row in document_rows:
                        doc_data = self.extract_document_data(doc_row)
                        if doc_data:
                            documents_list.append(doc_data)
                antenna_data['documents'] = documents_list

        return antenna_data

    async def collect_antenna_ids_from_page(self, session: ClientSession, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Collect antenna IDs and basic data from a single page."""
        table = soup.find("table", class_="table table-striped table-condensed table-responsive")
        if not table:
            return []

        antenna_data_list = []
        
        for row in table.find_all("tr")[1:]:  # Skip header row
            basic_data = self.extract_basic_antenna_data(row)
            if basic_data:
                antenna_data_list.append(basic_data)

        return antenna_data_list

    async def collect_all_antenna_ids_from_municipality(self, session: ClientSession, municipality: str) -> List[Dict[str, Any]]:
        """Collect all antenna IDs from all pages of a municipality."""
        all_antenna_data = []
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
            page_antenna_data = await self.collect_antenna_ids_from_page(session, soup)
            all_antenna_data.extend(page_antenna_data)
            Actor.log.info(f"Found {len(page_antenna_data)} antennas on page {page}")
            
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

        Actor.log.info(f"Collected {len(all_antenna_data)} antenna IDs from {municipality}")
        return all_antenna_data

    async def load_municipalities_from_input(self) -> List[str]:
        """Load municipalities from Actor input."""
        actor_input = await Actor.get_input() or {}
        
        municipalities = actor_input.get('municipalities', [])
        if isinstance(municipalities, str):
            # If it's a string, treat as comma-separated
            municipalities = [m.strip() for m in municipalities.split(',')]
        
        # Default municipalities if none provided
        if not municipalities:
            municipalities = [
                "Αλμωπίας", "Αμαρουσίου", "Αλεξανδρούπολης", 
                "Θεσσαλονίκης", "Αθηναίων", "Αίγινας"
            ]
        
        return municipalities


async def main():
    async with Actor:
        Actor.log.info("Starting Greek Antenna Scraper - Two Stage Process")
        
        scraper = GreekAntennaScraper()
        
        # Get municipalities from input
        municipalities = await scraper.load_municipalities_from_input()
        Actor.log.info(f"Will scrape {len(municipalities)} municipalities: {municipalities}")
        
        async with aiohttp.ClientSession() as session:
            
            # STAGE 1: Collect all antenna IDs from all municipalities
            Actor.log.info("=== STAGE 1: Collecting all antenna IDs from municipalities ===")
            all_basic_antenna_data = []
            unique_antenna_ids = set()
            
            for municipality in municipalities:
                Actor.log.info(f"Collecting antenna IDs from municipality: {municipality}")
                municipality_antenna_data = await scraper.collect_all_antenna_ids_from_municipality(session, municipality)
                
                # Add to our collection and track unique IDs
                for antenna_data in municipality_antenna_data:
                    antenna_id = antenna_data.get('antenna_id')
                    if antenna_id and antenna_id not in unique_antenna_ids:
                        unique_antenna_ids.add(antenna_id)
                        all_basic_antenna_data.append(antenna_data)
                
                Actor.log.info(f"Completed collecting from {municipality}: {len(municipality_antenna_data)} antennas found")
                
                # Small delay between municipalities
                await asyncio.sleep(2)
            
            Actor.log.info(f"=== STAGE 1 COMPLETE: Collected {len(unique_antenna_ids)} unique antenna IDs ===")
            
            # STAGE 2: Get detailed information for each antenna
            Actor.log.info("=== STAGE 2: Getting detailed information for each antenna ===")
            all_detailed_results = []
            
            for i, basic_data in enumerate(all_basic_antenna_data):
                antenna_id = basic_data['antenna_id']
                Actor.log.info(f"Processing antenna {i+1}/{len(all_basic_antenna_data)}: ID {antenna_id}")
                
                # Get detailed information
                detailed_data = await scraper.get_antenna_details(session, antenna_id)
                
                # Merge basic data with detailed data
                combined_data = {
                    **basic_data,  # Basic data from stage 1
                    **detailed_data  # Detailed data from stage 2
                }
                
                all_detailed_results.append(combined_data)
                
                # Small delay to be respectful to the server
                await asyncio.sleep(1)
                
                # Push data in batches of 50 to avoid memory issues
                if len(all_detailed_results) % 50 == 0:
                    Actor.log.info(f"Pushing batch of results to dataset (processed {len(all_detailed_results)} so far)")
                    await Actor.push_data(all_detailed_results[-50:])
            
            # Push any remaining results
            if len(all_detailed_results) % 50 != 0:
                remaining_count = len(all_detailed_results) % 50
                Actor.log.info(f"Pushing final batch of {remaining_count} results to dataset")
                await Actor.push_data(all_detailed_results[-remaining_count:])
            
            Actor.log.info(f"=== SCRAPING COMPLETE: Successfully processed {len(all_detailed_results)} antennas ===")
            Actor.log.info(f"Total municipalities processed: {len(municipalities)}")
            Actor.log.info(f"Total unique antennas found: {len(unique_antenna_ids)}")


if __name__ == "__main__":
    asyncio.run(main())