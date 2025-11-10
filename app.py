"""Streamlit PDF Translation App - With Supabase Auth"""
import streamlit as st
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from translate_haiku_100 import process_pdf
from auth import require_auth, display_user_info, get_user_id
from supabase_client import get_supabase_client
from anthropic_translator import translate_with_haiku

# Configuration constants
HAIKU_PRICE_INPUT_PER_1M = 0.80
HAIKU_PRICE_OUTPUT_PER_1M = 4.00

# Helper functions
def sanitize_filename(filename):
    """Sanitize filename for Windows file system compatibility"""
    if not filename:
        return filename
    # Already sanitized by anthropic_translator, but double-check for Windows invalid chars
    for char in '<>:"/\\|?*':
        filename = filename.replace(char, '_')
    return filename

def translate_filenames_batch(filenames, api_key, source_lang, target_lang):
    """Translate multiple filenames in a single API call.

    Args:
        filenames: Dict of {index: filename_without_extension}
        api_key: Anthropic API key
        source_lang: Source language
        target_lang: Target language

    Returns:
        Dict of {index: translated_filename} or empty dict on error
    """
    try:
        result = translate_with_haiku(filenames, api_key, source_lang, target_lang)
        # Sanitize translated filenames for Windows filesystem
        sanitized = {k: sanitize_filename(v) for k, v in result["translations"].items()}
        return {
            "translations": sanitized,
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"]
        }
    except Exception as e:
        print(f"Batch filename translation failed: {e}")
        return {"translations": {}, "input_tokens": 0, "output_tokens": 0}

def log_translation_to_database(supabase, user_id, file_info):
    """Log translation to Supabase database.

    Args:
        supabase: Supabase client
        user_id: User ID
        file_info: Dict with translation details

    Returns:
        True if logged successfully, False otherwise
    """
    try:
        supabase.log_translation(
            user_id=user_id,
            original_filename=file_info["original_filename"],
            translated_filename=file_info["translated_filename"],
            input_tokens=file_info["input_tokens"],
            output_tokens=file_info["output_tokens"],
            file_size_bytes=file_info.get("file_size_bytes"),
            status=file_info.get("status", "completed")
        )
        return True
    except Exception as e:
        print(f"Database logging failed: {e}")
        return False

# Configure page
st.set_page_config(
    page_title="PDF Translator FR→EN",
    page_icon="📄",
    layout="centered"
)

# Require authentication (or allow local mode if Supabase not configured)
require_auth()

# Create necessary directories based on user
user_id = get_user_id()
if user_id:
    # Authenticated user - use user-specific folder
    USER_DIR = Path("user_files") / user_id
    UPLOAD_DIR = USER_DIR / "uploads"
    OUTPUT_DIR = USER_DIR / "translated"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
else:
    # Local testing mode - use shared folder
    UPLOAD_DIR = Path("uploads")
    OUTPUT_DIR = Path("translated_pdfs")
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

# Title
st.title("AI PDF Translator")
st.markdown("Translate PDF documents between multiple languages")

# Warning
st.warning("⚠️ Important: AI-powered translation may not be 100% accurate. Always double-check critical information.")

# Get API key from environment
api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if api_key:
    st.session_state["anthropic_api_key"] = api_key

# Sidebar
with st.sidebar:
    # Display logo
    logo_path = Path("MSDL_Logo_Noir_RGB_HR.png")
    if logo_path.exists():
        st.image(str(logo_path), width="stretch")
        # Add custom CSS to remove rounded corners
        st.markdown("""
        <style>
        [data-testid="stImage"] img {
            border-radius: 0px !important;
        }
        </style>
        """, unsafe_allow_html=True)

    st.divider()
    st.header("⚙️ How it works")
    st.markdown("""
    1. **Upload** French PDF(s)
    2. **Click** Batch Translate
    3. **Download** translated PDFs
    """)

    # Display user info and logout button if authenticated
    display_user_info()

# Main area
tab1, tab2, tab3 = st.tabs(["📤 Upload & Translate", "📁 Files", "📊 History"])

with tab1:
    st.header("Upload PDFs")

    # Language selection
    col_lang1, col_lang2 = st.columns(2)
    with col_lang1:
        source_lang = st.selectbox(
            "Source Language",
            ["French", "English", "Spanish"],
            index=0,
            help="Language of the PDF to translate"
        )
    with col_lang2:
        target_lang = st.selectbox(
            "Target Language",
            ["English", "French", "Spanish"],
            index=0,
            help="Language to translate to"
        )

    # Validate language selection
    if source_lang == target_lang:
        st.error(f"⚠️ Source and target languages must be different. You selected {source_lang} → {target_lang}")

    uploaded_files = st.file_uploader(
        f"Choose {source_lang} PDF files",
        type=['pdf'],
        accept_multiple_files=True,
        help=f"Upload one or more PDFs in {source_lang}"
    )

    if uploaded_files:
        st.success(f"✅ Uploaded {len(uploaded_files)} file(s)")

        # Show uploaded files
        for uploaded_file in uploaded_files:
            st.text(f"📄 {uploaded_file.name}")

        st.divider()

        # Initialize translation state
        if "is_translating" not in st.session_state:
            st.session_state.is_translating = False
        if "translation_completed" not in st.session_state:
            st.session_state.translation_completed = False

        # Only show batch translate section if translation hasn't been completed
        if not st.session_state.translation_completed:
            st.header(f"Batch Translate ({source_lang} → {target_lang})")

            # Batch translate button - disabled during translation
            button_disabled = st.session_state.is_translating or source_lang == target_lang
            if st.button("🤖 Batch Translate All Files", type="primary", width="stretch", disabled=button_disabled):
                if source_lang == target_lang:
                    st.error("❌ Cannot translate: Source and target languages are the same!")
                elif not st.session_state.get("anthropic_api_key"):
                    st.error("❌ API Key not found! Set ANTHROPIC_API_KEY environment variable on Render.")
                else:
                    # Set translation state to true
                    st.session_state.is_translating = True
                    import shutil
                    import time

                    start_time = time.time()
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    timer_text = st.empty()

                    total_files = len(uploaded_files)
                    completed = 0
                    total_input_tokens = 0
                    total_output_tokens = 0

                    # Step 1: Batch translate ALL filenames in one API call
                    status_text.text("🔤 Translating filenames...")
                    progress_bar.progress(0.05)

                    filenames_to_translate = {
                        f"file_{idx}": uploaded_file.name.replace('.pdf', '')
                        for idx, uploaded_file in enumerate(uploaded_files)
                    }

                    filename_result = translate_filenames_batch(
                        filenames_to_translate,
                        st.session_state["anthropic_api_key"],
                        source_lang,
                        target_lang
                    )

                    translated_filenames = filename_result["translations"]
                    total_input_tokens += filename_result["input_tokens"]
                    total_output_tokens += filename_result["output_tokens"]

                    # Step 2: Process each file
                    for idx, uploaded_file in enumerate(uploaded_files):
                        # Calculate progress for this file (filenames done = 5%, files start at 10%)
                        file_base_progress = 0.1 + (idx / total_files) * 0.9
                        file_progress_range = 0.9 / total_files

                        # Save uploaded file
                        elapsed = time.time() - start_time
                        timer_text.text(f"⏱️ Elapsed time: {elapsed:.1f}s")
                        status_text.text(f"📥 Uploading {uploaded_file.name}...")
                        progress_bar.progress(file_base_progress + file_progress_range * 0.1)

                        input_path = UPLOAD_DIR / f"temp_input_{idx}.pdf"
                        with open(input_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())

                        output_path = OUTPUT_DIR / f"temp_output_{idx}.pdf"

                        try:
                            # Translate PDF content
                            status_text.text(f"🤖 Translating {uploaded_file.name}...")

                            def update_progress(progress_value):
                                # Update both progress bar and elapsed time
                                overall_progress = file_base_progress + (file_progress_range * progress_value)
                                progress_bar.progress(overall_progress)
                                elapsed = time.time() - start_time
                                timer_text.text(f"⏱️ Elapsed time: {elapsed:.1f}s")

                            success, input_tokens, output_tokens = process_pdf(
                                str(input_path),
                                str(output_path),
                                st.session_state["anthropic_api_key"],
                                source_lang=source_lang,
                                target_lang=target_lang,
                                progress_callback=update_progress
                            )

                            if success:
                                # Get translated filename from batch (or use original as fallback)
                                file_key = f"file_{idx}"
                                translated_name = translated_filenames.get(
                                    file_key,
                                    uploaded_file.name.replace('.pdf', '')  # Fallback to original
                                )

                                # Move to final location
                                final_output_name = f"{translated_name}.pdf"
                                final_output_path = OUTPUT_DIR / final_output_name
                                shutil.move(str(output_path), str(final_output_path))

                                completed += 1
                                total_input_tokens += input_tokens
                                total_output_tokens += output_tokens

                                # Log to database if Supabase is configured
                                user_id = get_user_id()
                                if user_id and st.session_state.get("supabase"):
                                    file_size = uploaded_file.size if hasattr(uploaded_file, 'size') else None
                                    logged = log_translation_to_database(
                                        st.session_state.supabase,
                                        user_id,
                                        {
                                            "original_filename": uploaded_file.name,
                                            "translated_filename": final_output_name,
                                            "input_tokens": input_tokens,
                                            "output_tokens": output_tokens,
                                            "file_size_bytes": file_size,
                                            "status": "completed"
                                        }
                                    )
                                    if not logged:
                                        st.warning(f"⚠️ {uploaded_file.name}: Translation completed but history wasn't saved")

                                # Show tokens for this file
                                file_tokens = input_tokens + output_tokens
                                st.success(f"✅ {uploaded_file.name}: {file_tokens:,} tokens ({input_tokens:,} in + {output_tokens:,} out)")

                                # Update progress to 100% for this file
                                progress_bar.progress((idx + 1) / total_files)
                            else:
                                st.warning(f"⚠️ {uploaded_file.name} needs manual translation - check console")

                                # Update progress even if failed
                                progress_bar.progress((idx + 1) / total_files)

                        except Exception as e:
                            st.error(f"❌ Failed to translate {uploaded_file.name}: {e}")
                            # Update progress even on error
                            progress_bar.progress((idx + 1) / total_files)
                            continue

                    # Final time
                    total_time = time.time() - start_time
                    minutes = int(total_time // 60)
                    seconds = total_time % 60

                    if minutes > 0:
                        time_str = f"{minutes}m {seconds:.1f}s"
                    else:
                        time_str = f"{seconds:.1f}s"

                    # Calculate cost
                    total_tokens = total_input_tokens + total_output_tokens
                    cost_input = (total_input_tokens / 1_000_000) * HAIKU_PRICE_INPUT_PER_1M
                    cost_output = (total_output_tokens / 1_000_000) * HAIKU_PRICE_OUTPUT_PER_1M
                    total_cost = cost_input + cost_output

                    # Show final summary
                    status_text.text("")
                    timer_text.text(f"⏱️ Total time: {time_str}")
                    progress_bar.empty()

                    st.success(f"✅ Batch translation complete! Processed {completed}/{total_files} files in {time_str}")

                    # Show token usage (cost hidden but still logged to database)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Tokens", f"{total_tokens:,}")
                    with col2:
                        st.metric("Input", f"{total_input_tokens:,}")
                    with col3:
                        st.metric("Output", f"{total_output_tokens:,}")

                    st.info("📁 Check the 'Files' tab to download your translated PDFs")

                    # Reset translation state and mark as completed
                    st.session_state.is_translating = False
                    st.session_state.translation_completed = True
        else:
            # Translation completed - show summary and allow uploading new files
            st.success("Translation complete! Your files are ready in the 'Files' tab.")

            if st.button("Upload New Files", type="primary", width="stretch"):
                st.session_state.translation_completed = False
                st.rerun()

with tab2:
    st.header("📁 Translated Files")

    if OUTPUT_DIR.exists():
        pdf_files = list(OUTPUT_DIR.glob("*.pdf"))

        if pdf_files:
            for pdf_file in sorted(pdf_files, key=lambda x: x.stat().st_mtime, reverse=True):
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    st.markdown(f"**{pdf_file.name}**")

                with col2:
                    size_mb = pdf_file.stat().st_size / 1024 / 1024
                    st.text(f"{size_mb:.2f} MB")

                with col3:
                    with open(pdf_file, "rb") as f:
                        st.download_button(
                            label="Download",
                            data=f,
                            file_name=pdf_file.name,
                            mime="application/pdf",
                            key=str(pdf_file)
                        )
        else:
            st.info("No translated files yet")

with tab3:
    st.header("📊 Translation History")

    # Only show history if Supabase is configured and user is authenticated
    user_id = get_user_id()
    if user_id and st.session_state.get("supabase"):
        # Get user stats
        try:
            stats = st.session_state.supabase.get_user_stats(user_id)

            # Display statistics (cost hidden from UI but tracked in database)
            st.subheader("Your Statistics")
            col1, col2 = st.columns(2)

            with col1:
                st.metric("Total Translations", stats.get("total_translations", 0))
            with col2:
                st.metric("Total Tokens", f"{stats.get('total_tokens_used', 0):,}")

            st.divider()

            # Get translation history
            translations = st.session_state.supabase.get_user_translations(user_id, limit=50)

            if translations:
                st.subheader("Recent Translations")

                for trans in translations:
                    with st.expander(f"📄 {trans['original_filename']} → {trans['translated_filename']}"):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown(f"**Date:** {trans['created_at'][:10]}")
                            st.markdown(f"**Status:** {trans['status']}")
                            if trans.get('file_size_bytes'):
                                size_mb = trans['file_size_bytes'] / 1024 / 1024
                                st.markdown(f"**File Size:** {size_mb:.2f} MB")

                        with col2:
                            st.markdown(f"**Tokens:** {trans.get('total_tokens', 0):,}")
                            st.markdown(f"**Input:** {trans.get('input_tokens', 0):,}")
                            st.markdown(f"**Output:** {trans.get('output_tokens', 0):,}")
            else:
                st.info("No translation history yet")

        except Exception as e:
            st.error(f"Failed to load history: {e}")
    else:
        st.info("History is only available when logged in with Supabase")

# Footer
st.divider()
st.markdown("*Production version with Supabase auth (local mode enabled if Supabase not configured)*")
