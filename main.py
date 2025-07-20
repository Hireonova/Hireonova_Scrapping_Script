import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from collections import deque
import json
import re
import time
import random
from datetime import datetime, timedelta
from termcolor import colored
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, HttpUrl, Field
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc
from urllib.parse import urljoin, urlparse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Pydantic Models for Data Validation ---
class JobPosting(BaseModel):
    """
    Pydantic model to define the structure and validate scraped job data.
    """
    job_title: str
    job_description: str
    job_location: str
    apply_url: HttpUrl = Field(..., description="URL to apply for the job")
    company_image: Optional[HttpUrl] = None
    date_posted: Optional[datetime] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class JobPostingAPI(BaseModel):
    """
    Pydantic model matching the API schema (without job_location)
    """
    job_title: str
    job_description: str = ""
    apply_url: str
    company_image: Optional[str] = None
    date_posted: Optional[datetime] = None

# --- OLLama Integration ---
OLLAMA_API_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "gemma3"

def get_job_details_with_ollama(html_content: str, url: str) -> dict:
    """
    Uses OLLama (Gemma 3) to identify and extract job details from HTML content
    """
    truncated_html = html_content[:8000]

    prompt = f"""
    Analyze the following HTML content from {url} and extract job details.
    Look for:
    - Job Title (most prominent heading for the job)
    - Job Description (the main body of text describing the role, responsibilities, and qualifications)
    - Job Location (e.g., "Remote", "New York", "London, UK")
    - Apply URL (a direct link or button URL to apply for the job, or use the current URL if no direct link)
    - Company Image (URL of the company's logo or a relevant image, if present)
    - Date Posted (the date the job was posted, or "X days/hours ago", try to convert to YYYY-MM-DD if possible)

    Return ONLY a JSON object with these keys. If a field is not found, set it to null.
    Ensure apply_url is a valid URL. If it's a relative URL, make it absolute using the base domain.

    HTML Content:
    {truncated_html}
    """

    headers = {'Content-Type': 'application/json'}
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    try:
        response = requests.post(OLLAMA_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        response_data = response.json()
        
        if 'message' in response_data and 'content' in response_data['message']:
            content_str = response_data['message']['content']
            
            # Clean up markdown formatting
            if content_str.startswith("```json") and content_str.endswith("```"):
                content_str = content_str[7:-3].strip()
            elif content_str.startswith("```") and content_str.endswith("```"):
                content_str = content_str[3:-3].strip()
            
            parsed_data = json.loads(content_str)
            
            # Make apply_url absolute
            if parsed_data.get('apply_url') and not parsed_data['apply_url'].startswith(('http://', 'https://')):
                parsed_data['apply_url'] = urljoin(url, parsed_data['apply_url'])

            # Parse date if provided
            if parsed_data.get('date_posted'):
                parsed_data['date_posted'] = parse_date_string(parsed_data['date_posted'])

            return parsed_data
        else:
            logger.error(f"Invalid OLLama response structure for {url}")
            return {}
            
    except Exception as e:
        logger.error(f"OLLama API error for {url}: {e}")
        return {}

def parse_date_string(date_str: str) -> Optional[datetime]:
    """Parse various date formats"""
    if not date_str:
        return None
        
    try:
        # Try common formats
        for fmt in ("%Y-%m-%d", "%B %d, %Y", "%d %B %Y", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Handle "X days/hours ago"
        time_ago_match = re.search(r'(\d+)\s+(day|hour|week|month|year)s?\s+ago', date_str, re.IGNORECASE)
        if time_ago_match:
            num = int(time_ago_match.group(1))
            unit = time_ago_match.group(2).lower()
            
            if unit == 'day':
                return datetime.now() - timedelta(days=num)
            elif unit == 'hour':
                return datetime.now() - timedelta(hours=num)
            elif unit == 'week':
                return datetime.now() - timedelta(weeks=num)
            elif unit == 'month':
                return datetime.now() - timedelta(days=num * 30)
            elif unit == 'year':
                return datetime.now() - timedelta(days=num * 365)
                
    except Exception as e:
        logger.warning(f"Could not parse date '{date_str}': {e}")
    
    return None

# --- API Integration ---
def push_job_to_api(job_data: dict) -> bool:
    """
    Push job data to the API endpoint
    """
    api_url = "http://localhost:8080/jobs"
    
    try:
        # Transform data to match API schema
        api_job = JobPostingAPI(
            job_title=job_data.get('job_title', ''),
            job_description=job_data.get('job_description', ''),
            apply_url=str(job_data.get('apply_url', '')),
            company_image=job_data.get('company_image'),
            date_posted=job_data.get('date_posted')
        )
        
        # Convert to dict for API
        payload = api_job.model_dump(exclude_none=True)
        if payload.get('date_posted'):
            payload['date_posted'] = payload['date_posted'].isoformat()
        
        response = requests.post(api_url, json=payload, timeout=30)
        response.raise_for_status()
        
        logger.info(f"Successfully pushed job '{job_data.get('job_title')}' to API")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Error pushing job to API: {e}")
        return False

# --- Enhanced Job Scraper Class ---
class EnhancedJobScraper:
    def __init__(self, urls_file: str, delay: int = 3, timeout: int = 20, use_selenium: bool = True):
        self.urls_file = urls_file
        self.ua = UserAgent()
        self.delay = delay
        self.timeout = timeout
        self.use_selenium = use_selenium
        self.scraped_jobs = []
        self.visited_urls = set()
        self.queue = deque()
        self.max_pages_per_domain = 30
        self.driver = None
        self.session = requests.Session()
        self._setup_session()
        
    def _setup_session(self):
        """Setup requests session with anti-blocking measures"""
        self.session.headers.update({
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
    def _get_selenium_driver(self):
        """Setup undetected Chrome driver for JS-heavy sites"""
        if self.driver is None:
            try:
                options = uc.ChromeOptions()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-blink-features=AutomationControlled')
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-plugins')
                options.add_argument('--disable-images')
                options.add_argument('--disable-javascript')  # Can be removed if JS is needed
                
                self.driver = uc.Chrome(options=options)
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
            except Exception as e:
                logger.error(f"Failed to setup Selenium driver: {e}")
                self.use_selenium = False
        
        return self.driver

    def _load_start_urls(self) -> List[str]:
        """Load starting URLs from JSON file"""
        try:
            with open(self.urls_file, 'r') as f:
                data = json.load(f)
                return data.get('urls', [])
        except FileNotFoundError:
            logger.error(f"{self.urls_file} not found")
            return []
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in {self.urls_file}")
            return []

    def _fetch_page_requests(self, url: str) -> Optional[str]:
        """Fetch page using requests with anti-blocking measures"""
        try:
            # Random delay
            time.sleep(random.uniform(self.delay, self.delay + 2))
            
            # Rotate user agent
            self.session.headers['User-Agent'] = self.ua.random
            
            # Add random headers
            if random.choice([True, False]):
                self.session.headers['Referer'] = 'https://www.google.com/'
            
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None

    def _fetch_page_selenium(self, url: str) -> Optional[str]:
        """Fetch page using Selenium for JS-heavy sites"""
        driver = self._get_selenium_driver()
        if not driver:
            return None
            
        try:
            driver.get(url)
            
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Additional wait for dynamic content
            time.sleep(random.uniform(2, 4))
            
            # Scroll to load more content if needed
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            return driver.page_source
            
        except Exception as e:
            logger.error(f"Selenium failed for {url}: {e}")
            return None

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch page with fallback strategy"""
        logger.info(f"Fetching: {url}")
        
        # Try requests first (faster)
        html_content = self._fetch_page_requests(url)
        
        # Fallback to Selenium if requests fails or if we detect JS-heavy content
        if not html_content and self.use_selenium:
            logger.info(f"Trying Selenium for {url}")
            html_content = self._fetch_page_selenium(url)
        
        # Check if page seems to be JS-heavy and retry with Selenium
        if html_content and self.use_selenium:
            if len(html_content) < 1000 or 'loading' in html_content.lower():
                logger.info(f"Page seems JS-heavy, retrying with Selenium for {url}")
                selenium_content = self._fetch_page_selenium(url)
                if selenium_content and len(selenium_content) > len(html_content):
                    html_content = selenium_content
        
        return html_content

    def _extract_links(self, html_content: str, base_url: str) -> List[str]:
        """Extract relevant job-related links"""
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []
        base_domain = urlparse(base_url).netloc
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)
            parsed_url = urlparse(full_url)

            # Same domain and not visited
            if parsed_url.netloc == base_domain and full_url not in self.visited_urls:
                # Job-related patterns
                if re.search(r'/job|/jobs|/careers|/apply|/view|/listing|/posting|/opportunities', 
                           parsed_url.path, re.IGNORECASE):
                    links.append(full_url)
                # Pagination
                elif re.search(r'page=\d+|start=\d+|offset=\d+|p=\d+', parsed_url.query, re.IGNORECASE):
                    links.append(full_url)
                # General job-related URLs
                elif any(keyword in full_url.lower() for keyword in ['job', 'career', 'hiring', 'work', 'position']):
                    links.append(full_url)

        return links[:20]  # Limit to prevent too many links

    def _parse_job_page(self, html_content: str, url: str) -> Optional[dict]:
        """Parse job page to extract job details"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        extracted_data = {
            "job_title": None,
            "job_description": None,
            "job_location": None,
            "apply_url": None,
            "company_image": None,
            "date_posted": None
        }

        # Extract job title
        title_selectors = [
            'h1[class*="title"]', 'h1[class*="job"]', 'h1[class*="position"]',
            'h2[class*="title"]', 'h2[class*="job"]', 'h2[class*="position"]',
            '.job-title', '.position-title', '.title', 'h1', 'h2'
        ]
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem and title_elem.get_text(strip=True):
                extracted_data['job_title'] = title_elem.get_text(strip=True)
                break

        # Extract job description
        desc_selectors = [
            '[class*="description"]', '[class*="job-description"]', '[class*="content"]',
            '[class*="details"]', '[class*="requirements"]', '.description', '.job-content'
        ]
        
        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                desc_text = desc_elem.get_text(separator='\n', strip=True)
                if len(desc_text) > 100:  # Ensure it's substantial
                    extracted_data['job_description'] = desc_text[:2000]  # Limit length
                    break

        # Extract location
        location_selectors = [
            '[class*="location"]', '[class*="address"]', '[class*="remote"]', 
            '.location', '.job-location', '.address'
        ]
        
        for selector in location_selectors:
            location_elem = soup.select_one(selector)
            if location_elem and location_elem.get_text(strip=True):
                extracted_data['job_location'] = location_elem.get_text(strip=True)
                break

        # Extract apply URL
        apply_selectors = [
            'a[href*="apply"]', 'a[class*="apply"]', 'a[class*="button"]',
            '.apply-btn', '.apply-link', '.job-apply'
        ]
        
        for selector in apply_selectors:
            apply_elem = soup.select_one(selector)
            if apply_elem and apply_elem.get('href'):
                extracted_data['apply_url'] = urljoin(url, apply_elem['href'])
                break

        # Default apply URL to current URL if not found
        if not extracted_data['apply_url']:
            extracted_data['apply_url'] = url

        # Extract company image
        img_selectors = [
            'img[src*="logo"]', 'img[class*="logo"]', 'img[class*="company"]',
            '.company-logo img', '.logo img'
        ]
        
        for selector in img_selectors:
            img_elem = soup.select_one(selector)
            if img_elem and img_elem.get('src'):
                extracted_data['company_image'] = urljoin(url, img_elem['src'])
                break

        # Use OLLama to fill missing fields
        mandatory_missing = not all([
            extracted_data['job_title'],
            extracted_data['job_description'],
            extracted_data['job_location']
        ])

        if mandatory_missing:
            logger.info(f"Using OLLama to fill missing fields for {url}")
            ollama_data = get_job_details_with_ollama(html_content, url)
            
            for key in extracted_data:
                if not extracted_data[key] and ollama_data.get(key):
                    extracted_data[key] = ollama_data[key]

        # Final validation
        if not all([extracted_data['job_title'], extracted_data['job_description']]):
            logger.warning(f"Missing mandatory fields for {url}")
            return None

        return extracted_data

    def crawl(self):
        """Main crawling method"""
        start_urls = self._load_start_urls()
        if not start_urls:
            logger.error("No starting URLs found")
            return

        for start_url in start_urls:
            domain = urlparse(start_url).netloc
            self.queue.clear()
            self.visited_urls.clear()
            self.queue.append(start_url)
            self.visited_urls.add(start_url)
            
            pages_crawled = 0
            successful_jobs = 0
            
            logger.info(f"Starting crawl for {domain}")

            while self.queue and pages_crawled < self.max_pages_per_domain:
                current_url = self.queue.popleft()
                
                html_content = self._fetch_page(current_url)
                if html_content:
                    job_data = self._parse_job_page(html_content, current_url)
                    
                    if job_data:
                        # Push to API
                        if push_job_to_api(job_data):
                            successful_jobs += 1
                            self.scraped_jobs.append(job_data)
                            logger.info(f"✓ Job found and pushed: {job_data['job_title']}")
                        else:
                            logger.warning(f"Failed to push job: {job_data['job_title']}")
                    
                    # Extract more links
                    new_links = self._extract_links(html_content, current_url)
                    for link in new_links:
                        if link not in self.visited_urls and len(self.queue) < 50:
                            self.visited_urls.add(link)
                            self.queue.append(link)
                
                pages_crawled += 1
                
                # Add random delay to avoid being blocked
                time.sleep(random.uniform(2, 5))
            
            logger.info(f"Finished {domain}: {successful_jobs} jobs from {pages_crawled} pages")

    def save_jobs_to_json(self, filename: str = "scraped_jobs.json"):
        """Save scraped jobs to JSON file"""
        if self.scraped_jobs:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.scraped_jobs, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"Saved {len(self.scraped_jobs)} jobs to {filename}")
        else:
            logger.warning("No jobs to save")

    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()
        self.session.close()

def main():
    urls_file = 'urls.json'
    
    # Create example URLs file
    try:
        with open(urls_file, 'x') as f:
            json.dump({
                "urls": [
                    "https://remoteok.com/remote-dev-jobs",
                    "https://weworkremotely.com/remote-jobs",
                    "https://stackoverflow.com/jobs",
                    "https://jobs.lever.co/",
                    "https://boards.greenhouse.io/",
                ]
            }, f, indent=2)
        logger.info(f"Created example {urls_file}")
    except FileExistsError:
        pass

    scraper = EnhancedJobScraper(
        urls_file=urls_file,
        delay=3,
        timeout=30,
        use_selenium=True
    )
    
    try:
        scraper.crawl()
        scraper.save_jobs_to_json()
    finally:
        scraper.cleanup()

if __name__ == "__main__":
    main()
