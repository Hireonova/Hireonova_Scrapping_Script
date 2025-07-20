
# 🚀 Hireonova_Scrapping_Script

Hireonova Scraping Script is a powerful, AI-integrated Python-based job scraper that crawls and scrapes job listings from across the web—including complex, JavaScript-heavy sites. It intelligently navigates through 200K+ pages using advanced heuristics and semantic tools to extract the most relevant job data such as title, company, location, skills, and apply URLs.

---

## 📌 Features

- ✅ Scrapes static and dynamic (JavaScript-rendered) job sites using both `requests` and `Selenium`
- ✅ Dynamically identifies job cards using AI/NLP models (Ollama/Gemma-compatible)
- ✅ Performs BFS-based crawling to locate deep job listing pages
- ✅ Uses User-Agent rotation and IP-safe scraping with `fake-useragent`
- ✅ Automatically extracts structured job data (title, company, skills, etc.)
- ✅ Color-coded terminal output with `termcolor` for better log visibility
- ✅ Supports custom rules for known job boards like RemoteOK, Wellfound, etc.
- ✅ Built-in dark/light compatible frontend integration (React + Tailwind suggested)

---

## 🧱 Project Structure

```
Hireonova_Scrapping_Script/
│
├── main.py                  # Main entry point for scraping jobs
├── requirements.txt         # Python dependencies
├── README.md                # Project documentation
├── utils/
│   ├── nlp_extractor.py     # NLP-based job data extraction
│   └── bfs_crawler.py       # BFS-based URL traversal logic
└── data/
    └── job_results.json     # Saved job data (optional)
```

---

## 📦 Requirements

Make sure you have **Python 3.8+** installed.

Install the required packages:

```bash
pip install -r requirements.txt
```

---

## ⚙️ Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/Hireonova_Scrapping_Script.git
cd Hireonova_Scrapping_Script
```

### 2. (Optional) Create a Virtual Environment

```bash
python -m venv env
source env/bin/activate  # On Windows: env\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 🚀 Running the Scraper

To start scraping, simply run:

```bash
python main.py
```

The scraper will:
- Use BFS to crawl and locate job pages
- Analyze job content with NLP
- Extract and print/save job data
- Output colored logs with job discovery status

---

## 🛠 Technologies Used

| Tool                  | Purpose                                 |
|-----------------------|-----------------------------------------|
| `requests`            | Lightweight static scraping             |
| `beautifulsoup4`      | HTML parsing and DOM traversal          |
| `selenium + undetected_chromedriver` | Dynamic JavaScript rendering |
| `pydantic`            | Schema validation for job entries       |
| `termcolor`           | Enhanced CLI logging                    |
| `fake-useragent`      | User-agent spoofing                     |
| `webdriver-manager`   | Auto manages compatible ChromeDrivers   |

---

## 🔒 Anti-Bot Strategy

- Randomized User-Agent with `fake-useragent`
- Uses `undetected-chromedriver` to bypass bot detection
- Time delay + jitter added between requests
- BFS avoids recursive traps and duplicate paths

---

## 📤 Output Format

Job listings are printed in terminal and can be saved as structured JSON:

```json
{
  "title": "Software Engineer - AI",
  "company": "TechNova Inc.",
  "location": "Remote",
  "skills": ["Python", "LLM", "NLP"],
  "description": "We are looking for...",
  "apply_url": "https://jobs.technova.com/apply/12345"
}
```

---

## 🧠 AI/NLP Integration (Optional but Recommended)

You can plug in **Ollama (Gemma 3B or similar)** to semantically identify job cards and extract key info:

- Run Ollama server locally
- Send HTML blocks to your endpoint like:
  ```python
  response = requests.post("http://localhost:11434/api/gemma", json={"prompt": html_chunk})
  ```

> This improves scraping accuracy especially on unstructured pages.

---

## 📅 Future Enhancements

- [ ] Add resume-matching engine
- [ ] Add support for more job boards
- [ ] Use distributed crawling
- [ ] Connect to MongoDB/PostgreSQL for storage
- [ ] Add CLI arguments and filtering (e.g., role, location)

---

## 👨‍💻 Author

Made with ❤️ by [Nickhil verma]  

---


