import streamlit as st
import fitz  # PyMuPDF
import os
import subprocess
import json
import google.generativeai as genai
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

# --- CONFIGURATION ---
TEMPLATE_FILE = "cv_template.tex"
BUILD_DIR = "build"

# Ensure build directory exists
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
    line_statement_prefix='%%',
    line_comment_prefix='%#',
    trim_blocks=True,
    autoescape=False,
)

# --- FUNCTIONS ---
def extract_text_from_pdf(uploaded_file):
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def get_ai_data(api_key, raw_text):
    """
    Sends the raw text to Gemini and gets structured JSON back.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are an expert HR assistant. Extract the resume details from the text below 
    and format them into this exact JSON structure. 
    Summarize descriptions to fit a 1-page CV.
    
    JSON Structure required:
    {{
        "name": "...",
        "title": "...",
        "email": "...",
        "phone": "...",
        "linkedin": "...",
        "portfolio": "...",
        "summary": "...",
        "skills_hard": "...",
        "skills_tools": "...",
        "skills_soft": "...",
        "experience": [
            {{ "role": "...", "company": "...", "dates": "...", "bullets": ["...", "..."] }}
        ],
        "education": [
            {{ "degree": "...", "institution": "...", "year": "...", "grade": "..." }}
        ],
        "projects": [
            {{ "name": "...", "description": "..." }}
        ]
    }}

    RAW TEXT:
    {raw_text}
    """
    
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    return json.loads(response.text)

def compile_latex(data, photo_filename):
    # 1. Update data with the correct photo path for LaTeX
    # LaTeX needs absolute paths or paths relative to execution. 
    # Since we run pdflatex in the root, 'build/photo.jpg' works if passed correctly.
    data['photo_path'] = photo_filename

    # 2. Render Template
    template = env.get_template(TEMPLATE_FILE)
    latex_content = template.render(data)

    # 3. Save .tex file
    tex_path = os.path.join(BUILD_DIR, "resume.tex")
    with open(tex_path, "w") as f:
        f.write(latex_content)

    # 4. Compile PDF
    # We run it twice to ensure layout is correct
    try:
        subprocess.run(["pdflatex", "-output-directory", BUILD_DIR, tex_path], check=True)
    except subprocess.CalledProcessError as e:
        st.error("LaTeX Compilation Failed! Check the logs.")
        return None

    return os.path.join(BUILD_DIR, "resume.pdf")

# --- APP UI ---
st.set_page_config(page_title="One-Page CV Generator", layout="wide")

st.title("📄 AI Resume Standardizer")
st.markdown("Upload a raw CV + Photo, and get a perfect 1-page PDF back.")

# Sidebar for API Key
api_key = st.sidebar.text_input("Gemini API Key", type="password")
if not api_key:
    st.sidebar.warning("Please enter your API Key to proceed.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Upload")
    uploaded_cv = st.file_uploader("Upload Current CV (PDF)", type=["pdf"])
    uploaded_photo = st.file_uploader("Upload Photo (JPG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded_cv and uploaded_photo and api_key:
    if st.button("Generate One-Page CV"):
        with st.spinner("Analyzing text with AI..."):
            # 1. Extract Text
            raw_text = extract_text_from_pdf(uploaded_cv)
            
            # 2. Get JSON from AI
            try:
                cv_data = get_ai_data(api_key, raw_text)
                st.success("Analysis Complete!")
            except Exception as e:
                st.error(f"AI Error: {e}")
                st.stop()

            # 3. Save Photo for LaTeX
            photo_path = os.path.join(BUILD_DIR, "user_photo.jpg")
            with open(photo_path, "wb") as f:
                f.write(uploaded_photo.getbuffer())

            # 4. Compile
            with st.spinner("Compiling PDF..."):
                pdf_path = compile_latex(cv_data, "user_photo.jpg")

            # 5. Show Download
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        label="Download Formatted CV",
                        data=f,
                        file_name="Formatted_CV.pdf",
                        mime="application/pdf"
                    )
                
                # Preview
                st.subheader("Preview")
                st.image(photo_path, width=100)
                st.json(cv_data)
