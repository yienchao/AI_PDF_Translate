# AI PDF Translator

Web-based PDF translation application powered by Claude Haiku 4.5 API with multi-language support, API key rotation, and optional user authentication.

## Features

- **Multi-Language Support**: Translate between French, English, Spanish, Italian, and German
- **Batch Translation**: Upload and translate multiple PDFs simultaneously (up to 5 concurrent)
- **API Key Rotation**: Round-robin rotation across multiple API keys for redundancy
- **Real-time Progress Tracking**: Visual progress bars with time estimates
- **User Authentication** (Optional): Supabase integration for user accounts and translation history
- **Translation History**: Track token usage and past translations (when authenticated)
- **Smart Text Extraction**: Skips technical codes, units, and preserves formatting
- **Optimized for Speed**: No caching overhead, maximum translation throughput

## Architecture

**Translation Pipeline:**

1. **Text Extraction** - PyMuPDF extracts text with position, font, and color data
2. **Smart Filtering** - Skips numbers, units, material codes, reference codes
3. **Batch Translation** - Claude Haiku 4.5 API with dynamic batching (auto-adjusts based on token estimates)
4. **Parallel Processing** - 5 concurrent PDF translations with API key rotation
5. **Format Preservation** - Maintains original PDF layout, fonts, and colors
6. **History Logging** - Tracks translations in Supabase (optional)

## Performance Benchmarks

**Current Configuration:**
- Model: Claude Haiku 4.5 (optimized for speed)
- Parallel Workers: 5
- API Keys: 5 (round-robin rotation)
- Caching: Disabled (prioritizes speed over cost)

**Typical Performance:**
- 12 architectural PDFs: ~13 minutes
- Single PDF (10-20 pages): ~1-2 minutes
- Token usage: 5,000-15,000 tokens per PDF

**Why Haiku 4.5?**
- 2-3x faster than Sonnet 4.5
- 4x cheaper than Sonnet 4.5
- Excellent quality for technical document translation

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
   ANTHROPIC_API_KEY=your_api_key
   SUPABASE_URL=your_project_url
   SUPABASE_KEY=your_anon_key
   ```

3. **Run Application**:
   ```bash
   streamlit run app.py
   ```

## API Key Rotation (Advanced)

For improved redundancy, you can configure multiple Anthropic API keys:

### Setup Multiple Keys

Add to your `.env` file:
```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_API_KEY_1=sk-ant-api03-...
ANTHROPIC_API_KEY_2=sk-ant-api03-...
ANTHROPIC_API_KEY_3=sk-ant-api03-...
ANTHROPIC_API_KEY_4=sk-ant-api03-...
```

### How It Works

- **Round-robin rotation**: Distributes requests evenly across all keys
- **Automatic failover**: If one key hits rate limit, switches to next available key
- **Usage tracking**: Monitors requests, tokens, and errors per key

### Important Notes

- Rate limits are **per organization**, not per key
- Multiple keys from the same Anthropic organization share rate limits
- 5 keys provide redundancy but not speed improvement
- To increase speed, you need keys from different organizations

### Rate Limits (Tier 2)

- **Output tokens**: 200,000 per minute
- **Input tokens**: 1,000,000 per minute
- **Requests**: 2,000 per minute
- **Concurrent connections**: ~5-10 per organization

## Project Structure

```
├── app.py                      # Main Streamlit application
├── auth.py                     # Supabase authentication module
├── supabase_client.py          # Database operations wrapper
├── anthropic_translator.py     # Claude API integration (no caching)
├── api_key_manager.py          # API key rotation manager
├── translate_haiku_100.py      # PDF processing engine
├── schema.sql                  # Database schema
├── fix_view_permissions.sql    # View permissions fix
├── requirements.txt            # Python dependencies
├── .env.example                # Configuration template
└── .claude/                    # Project planning documents
    └── phase2-nextjs-plan.md   # Next.js migration plan
```

## Configuration

### Environment Variables

- `ANTHROPIC_API_KEY` (Required): Your Anthropic API key
- `ANTHROPIC_API_KEY_1` through `ANTHROPIC_API_KEY_4` (Optional): Additional API keys for rotation
- `SUPABASE_URL` (Optional): Supabase project URL for auth
- `SUPABASE_KEY` (Optional): Supabase anonymous key for auth

### Cost Estimation

Claude Haiku 4.5 Pricing:
- Input: $0.80 per 1M tokens
- Output: $4.00 per 1M tokens

**Typical Costs:**
- Single architectural PDF: $0.02-$0.06
- Batch of 12 PDFs: $0.25-$0.75
- 100-page PDF: $0.15-$0.50

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
- Per-file token breakdown with API key tracking

### Parallel Processing
- Processes up to 5 PDFs simultaneously
- ThreadPoolExecutor for concurrent translation
- API key rotation across workers

## Supported Languages

- French (Français)
- English
- Spanish (Español)
- Italian (Italiano)
- German (Deutsch)

## Requirements

- Python 3.8+
- Anthropic API key (Tier 2 recommended for production)
- Optional: Supabase project (for auth and history)

## Roadmap

### Phase 1: Performance Optimization (Completed ✅)
- API key rotation with round-robin
- Removed prompt caching for maximum speed
- Parallel processing with 5 workers
- Performance benchmarking

### Phase 2: Next.js Frontend (Planned)
- Replace Streamlit with Next.js/React frontend
- Modern drag-and-drop file upload UI
- Real-time progress tracking with WebSocket/polling
- Deploy frontend to Vercel, backend to Render
- See `.claude/phase2-nextjs-plan.md` for details

## License

MIT
