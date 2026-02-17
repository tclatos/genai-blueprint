# Main Streamlit application configuration and setup
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from genai_tk.utils.basic_auth import authenticate, load_auth_config
from genai_tk.utils.config_exceptions import (
    ConfigError,
    ConfigKeyNotFoundError,
)
from genai_tk.utils.config_mngr import global_config
from genai_tk.utils.logger_factory import setup_logging
from loguru import logger

load_dotenv(verbose=True)

setup_logging()
# print("Starting Web Application...")


try:
    # Configure Streamlit page settings
    app_name = global_config().get_str("ui.app_name")
except ConfigKeyNotFoundError as e:
    st.error(f"❌ Configuration Error: {e.message}")
    st.info(f"💡 {e.suggestion}")
    st.stop()
except ConfigError as e:
    st.error(f"❌ Configuration Error: {e.message}")
    if hasattr(e, "suggestion") and e.suggestion:
        st.info(f"💡 {e.suggestion}")
    st.stop()

st.set_page_config(
    page_title=app_name,
    page_icon="🛠️",
    layout="wide",  #
    initial_sidebar_state="expanded",
)

# Initialize session state for authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Authentication handling
auth_config = load_auth_config()

# Only show login form if authentication is enabled and user is not authenticated
if auth_config.enabled and not st.session_state.authenticated:
    st.title("Login")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

        if submit:
            if authenticate(username, password):
                st.session_state.authenticated = True
                st.success("Login successful!")
                st.rerun()
            else:
                st.error("Invalid username or password")

    # Stop execution if not authenticated
    st.stop()

# Only show the main application if authenticated
LOGO = "New Atos logo white.png"
logo = str(Path.cwd() / "genai_blueprint/webapp/static" / LOGO)
st.logo(logo, size="medium")

# Get Streamlit pages to display from config
try:
    pages_dir = global_config().get_dir_path("ui.pages_dir")
except ConfigKeyNotFoundError as e:
    st.error(f"❌ Pages directory not configured: {e.message}")
    st.info(f"💡 {e.suggestion}")
    st.stop()
except ConfigError as e:
    st.error(f"❌ Configuration error loading pages directory: {e.message}")
    if hasattr(e, "suggestion") and e.suggestion:
        st.info(f"💡 {e.suggestion}")
    st.stop()

# Get navigation structure from config
try:
    nav_config = global_config().get("ui.navigation", {})
except ConfigError as e:
    st.error(f"❌ Navigation configuration error: {e.message}")
    if hasattr(e, "suggestion") and e.suggestion:
        st.info(f"💡 {e.suggestion}")
    st.stop()

# Build pages dictionary with sections
pages = {}


def file_name_to_page_name(file_name: str) -> str:
    """Convert a file name to a formatted page name.

    Converts to title case while preserving existing capitalization in acronyms and mixed case words.
    Handles file paths by extracting just the filename part.

    Examples:
        'CLI_command.py' -> 'CLI Command'
        'demos/deep_search_agent.py' -> 'Deep Search Agent'
        'reAct_demo.py' -> 'ReAct Demo'
        'API_demo.py' -> 'API Demo'
        'myTool.py' -> 'MyTool'
    """
    try:
        # Extract just the filename from the path (remove directory)
        file_name_only = file_name.split("/")[-1]

        # Remove the file extension
        name_without_ext = file_name_only.rsplit(".", 1)[0]

        # Handle numeric prefix and emoji if present
        name_parts = name_without_ext.split("_")

        # Skip numeric prefix and emoji prefix if they exist
        start_idx = 0
        if len(name_parts) > 0 and name_parts[0].isdigit():
            start_idx = 1

        if len(name_parts) > start_idx and name_parts[start_idx] in ["🛠️", "📊", "🔍"]:
            start_idx += 1

        # Process the remaining parts
        words = name_parts[start_idx:]
        formatted_words = []

        for word in words:
            if not word:  # Skip empty parts
                continue

            # Check if word has mixed case (e.g., reAct, myTool)
            if any(c.isupper() for c in word[1:]):
                # Preserve mixed case but ensure first letter is uppercase
                formatted_words.append(word[0].upper() + word[1:])
            # Check if word is all uppercase (e.g., API, CLI)
            elif word == word.upper() and len(word) > 1:
                formatted_words.append(word)
            # Regular word - capitalize first letter
            else:
                formatted_words.append(word.capitalize())

        return " ".join(formatted_words) if formatted_words else file_name
    except Exception:
        return file_name


for section_name, page_files in nav_config.items():
    section_pages = []
    for page_file_name in page_files:
        page_path = pages_dir / page_file_name
        if page_path.exists():
            section_pages.append(st.Page(page=page_path, title=file_name_to_page_name(page_file_name)))
        else:
            logger.warning(f"page not found: {page_path} ")
    if section_pages:
        pages[section_name.title()] = section_pages

pg = st.navigation(pages, position="top")
pg.run()
