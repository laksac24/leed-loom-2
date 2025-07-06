import requests
from bs4 import BeautifulSoup
import nltk
import re
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import time
import google.generativeai as genai
from google.generativeai import types
from flask import Flask, render_template, request, send_file, jsonify
import os
import shutil
import tempfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Download required NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab')

def setup_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")
    
    # For Render deployment
    options.binary_location = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
    
    service = Service(os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver"))
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def scrape_website_info(url):
    driver = None
    try:
        driver = setup_driver()
        driver.get(url)
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        title = soup.title.string.strip() if soup.title else ""

        meta_desc = ""
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_tag and 'content' in meta_tag.attrs:
            meta_desc = meta_tag['content'].strip()

        h1_tags = [h1.get_text(strip=True) for h1 in soup.find_all('h1')]

        links = [a['href'] for a in soup.find_all('a', href=True) if 'about' in a['href'].lower()]
        about_content = ""
        if links:
            about_url = links[0]
            if about_url.startswith('/'):
                base_url = re.match(r'^https?://[^/]+', url).group(0)
                about_url = base_url + about_url
            driver.get(about_url)
            time.sleep(2)
            about_soup = BeautifulSoup(driver.page_source, 'html.parser')
            paragraphs = about_soup.find_all('p')
            about_content = ' '.join(p.get_text() for p in paragraphs)
            about_content = about_content.strip()[:3000]

        homepage_paragraphs = soup.find_all('p')
        homepage_text = ' '.join(p.get_text() for p in homepage_paragraphs)
        homepage_text = homepage_text.strip()[:3000]

        return {
            'title': title,
            'meta_description': meta_desc,
            'h1_tags': h1_tags,
            'about_content': about_content,
            'homepage_text': homepage_text
        }
    except Exception as e:
        print(f"Error scraping website: {e}")
        return {
            'title': url,
            'meta_description': '',
            'h1_tags': [],
            'about_content': '',
            'homepage_text': ''
        }
    finally:
        if driver:
            driver.quit()

def get_main_keywords(text, limit=8):
    text = re.sub(r'[^\w\s]', '', text.lower())
    tokens = word_tokenize(text)
    stop_words = set(stopwords.words('english'))
    words = [word for word in tokens if word.isalpha() and word not in stop_words and len(word) > 2]

    relevant_words = [
        'marketing', 'growth', 'strategy', 'brand', 'experience', 'customers',
        'clients', 'design', 'technology', 'innovation', 'solutions', 'services',
        'campaigns', 'team', 'creative', 'performance', 'development', 'results',
        'insights', 'business', 'products', 'reach', 'digital', 'engagement'
    ]

    filtered = [word for word in words if word in relevant_words]
    frequency = {}
    for word in filtered:
        frequency[word] = frequency.get(word, 0) + 1

    sorted_keywords = sorted(frequency.items(), key=lambda x: x[1], reverse=True)
    return [kw[0] for kw in sorted_keywords[:limit]]

def write_brand_summary(url, keywords, site_info):
    title = site_info['title'] if site_info['title'] else url

    if not keywords:
        return (
            f"{title} is a digital agency helping businesses grow through strategic marketing and performance-driven solutions. "
            f"The team focuses on delivering measurable results through creativity and execution."
        )

    key_areas = keywords[:3]
    support_areas = keywords[3:5] if len(keywords) > 4 else keywords[:2]

    key_text = ", ".join(key_areas)
    support_text = " and ".join(support_areas) if len(support_areas) > 1 else support_areas[0] if support_areas else "various areas"

    return (
        f"{title} is a results-driven digital agency specializing in {key_text}. "
        f"With a strong foundation in {support_text}, "
        f"the agency delivers tailored solutions that align with real business goals."
    )

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index2.html')

@app.route('/predict', methods=['POST'])
def generate_pitch():
    try:
        url = request.form.get('url')
        api_key = request.form.get('API')
        
        if not url or not api_key:
            return jsonify({'error': 'URL and API key are required'}), 400
        
        # Scrape website information
        site_info = scrape_website_info(url)
        combined_text = site_info['about_content'] + " " + site_info['homepage_text']

        if len(combined_text) < 200:
            return jsonify({'error': 'Insufficient content found on the website'}), 400

        keywords = get_main_keywords(combined_text)
        summary = write_brand_summary(url, keywords, site_info)

        # Generate LaTeX code using Gemini
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[summary],
            config=types.GenerateContentConfig(
                max_output_tokens=1000,
                temperature=0.1,
                system_instruction="generate complete latex code to create ppt to pitch to the company. The code should be short and complete. give only code and nothing else."
            )
        )
        
        response2 = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[response.text],
            config=types.GenerateContentConfig(
                max_output_tokens=1000,
                temperature=0.1,
                system_instruction="debug the code. give only code and nothing else."
            )
        )

        # Clean up the LaTeX code
        result = str(response2.text).replace("```latex", "").replace("```", "").strip()
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            tex_file = os.path.join(temp_dir, "pitch.tex")
            pdf_file = os.path.join(temp_dir, "pitch.pdf")
            
            # Write LaTeX file
            with open(tex_file, "w", encoding='utf-8') as f:
                f.write(result)
            
            # Compile LaTeX to PDF
            os.system(f"cd {temp_dir} && pdflatex pitch.tex")
            
            # Check if PDF was created
            if os.path.exists(pdf_file):
                # Move to static directory for serving
                static_dir = os.path.join(app.root_path, 'static')
                os.makedirs(static_dir, exist_ok=True)
                final_pdf = os.path.join(static_dir, 'pitch.pdf')
                shutil.copy2(pdf_file, final_pdf)
                
                return jsonify({'success': True, 'download_url': '/download'})
            else:
                return jsonify({'error': 'Failed to generate PDF'}), 500
                
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/download')
def download_pdf():
    try:
        pdf_path = os.path.join(app.root_path, 'static', 'pitch.pdf')
        if os.path.exists(pdf_path):
            return send_file(pdf_path, as_attachment=True, download_name='company_pitch.pdf')
        else:
            return jsonify({'error': 'PDF file not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)