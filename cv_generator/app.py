import streamlit as st
import fitz  # PyMuPDF
import os
import subprocess
import json
import re  # Added for regex cleaning
import google.generativeai as genai
from jinja2 import Environment, FileSystemLoader

# --- CONFIGURATION ---
TEMPLATE_FILE = "cv_template.tex"
BUILD_DIR = "build"
os.makedirs(BUILD_DIR, exist_ok=True)

# --- JINJA2 SETUP ---
env = Environment(
    loader=FileSystemLoader('.'),
    block_start_string='\BLOCK{',
    block_end_string='}',
    variable_start_string='\VAR{',
    variable_end_string='}',
    comment_start_string='\#{',
    comment_end_string='}',
    trim_blocks=True,
    autoescape=False,
)

def clean_json_string(json_str):
    """
    Cleans the AI response to ensure it's valid JSON.
    Removes markdown code blocks (```json ... ```).
    """
    # Remove ```json and ``` at the start/end
    cleaned = re.sub(r'^```json\s*', '', json_str, flags=re.MULTILINE)
    cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE)
    return cleaned.strip()

def get_ai_data(api_key, raw_text):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Act as a professional resume writer. Extract data from the text below and return strict JSON.
    Do not use Markdown formatting. Do not include ```json fences. Just return the raw JSON object.
    
    JSON Structure:
    {{
        "name": "Full Name",
        "title": "Current Job Title",
        "email": "Email",
        "phone": "Phone",
        "linkedin": "LinkedIn URL",
        "portfolio": "Portfolio URL",
        "summary": "Professional summary (max 300 chars)",
        "skills_hard": "List of hard skills",
        "skills_tools": "List of tools",
        "skills_soft": "List of soft skills",
        "experience": [ {{ "role": "...", "company": "...", "dates": "...", "bullets": ["...", "..."] }} ],
        "education": [ {{ "degree": "...", "institution": "...", "year": "...", "grade": "..." }} ],
        "projects": [ {{ "name": "...", "description": "..." }} ]
    }}

    RAW TEXT:
    {raw_text}
    """
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    
    # DEBUG: Print what AI sent back to the logs
    print("AI RESPONSE RAW:", response.text)
    
    try:
        return json.loads(clean_json_string(response.text))
    except json.JSONDecodeError as e:
        st.error(f"JSON Error: The AI return invalid data. Raw data: {response.text}")
        raise e

def compile_latex(data, photo_filename):
    # Logic: Tell LaTeX if we have a photo or not
    if photo_filename and os.path.exists(os.path.join(BUILD_DIR, photo_filename)):
        data['show_photo'] = True
        data['photo_path'] = photo_filename
    else:
        data['show_photo'] = False
        data['photo_path'] = ""

    template = env.get_template(TEMPLATE_FILE)
    latex_content = template.render(data)

    tex_path = os.path.join(BUILD_DIR, "resume.tex")
    with open(tex_path, "w") as f:
        f.write(latex_content)

    try:
        # Run pdflatex
        cmd = ["pdflatex", "-output-directory", BUILD_DIR, "-interaction=nonstopmode", tex_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            st.error("LaTeX Error Log:")
            st.text(result.stdout[-1000:]) # Show last 1000 chars of log
            st.error(result.stderr)
            return None
            
    except FileNotFoundError:
        st.error("CRITICAL ERROR: 'pdflatex' not found. Did you add packages.txt?")
        return None

    return os.path.join(BUILD_DIR, "resume.pdf")

# --- UI ---
st.set_page_config(page_title="AI CV Generator")
st.title("📄 Instant CV Standardizer (Debug Mode)")

api_key = st.sidebar.text_input("Gemini API Key", type="password")

uploaded_cv = st.file_uploader("Upload CV (PDF)", type=["pdf"])
uploaded_photo = st.file_uploader("Upload Photo (JPG/PNG)", type=["jpg", "jpeg", "png"])

if st.button("Generate CV") and uploaded_cv and api_key:
    with st.spinner("Processing..."):
        # 1. Extract Text
        doc = fitz.open(stream=uploaded_cv.read(), filetype="pdf")
        text = "".join([page.get_text() for page in doc])
        
        # 2. AI
        try:
            cv_data = get_ai_data(api_key, text)
        except Exception as e:
            st.stop()
            
        # 3. Photo
        photo_name = None
        if uploaded_photo:
            photo_name = "user_photo.jpg"
            with open(os.path.join(BUILD_DIR, photo_name), "wb") as f:
                f.write(uploaded_photo.getbuffer())

        # 4. Compile
        pdf_path = compile_latex(cv_data, photo_name)
        
        if pdf_path:
            with open(pdf_path, "rb") as f:
                st.download_button("Download PDF", f, "cv.pdf", "application/pdf")
