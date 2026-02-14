"""Streamlit PDF Translation App - With Supabase Auth"""
import streamlit as st
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Load environment variables from .env file
load_dotenv()

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from translate_haiku_100 import process_pdf
from auth import require_auth, display_user_info, get_user_id
from supabase_client import get_supabase_client
from anthropic_translator import translate_with_haiku
from api_key_manager import get_key_manager

# Configuration constants
HAIKU_PRICE_INPUT_PER_1M = 1.00
HAIKU_PRICE_OUTPUT_PER_1M = 5.00
MAX_PARALLEL_TRANSLATIONS = 5  # Standard instance (2GB RAM)
MAX_FILE_SIZE_MB = 50  # Maximum file size per PDF to prevent memory exhaustion
MAX_TOTAL_UPLOAD_MB = 100  # Maximum total upload size per batch
MAX_OUTPUT_FILES = 20  # Maximum number of output files to keep per user (cleanup oldest)
LOCK_FILE = Path("translation_lock.txt")
LOCK_TIMEOUT_SECONDS = 300  # 5 minutes - assume stuck if older than this

# Helper functions
def acquire_translation_lock(user_id):
    """Try to acquire the translation lock. Returns True if acquired, False if busy."""
    import time
    try:
        if LOCK_FILE.exists():
            # Check if lock is stale (older than timeout)
            lock_age = time.time() - LOCK_FILE.stat().st_mtime
            if lock_age > LOCK_TIMEOUT_SECONDS:
                # Stale lock, remove it
                LOCK_FILE.unlink()
            else:
                # Lock is held by someone else
                return False
        # Create lock file with user ID
        LOCK_FILE.write_text(f"{user_id}:{time.time()}")
        return True
    except Exception:
        return False

def release_translation_lock():
    """Release the translation lock."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass

def get_lock_status():
    """Get current lock status. Returns (is_locked, user_id, seconds_elapsed)."""
    import time
    try:
        if LOCK_FILE.exists():
            content = LOCK_FILE.read_text()
            parts = content.split(":")
            if len(parts) == 2:
                lock_user = parts[0]
                lock_time = float(parts[1])
                elapsed = time.time() - lock_time
                return True, lock_user, elapsed
        return False, None, 0
    except Exception:
        return False, None, 0


def cleanup_old_output_files(output_dir, max_files=MAX_OUTPUT_FILES):
    """Remove oldest output files if count exceeds max_files to prevent disk/memory bloat."""
    try:
        pdf_files = list(output_dir.glob("*.pdf"))
        if len(pdf_files) > max_files:
            # Sort by modification time, oldest first
            pdf_files.sort(key=lambda x: x.stat().st_mtime)
            # Delete oldest files to get under limit
            files_to_delete = pdf_files[:len(pdf_files) - max_files]
            for f in files_to_delete:
                try:
                    f.unlink()
                    safe_print(f"[CLEANUP] Deleted old file: {f.name}")
                except Exception:
                    pass
    except Exception as e:
        safe_print(f"[CLEANUP] Error during cleanup: {e}")

def sanitize_filename(filename):
    """Sanitize filename for Windows file system compatibility"""
    if not filename:
        return filename
    # Already sanitized by anthropic_translator, but double-check for Windows invalid chars
    for char in '<>:"/\\|?*':
        filename = filename.replace(char, '_')
    return filename

def safe_print(text):
    """Safely print text with Unicode characters on Windows console"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: replace problematic characters for Windows console
        print(text.encode('ascii', 'replace').decode('ascii'))

def process_single_file(idx, uploaded_file, key_manager, source_lang, target_lang,
                       translated_filenames, UPLOAD_DIR, OUTPUT_DIR):
    """Process a single PDF file (used for parallel execution).

    Returns:
        tuple: (idx, success, input_tokens, output_tokens, translated_filename, error_msg, api_key_used)
    """
    import shutil
    import gc

    # Get API key from rotation manager
    api_key = key_manager.get_next_key()
    api_key_id = f"key_{list(key_manager.key_usage.keys()).index(api_key) + 1}"

    input_path = None
    output_path = None

    try:
        # Save uploaded file
        input_path = UPLOAD_DIR / f"temp_input_{idx}.pdf"
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        output_path = OUTPUT_DIR / f"temp_output_{idx}.pdf"

        # Translate PDF content
        success, input_tokens, output_tokens = process_pdf(
            str(input_path),
            str(output_path),
            api_key,
            source_lang=source_lang,
            target_lang=target_lang,
            progress_callback=None  # No per-file progress in parallel mode
        )

        # Record token usage
        if success:
            key_manager.record_tokens(api_key, input_tokens + output_tokens)

            # Get translated filename from batch (or use original as fallback)
            file_key = f"file_{idx}"
            translated_name = translated_filenames.get(
                file_key,
                uploaded_file.name.replace('.pdf', '')
            )

            # Move to final location
            final_output_name = f"{translated_name}.pdf"
            final_output_path = OUTPUT_DIR / final_output_name
            shutil.move(str(output_path), str(final_output_path))
            output_path = None  # Already moved, don't delete

            return (idx, True, input_tokens, output_tokens, final_output_name, None, api_key_id)
        else:
            key_manager.mark_error(api_key)
            # Log detailed error
            import sys
            safe_print(f"[ERROR] Translation failed for {uploaded_file.name} with api_key_id={api_key_id}")
            return (idx, False, 0, 0, None, "Translation failed - check console for details", api_key_id)

    except Exception as e:
        # Check if it's a rate limit error
        error_str = str(e).lower()
        if "rate" in error_str or "429" in error_str:
            key_manager.mark_rate_limited(api_key, duration_seconds=60)
            error_msg = f"Rate limit: {str(e)}"
        elif "authentication" in error_str or "401" in error_str or "invalid" in error_str:
            key_manager.mark_error(api_key)
            error_msg = f"Auth error: {str(e)}"
        else:
            key_manager.mark_error(api_key)
            error_msg = str(e)
        return (idx, False, 0, 0, None, error_msg, api_key_id)

    finally:
        # MEMORY OPTIMIZATION: Clean up temp files and force garbage collection
        try:
            if input_path and input_path.exists():
                input_path.unlink()
        except Exception:
            pass
        try:
            if output_path and output_path.exists():
                output_path.unlink()
        except Exception:
            pass
        # Force garbage collection to free PyMuPDF memory
        gc.collect()

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
        safe_print(f"Batch filename translation failed: {e}")
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
            file_size_bytes=file_info.get("file_size_bytes")
        )
        return True
    except Exception as e:
        safe_print(f"Database logging failed: {e}")
        return str(e)

# Configure page
st.set_page_config(
    page_title="PDF Translator FR→EN",
    page_icon="📄",
    layout="centered"
)

# Require authentication (or allow local mode if Supabase not configured)
require_auth()

# Initialize Supabase client for translation logging (independent of user auth)
if "supabase" not in st.session_state:
    try:
        st.session_state.supabase = get_supabase_client()
    except Exception:
        st.session_state.supabase = None  # Supabase not configured, logging disabled

# Create necessary directories based on user
user_id = get_user_id()
if user_id:
    # Authenticated user - use user-specific folder
    USER_DIR = Path("user_files") / user_id
    UPLOAD_DIR = USER_DIR / "uploads"
    OUTPUT_DIR = USER_DIR / "translated"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # MEMORY OPTIMIZATION: Clean up old output files to prevent disk bloat
    cleanup_old_output_files(OUTPUT_DIR)
else:
    # Local testing mode - use shared folder
    UPLOAD_DIR = Path("uploads")
    OUTPUT_DIR = Path("translated_pdfs")
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    # MEMORY OPTIMIZATION: Clean up old output files to prevent disk bloat
    cleanup_old_output_files(OUTPUT_DIR)

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

    # Language selection with native scripts
    # Map display names to internal language names
    LANGUAGES = [
        ("Français (French)", "French"),
        ("English (English)", "English"),
        ("Español (Spanish)", "Spanish"),
        ("Italiano (Italian)", "Italian"),
        ("Deutsch (German)", "German")
    ]

    LANGUAGE_MAP = {display: internal for display, internal in LANGUAGES}
    language_options = [display for display, _ in LANGUAGES]

    col_lang1, col_lang2 = st.columns(2)
    with col_lang1:
        source_display = st.selectbox(
            "Source Language",
            language_options,
            index=0,
            help="Language of the PDF to translate"
        )
        source_lang = LANGUAGE_MAP[source_display]

    with col_lang2:
        target_display = st.selectbox(
            "Target Language",
            language_options,
            index=1,  # Default to English
            help="Language to translate to"
        )
        target_lang = LANGUAGE_MAP[target_display]

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
        # Validate file sizes to prevent memory exhaustion
        oversized_files = []
        total_size_mb = 0
        valid_files = []

        for uploaded_file in uploaded_files:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            total_size_mb += file_size_mb
            if file_size_mb > MAX_FILE_SIZE_MB:
                oversized_files.append((uploaded_file.name, file_size_mb))
            else:
                valid_files.append(uploaded_file)

        if oversized_files:
            st.error(f"Files exceeding {MAX_FILE_SIZE_MB}MB limit:")
            for name, size in oversized_files:
                st.text(f"  - {name}: {size:.1f}MB")
            st.warning("Please remove oversized files and re-upload.")

        if total_size_mb > MAX_TOTAL_UPLOAD_MB:
            st.error(f"Total upload size ({total_size_mb:.1f}MB) exceeds {MAX_TOTAL_UPLOAD_MB}MB limit. Please upload fewer files.")
            uploaded_files = []  # Block processing
        elif oversized_files:
            uploaded_files = valid_files  # Only process valid files

        if uploaded_files:
            st.success(f"Uploaded {len(uploaded_files)} file(s) ({total_size_mb:.1f}MB total)")

        # Show uploaded files
        for uploaded_file in uploaded_files:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            st.text(f"  {uploaded_file.name} ({file_size_mb:.1f}MB)")

        st.divider()

        # Initialize translation state
        if "is_translating" not in st.session_state:
            st.session_state.is_translating = False
        if "translation_completed" not in st.session_state:
            st.session_state.translation_completed = False

        # Reset completed state if uploaded files changed
        current_files = frozenset(f.name for f in uploaded_files)
        if current_files != st.session_state.get("last_translated_files"):
            st.session_state.translation_completed = False

        # Only show batch translate section if translation hasn't been completed
        if not st.session_state.translation_completed:
            st.header(f"Batch Translate ({source_lang} → {target_lang})")

            # Check if another user is translating
            is_locked, lock_user, lock_elapsed = get_lock_status()
            if is_locked and lock_user != user_id:
                st.warning(f"Another translation is in progress ({int(lock_elapsed)}s elapsed). Please wait...")
                st.info("The page will auto-refresh when ready. Or click below to check status.")
                if st.button("Check Status"):
                    st.rerun()
            else:
                # Batch translate button - disabled during translation
                button_disabled = st.session_state.is_translating or source_lang == target_lang
                if st.button("Batch Translate All Files", type="primary", disabled=button_disabled):
                    if source_lang == target_lang:
                        st.error("Cannot translate: Source and target languages are the same!")
                    elif not st.session_state.get("anthropic_api_key"):
                        st.error("API Key not found! Set ANTHROPIC_API_KEY environment variable on Render.")
                    elif not acquire_translation_lock(user_id):
                        st.error("Another translation just started. Please wait and try again.")
                        st.rerun()
                    else:
                        # Set translation state to true
                        st.session_state.is_translating = True
                        import shutil
                        import time

                        # Initialize API key manager
                        try:
                            key_manager = get_key_manager()
                            total_keys = key_manager.get_total_keys()
                            st.info(f"Using API key rotation with {total_keys} key(s)")
                        except ValueError as e:
                            st.error(f"{e}")
                            release_translation_lock()
                            st.session_state.is_translating = False
                            st.stop()

                        start_time = time.time()
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        timer_text = st.empty()
                        error_placeholder = st.empty()

                        total_files = len(uploaded_files)
                        completed = 0
                        total_input_tokens = 0
                        total_output_tokens = 0
                        translation_failed = False

                        # Step 1: Batch translate ALL filenames in one API call
                        status_text.text("Translating filenames...")
                        progress_bar.progress(0.05)

                        filenames_to_translate = {
                            f"file_{idx}": uploaded_file.name.replace('.pdf', '')
                            for idx, uploaded_file in enumerate(uploaded_files)
                        }

                        # Use first key for filename translation
                        filename_api_key = key_manager.get_next_key()
                        try:
                            filename_result = translate_filenames_batch(
                                filenames_to_translate,
                                filename_api_key,
                                source_lang,
                                target_lang
                            )
                        except Exception as e:
                            error_placeholder.error(f"Translation failed: {e}")
                            release_translation_lock()
                            st.session_state.is_translating = False
                            translation_failed = True
                            filename_result = {"translations": {}, "input_tokens": 0, "output_tokens": 0}

                        translated_filenames = filename_result["translations"]
                        total_input_tokens += filename_result["input_tokens"]
                        total_output_tokens += filename_result["output_tokens"]
                        if filename_result["input_tokens"] > 0:
                            key_manager.record_tokens(filename_api_key, filename_result["input_tokens"] + filename_result["output_tokens"])

                        # Step 2: Process files (skip if filename translation already failed)
                        if translation_failed:
                            status_text.text("")
                            progress_bar.empty()
                            st.stop()

                        def log_completed_file(uploaded_file, final_output_name, input_tokens, output_tokens, api_key_id):
                            """Log a completed file to DB and show success message."""
                            if st.session_state.get("supabase"):
                                file_size = uploaded_file.size if hasattr(uploaded_file, 'size') else None
                                logged = log_translation_to_database(
                                    st.session_state.supabase,
                                    get_user_id(),
                                    {
                                        "original_filename": uploaded_file.name,
                                        "translated_filename": final_output_name,
                                        "input_tokens": input_tokens,
                                        "output_tokens": output_tokens,
                                        "file_size_bytes": file_size
                                    }
                                )
                                if logged is not True:
                                    st.warning(f"{uploaded_file.name}: DB log failed: {logged}")

                            file_tokens = input_tokens + output_tokens
                            st.success(f"{uploaded_file.name}: {file_tokens:,} tokens [{api_key_id}]")

                        if total_files == 1:
                            # SINGLE FILE: Run sequentially with live per-page progress
                            import shutil as shutil_single
                            import gc

                            uploaded_file = uploaded_files[0]
                            api_key = key_manager.get_next_key()
                            api_key_id = f"key_{list(key_manager.key_usage.keys()).index(api_key) + 1}"

                            status_text.text(f"Translating {uploaded_file.name}...")
                            progress_bar.progress(0.1)

                            # Save uploaded file
                            input_path = UPLOAD_DIR / "temp_input_0.pdf"
                            with open(input_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())
                            output_path = OUTPUT_DIR / "temp_output_0.pdf"

                            # Progress callback that updates UI in real-time
                            def update_progress(progress_value):
                                # Map 0.0-1.0 to 0.1-0.95 on the progress bar
                                bar_value = 0.1 + (progress_value * 0.85)
                                progress_bar.progress(min(bar_value, 0.95))
                                elapsed = time.time() - start_time
                                pct = int(progress_value * 100)
                                status_text.text(f"Translating {uploaded_file.name}... {pct}%")
                                timer_text.text(f"Elapsed: {elapsed:.1f}s")

                            try:
                                success, input_tokens, output_tokens = process_pdf(
                                    str(input_path),
                                    str(output_path),
                                    api_key,
                                    source_lang=source_lang,
                                    target_lang=target_lang,
                                    progress_callback=update_progress
                                )

                                if success:
                                    key_manager.record_tokens(api_key, input_tokens + output_tokens)
                                    completed += 1
                                    total_input_tokens += input_tokens
                                    total_output_tokens += output_tokens

                                    # Move to final location
                                    file_key = "file_0"
                                    translated_name = translated_filenames.get(
                                        file_key, uploaded_file.name.replace('.pdf', ''))
                                    final_output_name = f"{translated_name}.pdf"
                                    final_output_path = OUTPUT_DIR / final_output_name
                                    shutil_single.move(str(output_path), str(final_output_path))

                                    log_completed_file(uploaded_file, final_output_name, input_tokens, output_tokens, api_key_id)
                                else:
                                    key_manager.mark_error(api_key)
                                    st.error(f"{uploaded_file.name}: Translation failed [{api_key_id}]")

                            except Exception as e:
                                st.error(f"Failed to translate {uploaded_file.name}: {e}")
                            finally:
                                # Cleanup
                                try:
                                    if input_path.exists():
                                        input_path.unlink()
                                except Exception:
                                    pass
                                gc.collect()

                        else:
                            # MULTIPLE FILES: Process in parallel
                            status_text.text(f"Translating {total_files} PDFs in parallel (up to {MAX_PARALLEL_TRANSLATIONS} at once)...")
                            progress_bar.progress(0.1)

                            completed_lock = threading.Lock()

                            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_TRANSLATIONS) as executor:
                                future_to_file = {
                                    executor.submit(
                                        process_single_file,
                                        idx,
                                        uploaded_file,
                                        key_manager,
                                        source_lang,
                                        target_lang,
                                        translated_filenames,
                                        UPLOAD_DIR,
                                        OUTPUT_DIR
                                    ): (idx, uploaded_file) for idx, uploaded_file in enumerate(uploaded_files)
                                }

                                for future in as_completed(future_to_file):
                                    idx, uploaded_file = future_to_file[future]

                                    try:
                                        file_idx, success, input_tokens, output_tokens, final_output_name, error_msg, api_key_id = future.result()

                                        if success:
                                            with completed_lock:
                                                completed += 1
                                                total_input_tokens += input_tokens
                                                total_output_tokens += output_tokens

                                            log_completed_file(uploaded_file, final_output_name, input_tokens, output_tokens, api_key_id)
                                        else:
                                            st.error(f"{uploaded_file.name}: {error_msg} [{api_key_id}]")

                                    except Exception as e:
                                        st.error(f"Failed to translate {uploaded_file.name}: {e}")

                                    # Update progress after each file completes
                                    with completed_lock:
                                        current_completed = completed
                                    elapsed = time.time() - start_time
                                    progress_bar.progress(0.1 + (current_completed / total_files) * 0.9)
                                    status_text.text(f"Translating ({current_completed}/{total_files} files complete)...")
                                    timer_text.text(f"Elapsed: {elapsed:.1f}s")

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
                        timer_text.text(f"Total time: {time_str}")
                        progress_bar.empty()

                        st.success(f"Batch translation complete! Processed {completed}/{total_files} files in {time_str}")

                        # Show token usage
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Tokens", f"{total_tokens:,}")
                        with col2:
                            st.metric("Input", f"{total_input_tokens:,}")
                        with col3:
                            st.metric("Output", f"{total_output_tokens:,}")

                        st.info("Check the 'Files' tab to download your translated PDFs")

                        # Release lock and reset translation state
                        release_translation_lock()
                        st.session_state.is_translating = False
                        st.session_state.translation_completed = True
                        st.session_state.last_translated_files = current_files
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

    # Show history if Supabase is configured
    history_user_id = get_user_id()
    if st.session_state.get("supabase"):
        # Get user stats
        try:
            stats = st.session_state.supabase.get_user_stats(history_user_id)

            # Display statistics
            st.subheader("Statistics")
            col1, col2 = st.columns(2)

            with col1:
                st.metric("Total Translations", stats.get("total_translations", 0))
            with col2:
                st.metric("Total Tokens", f"{stats.get('total_tokens_used', 0):,}")

            st.divider()

            # Get translation history
            translations = st.session_state.supabase.get_user_translations(history_user_id, limit=50)

            if translations:
                st.subheader("Recent Translations")

                for trans in translations:
                    date_str = trans['created_at'][:10]
                    tokens = trans.get('total_tokens', 0)
                    size_str = ""
                    if trans.get('file_size_bytes'):
                        size_mb = trans['file_size_bytes'] / 1024 / 1024
                        size_str = f"  |  {size_mb:.2f} MB"
                    st.markdown(f"**{date_str}**  |  {trans['original_filename']} → {trans['translated_filename']}  |  {tokens:,} tokens{size_str}")
            else:
                st.info("No translation history yet")

        except Exception as e:
            st.error(f"Failed to load history: {e}")
    else:
        st.info("History is unavailable - Supabase not configured")

