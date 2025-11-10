# PDF Translate - French to English

Automatic translation of architectural PDFs from French to English using dictionary lookup and AI-powered sentence translation.

## Features

- **Hybrid Translation**: Dictionary for short text (fast), AI agents for complete sentences (accurate)
- **Master Dictionary**: 3,857+ French-to-English entries
- **Per-PDF Sentence Caching**: Reusable translations for each PDF
- **Format Preservation**: Maintains fonts, colors, sizes, and strikethrough
- **Smart Categorization**: Skips units, acronyms, technical codes
- **No Franglish**: Complete sentence translation prevents mixed French/English

## Architecture

**Method 11: Indexed Sentence Translation**

1. **Phase 1**: Extract and categorize all text
   - Short text (1-3 words) → Dictionary lookup
   - Sentences (4+ words) → Index for AI translation
   - Skip: numbers, units, technical codes

2. **Phase 2**: Batch translate sentences
   - Save indexed sentences to `{PDF_CODE}_sentences_indexed.json`
   - Translate with AI agent
   - Save to `{PDF_CODE}_sentences.json`

3. **Phase 3**: Apply translations
   - Cover original text with white rectangles
   - Insert translated text with preserved formatting

## Quick Start

### Translate a PDF

```bash
python method11_indexed_sentences.py "input.pdf" "output.pdf"
```

### First run creates indexed sentences file:
```
Phase 1: Extracting text...
Phase 2: Translating 259 sentences...
Saved to: A-001_sentences_indexed.json

**ACTION REQUIRED:**
1. Translate A-001_sentences_indexed.json with AI
2. Save translations to A-001_sentences.json
3. Re-run script to complete
```

### Second run applies translations:
```bash
python method11_indexed_sentences.py "input.pdf" "output.pdf"
```

## Files

### Core
- `method11_indexed_sentences.py` - Main translation script
- `translations.json` - Master dictionary (3,857 entries)
- `find_remaining_french.py` - Quality check for remaining French

### Per-PDF Caches
- `{PDF_CODE}_sentences_indexed.json` - French sentences for translation
- `{PDF_CODE}_sentences.json` - English translations

## Requirements

```bash
pip install pymupdf
```

## Workflow for 700 PDFs

1. **Extract sentences from new PDF**:
   ```bash
   python method11_indexed_sentences.py "A-082.pdf" "A-082-EN.pdf"
   ```

2. **Translate indexed sentences** (with AI agent or manually)

3. **Complete translation** (re-run same command)

4. **Verify**:
   ```bash
   python find_remaining_french.py
   ```

## Statistics

- **Master Dictionary**: 3,857 entries
- **Test PDF (A-001)**: 967 text elements, 259 sentences
- **Translation Speed**: ~10 seconds per PDF
- **Quality**: 100% English (excluding technical codes)

## License

MIT
