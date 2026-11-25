import os
import sqlite3
import time
import requests
from playwright.sync_api import sync_playwright

DB_PATH = "/app/data/waec_archive.db"
IMAGE_DIR = "/app/data/images"

TARGET_SUBJECTS = ["Further Mathematics"]

def init_db():
    os.makedirs(IMAGE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            paper_title TEXT,
            question_num TEXT,
            question_text TEXT,
            answer_text TEXT,
            q_image_path TEXT,
            a_image_path TEXT
        )
    """)
    conn.commit()
    conn.close()

def download_image(img_url, base_url):
    if not img_url:
        return None
    try:
        # Resolve relative URLs to absolute URLs
        if not img_url.startswith("http"):
            from urllib.parse import urljoin
            img_url = urljoin(base_url, img_url)
            
        response = requests.get(img_url, timeout=15)
        if response.status_code == 200:
            filename = os.path.basename(img_url.split("?")[0])
            local_path = os.path.join(IMAGE_DIR, filename)
            with open(local_path, "wb") as f:
                f.write(response.content)
            return os.path.join("images", filename)
    except Exception as e:
        print(f"Failed to download image {img_url}: {e}")
    return None

def run_scraper():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("https://waeconline.org.ng/e-learning/index.htm", timeout=60000)

        for subject_name in TARGET_SUBJECTS:
            try:
                subject_link = page.locator(f"a:has-text('{subject_name}')").first
                if not subject_link.is_visible():
                    continue
                
                subject_link.click()
                page.wait_for_load_state("networkidle")
                
                paper_elements = page.locator("a[href*='html']").all()
                paper_urls = []
                for el in paper_elements:
                    href = el.get_attribute("href")
                    text = el.inner_text()
                    if href and ("WASSCE" in text or "Paper" in text or "Series" in text):
                        full_url = page.url[:page.url.rfind('/') + 1] + href
                        if full_url not in paper_urls:
                            paper_urls.append((text.strip(), full_url))

                for paper_title, paper_url in paper_urls:
                    try:
                        page.goto(paper_url, timeout=30000)
                        page.wait_for_load_state("networkidle")

                        question_tabs = page.locator("a").all()
                        q_links = []
                        for tab in question_tabs:
                            href = tab.get_attribute("href")
                            text = tab.inner_text().strip()
                            if href and ('jq' in href or text.isdigit()):
                                q_url = page.url[:page.url.rfind('/') + 1] + href
                                if q_url not in q_links:
                                    q_links.append((text, q_url))

                        for q_num, q_url in q_links:
                            if not q_num.isdigit():
                                continue
                            
                            page.goto(q_url, timeout=30000)
                            
                            q_box = page.locator(".question-box, div:has-text('QUESTION')").first
                            q_text = q_box.inner_text() if q_box.is_visible() else ""
                            q_img_el = q_box.locator("img").first if q_box.is_visible() else None
                            q_img_src = q_img_el.get_attribute("src") if q_img_el and q_img_el.is_visible() else None

                            obs_box = page.locator(".observation-box, div:has-text('Observation')").first
                            obs_text = obs_box.inner_text() if obs_box.is_visible() else ""
                            obs_img_el = obs_box.locator("img").first if obs_box.is_visible() else None
                            obs_img_src = obs_img_el.get_attribute("src") if obs_img_el and obs_img_el.is_visible() else None

                            # Download images locally for offline use
                            local_q_img = download_image(q_img_src, q_url)
                            local_a_img = download_image(obs_img_src, q_url)

                            cursor.execute("""
                                INSERT INTO questions (subject, paper_title, question_num, question_text, answer_text, q_image_path, a_image_path)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (subject_name, paper_title, f"QUESTION {q_num}", q_text, obs_text, local_q_img, local_a_img))
                            conn.commit()

                            time.sleep(0.3)

                    except Exception as paper_err:
                        print(f"Error processing paper {paper_title}: {paper_err}")

                page.goto("https://waeconline.org.ng/e-learning/index.htm", timeout=60000)

            except Exception as subj_err:
                print(f"Error processing subject {subject_name}: {subj_err}")

        browser.close()
    conn.close()
    print("Offline asset scraping completed.")

if __name__ == "__main__":
    run_scraper()
