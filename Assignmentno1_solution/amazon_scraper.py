"""
Amazon Product Review Scraper  
==============================
Amazon aggressively blocks bots and returns 503/CAPTCHA.
This script provides 3 strategies:

  STRATEGY 1 (requests + rotating UA) — Fastest, fails ~50% due to 503
  STRATEGY 2 (Selenium headless)      — Most reliable, needs Chrome/Firefox
  STRATEGY 3 (Amazon Product API)     — Official, no blocks, requires API key

Run:
    python3 amazon_scraper.py --strategy 1 --asin B09XYZ --pages 10
    python3 amazon_scraper.py --strategy 2 --asin B09XYZ --pages 10
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time, random, re, json, argparse
from datetime import datetime

# ─── USER-AGENT POOL (update quarterly) ──────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

PROXIES = []   # Add rotating proxies: ["http://user:pass@ip:port", ...]


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 1 — Requests with Anti-Bot Headers
# ══════════════════════════════════════════════════════════════════════════════
def get_amazon_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.amazon.in/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "DNT": "1",
    }


def create_amazon_session():
    """Warm up session by visiting Amazon homepage first."""
    session = requests.Session()
    try:
        resp = session.get(
            "https://www.amazon.in/",
            headers={**get_amazon_headers(), "Referer": "https://www.google.com/"},
            timeout=15,
        )
        print(f"  [Session] Amazon home: {resp.status_code} | Cookies: {len(session.cookies)}")
        time.sleep(random.uniform(2, 4))
    except Exception as e:
        print(f"  [Session] Warning: {e}")
    return session


def fetch_amazon_page(session, url, max_retries=5):
    """Fetch with exponential backoff. Key for beating 503."""
    for attempt in range(1, max_retries + 1):
        try:
            proxy = {"http": random.choice(PROXIES), "https": random.choice(PROXIES)} if PROXIES else None
            resp = session.get(url, headers=get_amazon_headers(), proxies=proxy, timeout=20)
            
            if resp.status_code == 200 and "review" in resp.text.lower():
                return resp
            elif resp.status_code == 503:
                wait = (2 ** attempt) + random.uniform(1, 4)
                print(f"\n  [503] Attempt {attempt}/{max_retries}. Backing off {wait:.1f}s...")
                time.sleep(wait)
            elif resp.status_code == 403 or "Robot Check" in resp.text:
                wait = (2 ** attempt) * 2 + random.uniform(2, 6)
                print(f"\n  [CAPTCHA/403] Attempt {attempt}/{max_retries}. Backing off {wait:.1f}s...")
                time.sleep(wait)
            elif resp.status_code == 200 and "captcha" in resp.text.lower():
                print(f"\n  [CAPTCHA page] Amazon wants verification. Use Strategy 2 (Selenium).")
                return None
            else:
                time.sleep(attempt * 3)
        except Exception as e:
            print(f"\n  [Error] {e}. Retry {attempt}/{max_retries}...")
            time.sleep(attempt * 3)
    return None


def parse_amazon_reviews(html):
    """Parse Amazon review HTML into list of dicts."""
    soup = BeautifulSoup(html, "lxml")
    reviews = []
    
    # Main review container
    review_divs = soup.find_all("div", {"data-hook": "review"})
    
    for div in review_divs:
        try:
            r = {}
            
            # Rating
            rating_el = div.find("i", {"data-hook": "review-star-rating"}) or \
                        div.find("i", {"data-hook": "cmps-review-star-rating"})
            if rating_el:
                m = re.search(r"([\d.]+) out of", rating_el.get("class", [""])[0] + " " + rating_el.get_text())
                r["rating"] = float(m.group(1)) if m else None
            
            # Title
            title_el = div.find("a", {"data-hook": "review-title"}) or \
                       div.find("span", {"data-hook": "review-title"})
            r["title"] = title_el.get_text(strip=True).lstrip("1234.5 ").strip() if title_el else ""
            
            # Body
            body_el = div.find("span", {"data-hook": "review-body"})
            r["review_body"] = body_el.get_text(strip=True) if body_el else ""
            
            # Reviewer
            name_el = div.find("span", {"class": "a-profile-name"})
            r["reviewer_name"] = name_el.get_text(strip=True) if name_el else "Anonymous"
            
            # Date
            date_el = div.find("span", {"data-hook": "review-date"})
            r["date"] = date_el.get_text(strip=True) if date_el else ""
            
            # Verified purchase
            verified_el = div.find("span", {"data-hook": "avp-badge"})
            r["verified_purchase"] = "Yes" if verified_el else "No"
            
            # Helpful votes
            helpful_el = div.find("span", {"data-hook": "helpful-vote-statement"})
            if helpful_el:
                m = re.search(r"(\d+)", helpful_el.get_text())
                r["helpful_votes"] = int(m.group(1)) if m else 0
            else:
                r["helpful_votes"] = 0
            
            # Review ID
            r["review_id"] = div.get("id", "")
            
            if r.get("review_body"):
                reviews.append(r)
        except Exception:
            continue
    
    return reviews


def scrape_amazon_strategy1(asin, pages=10, output_file="amazon_reviews_s1.csv", domain="amazon.in"):
    """Strategy 1: Requests-based scraper with anti-bot headers."""
    print(f"\n{'='*60}")
    print(f"  Amazon Review Scraper — Strategy 1 (Requests)")
    print(f"{'='*60}")
    print(f"  ASIN     : {asin}")
    print(f"  Domain   : {domain}")
    print(f"  Pages    : {pages}")
    print(f"{'='*60}\n")
    
    base_url = f"https://www.{domain}/product-reviews/{asin}/ref=cm_cr_arp_d_viewopt_srt?sortBy=recent&pageNumber="
    
    session = create_amazon_session()
    all_reviews = []
    
    for page in range(1, pages + 1):
        url = f"{base_url}{page}"
        print(f"[Page {page:02d}/{pages}] {url[-70:]}...", end=" ", flush=True)
        
        resp = fetch_amazon_page(session, url)
        
        if resp is None:
            print("FAILED. Switching to Strategy 2 recommended.")
            break
        
        reviews = parse_amazon_reviews(resp.text)
        
        if not reviews:
            print(f"0 reviews (page end or blocked).")
            if page > 2:
                break
            continue
        
        all_reviews.extend(reviews)
        print(f"✓ {len(reviews)} reviews | Total: {len(all_reviews)}")
        
        time.sleep(random.uniform(3, 7))  # CRITICAL: longer delays = fewer blocks
    
    _save_reviews(all_reviews, output_file, "Amazon")
    return all_reviews


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 2 — Selenium Headless Browser (Most Reliable)
# ══════════════════════════════════════════════════════════════════════════════
def scrape_amazon_strategy2(asin, pages=10, output_file="amazon_reviews_s2.csv", domain="amazon.in"):
    """
    Strategy 2: Selenium with headless Chrome.
    Install: pip install selenium && apt install chromium-driver
             OR: pip install webdriver-manager
    """
    print(f"\n{'='*60}")
    print(f"  Amazon Review Scraper — Strategy 2 (Selenium)")
    print(f"{'='*60}\n")
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
    except ImportError:
        print("[!] Selenium not installed. Run: pip install selenium")
        return []
    
    options = Options()
    options.add_argument("--headless=new")         # Headless mode
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    options.add_argument("--window-size=1920,1080")
    
    # Optional: stealth mode
    # options.add_argument("--disable-extensions")
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception as e:
        print(f"[!] Chrome not found: {e}")
        print("    Install with: sudo apt install chromium-browser chromium-chromedriver")
        print("    Or: pip install webdriver-manager")
        return []
    
    base_url = f"https://www.{domain}/product-reviews/{asin}/ref=cm_cr_arp_d_viewopt_srt?sortBy=recent&pageNumber="
    all_reviews = []
    
    try:
        # Warm up — visit homepage first
        driver.get(f"https://www.{domain}/")
        time.sleep(random.uniform(2, 4))
        
        for page in range(1, pages + 1):
            url = f"{base_url}{page}"
            print(f"[Page {page:02d}/{pages}] Loading...", end=" ", flush=True)
            
            driver.get(url)
            
            # Wait for reviews to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-hook="review"]'))
                )
            except TimeoutException:
                print(f"Timeout / CAPTCHA.")
                # Take screenshot for debugging
                driver.save_screenshot(f"captcha_page_{page}.png")
                print(f"  Screenshot saved: captcha_page_{page}.png")
                break
            
            # Random scroll to simulate human behavior
            driver.execute_script(f"window.scrollTo(0, {random.randint(300, 800)});")
            time.sleep(random.uniform(0.5, 1.5))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(1, 2))
            
            reviews = parse_amazon_reviews(driver.page_source)
            
            if not reviews:
                print(f"No reviews — end of pages.")
                break
            
            all_reviews.extend(reviews)
            print(f"✓ {len(reviews)} reviews | Total: {len(all_reviews)}")
            
            time.sleep(random.uniform(2, 5))
    
    finally:
        driver.quit()
    
    _save_reviews(all_reviews, output_file, "Amazon")
    return all_reviews


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY 3 — ScraperAPI / Bright Data (Proxy Service)
# ══════════════════════════════════════════════════════════════════════════════
def scrape_via_scraper_api(asin, api_key, pages=10, output_file="amazon_reviews_api.csv"):
    """
    Strategy 3: Use ScraperAPI to bypass all blocks.
    Sign up at: https://www.scraperapi.com (5,000 free credits/month)
    
    Usage: scrape_via_scraper_api("B09XYZ", "YOUR_API_KEY", pages=12)
    """
    print(f"\n[Strategy 3] Using ScraperAPI for ASIN: {asin}")
    
    all_reviews = []
    base_url = f"https://www.amazon.in/product-reviews/{asin}/ref=cm_cr_arp_d_viewopt_srt?sortBy=recent&pageNumber="
    
    for page in range(1, pages + 1):
        target_url = f"{base_url}{page}"
        proxy_url = f"http://scraperapi:{api_key}@proxy-server.scraperapi.com:8001"
        
        try:
            resp = requests.get(
                target_url,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=30,
            )
            reviews = parse_amazon_reviews(resp.text)
            all_reviews.extend(reviews)
            print(f"[Page {page}] {len(reviews)} reviews | Total: {len(all_reviews)}")
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f"[Page {page}] Error: {e}")
    
    _save_reviews(all_reviews, output_file, "Amazon")
    return all_reviews


def _save_reviews(reviews, output_file, platform):
    if not reviews:
        print("\n[!] No reviews to save.")
        return
    df = pd.DataFrame(reviews)
    df["platform"] = platform
    df["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df.to_csv(output_file, index=False, encoding="utf-8")
    print(f"\n[✓] Saved {len(reviews)} reviews → {output_file}")
    if "rating" in df.columns and df["rating"].notna().any():
        print(f"    Avg Rating : {df['rating'].mean():.2f}")
        print(f"    Rating Dist: {df['rating'].value_counts().sort_index().to_dict()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Amazon Review Scraper")
    parser.add_argument("--asin", default="B09W9FND7K", help="Amazon ASIN")
    parser.add_argument("--strategy", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--pages", type=int, default=12)
    parser.add_argument("--output", default="amazon_reviews.csv")
    parser.add_argument("--api-key", default="", help="ScraperAPI key (Strategy 3 only)")
    args = parser.parse_args()
    
    if args.strategy == 1:
        scrape_amazon_strategy1(args.asin, args.pages, args.output)
    elif args.strategy == 2:
        scrape_amazon_strategy2(args.asin, args.pages, args.output)
    elif args.strategy == 3:
        if not args.api_key:
            print("[!] --api-key required for Strategy 3")
        else:
            scrape_via_scraper_api(args.asin, args.api_key, args.pages, args.output)
