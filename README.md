# AI PDF Translator

Web-based PDF translation application powered by Claude Haiku 4.5 API with multi-language support and optional user authentication.

## Features

- **Multi-Language Support**: Translate between French, English, and Spanish
- **Batch Translation**: Upload and translate multiple PDFs simultaneously
- **Real-time Progress Tracking**: Visual progress bars with time estimates
- **User Authentication** (Optional): Supabase integration for user accounts and translation history
- **Translation History**: Track token usage and past translations (when authenticated)
- **Smart Text Extraction**: Skips technical codes, units, and preserves formatting
- **Optimized API Usage**: Batch processing with dynamic token-based batching

## Architecture

**Translation Pipeline:**

1. **Text Extraction** - PyMuPDF extracts text with position, font, and color data
2. **Smart Filtering** - Skips numbers, units, material codes, reference codes
3. **Batch Translation** - Claude Haiku 4.5 API with dynamic batching (auto-adjusts based on token estimates)
4. **Format Preservation** - Maintains original PDF layout, fonts, and colors
5. **History Logging** - Tracks translations in Supabase (optional)

## Quick Start

### Local Mode (No Authentication)

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set API Key**:
   ```bash
   # Windows
   set ANTHROPIC_API_KEY=your-api-key-here

   # Linux/Mac
   export ANTHROPIC_API_KEY=your-api-key-here
   ```

3. **Run Application**:
   ```bash
   streamlit run app.py
   ```

4. **Access**: Open http://localhost:8501

### Production Mode (With Supabase)

1. **Setup Supabase**:
   - Create a Supabase project at https://supabase.com
   - Run [schema.sql](schema.sql) in SQL Editor
   - Run [fix_view_permissions.sql](fix_view_permissions.sql)
   - Copy your project URL and anon key

2. **Configure Environment**:
   ```bash
   # Copy example and edit
   cp .env.example .env

   # Add your credentials to .env
   SUPABASE_URL=your_project_url
   SUPABASE_ANON_KEY=your_anon_key
   ```

3. **Run Application**:
   ```bash
   streamlit run app.py
   ```

## Project Structure

```
├── app.py                      # Main Streamlit application
├── auth.py                     # Supabase authentication module
├── supabase_client.py          # Database operations wrapper
├── anthropic_translator.py     # Claude API integration
├── translate_haiku_100.py      # PDF processing engine
├── schema.sql                  # Database schema
├── fix_view_permissions.sql    # View permissions fix
├── requirements.txt            # Python dependencies
└── .env.example               # Configuration template
```

## Configuration

### Environment Variables

- `ANTHROPIC_API_KEY` (Required): Your Anthropic API key
- `SUPABASE_URL` (Optional): Supabase project URL for auth
- `SUPABASE_ANON_KEY` (Optional): Supabase anonymous key for auth

### Cost Estimation

Claude Haiku 4.5 Pricing:
- Input: $0.80 per 1M tokens
- Output: $4.00 per 1M tokens

Typical usage: ~5,000-15,000 tokens per architectural PDF

## Features Detail

### Batch Filename Translation
- Translates all PDF filenames in a single API call (45% reduction in API calls)
- Falls back to original filename if translation fails

### Dynamic Token-Based Batching
- Estimates tokens per text (~1 token per 3 characters)
- Automatically creates batches within 15,000 token limit
- Prevents API failures from oversized requests

### Progress Tracking
- Hierarchical progress: Batch → File → Overall
- Real-time elapsed time display
- Token usage metrics after completion

## Requirements

- Python 3.8+
- Anthropic API key
- Optional: Supabase project (for auth and history)

## License

MIT
