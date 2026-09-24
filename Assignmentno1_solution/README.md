# Product Review Scraper — Amazon & Flipkart

## Why Amazon Returns 503

Amazon uses **AWS WAF + Bot Mitigation** that detects:
- Missing browser fingerprints (TLS fingerprint differs from Chrome)
- Missing cookies from homepage visit
- Too-fast request rates
- Missing JavaScript execution signals

---

## Quick Start

```bash
pip install -r requirements.txt

# Flipkart (put the product URL)
python3 flipkart_scraper.py --url "https://www.flipkart.com/product/p/ITEM123" --pages 12

# Amazon Strategy 1 (requests — fast, may get 503)
python3 amazon_scraper.py --asin B09W9FND7K --strategy 1 --pages 12

# Amazon Strategy 2 (Selenium headless — most reliable)
python3 amazon_scraper.py --asin B09W9FND7K --strategy 2 --pages 12

# Amazon Strategy 3 (ScraperAPI — never blocked)
python3 amazon_scraper.py --asin B09W9FND7K --strategy 3 --api-key YOUR_KEY --pages 12
```

---

## Anti-Block Techniques Used

| Technique | What it does |
|---|---|
| **Rotating User-Agents** | Mimics different browsers per request |
| **Session warm-up** | Visits homepage first to get real cookies |
| **Random delays** | 2–7s gaps between requests (human-like) |
| **Exponential backoff** | On 503: waits 4s, 8s, 16s... before retry |
| **Referer headers** | Makes requests look like they came from within the site |
| **Proxy rotation** | Rotate IPs to avoid IP-level blocks |

---

## Getting an Amazon ASIN

The ASIN is in any Amazon product URL:
```
https://www.amazon.in/dp/B09W9FND7K   ← B09W9FND7K is the ASIN
https://www.amazon.in/product-name/dp/B09W9FND7K
```

---

## If Still Getting Blocked

1. **Add proxies** — Residential proxies from Webshare.io (10 free), BrightData, or Oxylabs
2. **Use ScraperAPI** — scraperapi.com gives 5,000 free credits/month
3. **Increase delays** — Change `random.uniform(3, 7)` to `random.uniform(8, 15)`
4. **Use Selenium** — Strategy 2 executes real JavaScript like a browser
5. **Add CAPTCHA solver** — 2captcha.com API (~$3/1000 solves)

---

## Sample Output (`reviews_sample.csv`)

Pre-generated 120 reviews for testing your analysis pipeline.

Columns:
- `review_id`, `product_name`, `reviewer_name`
- `rating` (1–5), `title`, `review_body`
- `date`, `verified_purchase`, `helpful_votes`
- `location`, `platform`, `scraped_at`
