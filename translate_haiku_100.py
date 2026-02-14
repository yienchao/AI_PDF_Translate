"""
100% Haiku Translation Test
- NO dictionary lookup
- NO indexed files
- EVERYTHING gets translated by Haiku 4.5
- Purpose: Identify source of translation gaps
"""
import fitz
import gc
import os
import re
import sys
import time
from pathlib import Path
from anthropic_translator import translate_batch

# Folders
TRANSLATED_FOLDER = "translated_pdfs"

# Compile regexes once at module level for performance
REFERENCE_CODE_PATTERN_1 = re.compile(r'^[A-Z]{1,3}\d+[a-z]?$', re.IGNORECASE)
REFERENCE_CODE_PATTERN_2 = re.compile(r'^[A-Z]-\d+[a-z]?$', re.IGNORECASE)

def should_skip(text):
    """Skip empty, numbers only, units, acronyms, technical codes"""
    if not text or not text.strip():
        return True

    # Skip if no letters (pure numbers, symbols, etc.)
    if not any(c.isalpha() for c in text):
        return True

    # Skip common units and measurement abbreviations
    units = {'MM', 'CM', 'M', 'KG', 'LB', 'FT', 'IN', 'SQ', 'MIN', 'MAX', 'NO', 'QTY', 'TYP', 'REF',
             'GA', 'CAL', 'PSI', 'KPA', 'MPH', 'KPH', 'DEG', 'TEMP', 'DIA', 'THK', 'EA'}
    if text.upper().strip('.,;:()[]{}!?-') in units:
        return True

    # Skip material codes ONLY if they match specific patterns
    if len(text) <= 4 and not text.isupper():
        # Skip only if it has numbers (like "1a", "2b")
        if any(c.isdigit() for c in text):
            return True
        # Skip ONLY known material code patterns
        material_codes = {'ac', 'aci', 'al', 'ar', 'asp', 'bo', 'br', 'bv', 'bz',
                         'ca', 'cc', 'cf', 'cg', 'ci', 'cp', 'cr', 'cs', 'ct', 'cu', 'cv',
                         'ea', 'ec', 'ei', 'pbo', 'pfs', 'pi', 'pla', 'prt', 'ps', 'pt', 'pvb',
                         'rm', 'rv', 'st', 'ta', 'tc', 'te', 'ti', 'tm', 'tn', 'tep', 'tr',
                         'vac', 'vc', 'vcr'}
        if text.lower() in material_codes:
            return True

    # Skip reference codes like "PL1", "MF2", "A-505", "G485"
    if REFERENCE_CODE_PATTERN_1.match(text):
        return True
    if REFERENCE_CODE_PATTERN_2.match(text):
        return True

    return False

def merge_text_spans(spans):
    """Merge adjacent text spans"""
    if not spans:
        return []

    spans.sort(key=lambda s: (round(s["bbox"][1], 1), s["bbox"][0]))

    merged = []
    current = spans[0].copy()
    current["bbox"] = list(current["bbox"])

    for next_span in spans[1:]:
        same_line = abs(current["bbox"][1] - next_span["bbox"][1]) < 2
        x_gap = next_span["bbox"][0] - current["bbox"][2]
        close_horizontal = -1 <= x_gap <= 5

        if same_line and close_horizontal:
            if x_gap > 0.5:
                current["text"] += " " + next_span["text"]
            else:
                current["text"] += next_span["text"]
            current["bbox"][2] = max(current["bbox"][2], next_span["bbox"][2])
        else:
            merged.append(current)
            current = next_span.copy()
            current["bbox"] = list(current["bbox"])

    merged.append(current)
    return merged

def extract_text_from_pdf(pdf_path):
    """Extract all text with positions"""
    doc = fitz.open(pdf_path)
    all_text = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        page_spans = []
        for block in blocks:
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            page_spans.append({
                                "text": text,
                                "bbox": list(span["bbox"]),
                                "size": span["size"],
                                "color": span.get("color", 0)
                            })

        merged = merge_text_spans(page_spans)

        for item in merged:
            all_text.append({
                "page": page_num,
                "text": item["text"],
                "bbox": item["bbox"],
                "size": item["size"],
                "color": item["color"]
            })

    doc.close()
    return all_text

def safe_print(text):
    """Safely print text with Unicode characters on Windows console"""
    try:
        print(text.encode('ascii', 'replace').decode('ascii'))
    except:
        print(text)

def process_pdf(input_path, output_path, api_key, source_lang="French", target_lang="English", progress_callback=None, api_keys=None):
    """Process single PDF with 100% Haiku translation

    Args:
        input_path: Path to input PDF
        output_path: Path to save translated PDF
        api_key: Anthropic API key (fallback if api_keys not provided)
        source_lang: Source language
        target_lang: Target language
        progress_callback: Optional callback function(progress_value) where progress_value is 0.0-1.0
        api_keys: List of API keys to rotate across batches for parallel speed
    """
    safe_print(f"\n{'='*80}")
    safe_print(f"100% HAIKU TRANSLATION ({source_lang} -> {target_lang})")
    safe_print(f"Processing: {os.path.basename(input_path)}")
    safe_print('='*80)

    # Extract text
    safe_print("Extracting text...")
    text_elements = extract_text_from_pdf(input_path)
    safe_print(f"   Found {len(text_elements)} text elements")

    # Process each element - EVERYTHING goes to Haiku (no dictionary!)
    needs_translation = {}  # {index: french_text}
    skipped = 0

    for idx, elem in enumerate(text_elements):
        text = elem["text"]

        # Skip only numbers/units
        if should_skip(text):
            elem["translated"] = text
            elem["type"] = "skip"
            skipped += 1
        else:
            # EVERYTHING ELSE → Haiku (NO dictionary check!)
            elem["type"] = "needs_haiku"
            needs_translation[str(idx)] = text

    safe_print(f"   Skipped (numbers/units): {skipped}")
    safe_print(f"   Sending to Haiku: {len(needs_translation)}")

    # Translate with Haiku
    input_tokens = 0
    output_tokens = 0

    if needs_translation:
        safe_print(f"\nTranslating {len(needs_translation)} items with Haiku 4.5...")
        try:
            # Create progress callback that updates the main progress bar
            def batch_progress(current_batch, total_batches):
                if progress_callback:
                    # Translation is 20%-90% of total progress
                    # Map batch progress (0-1) to this range
                    batch_pct = current_batch / total_batches
                    overall_progress = 0.2 + (batch_pct * 0.7)  # 0.2 to 0.9
                    progress_callback(overall_progress)

            result = translate_batch(
                needs_translation,
                api_key,
                batch_size=100,
                source_lang=source_lang,
                target_lang=target_lang,
                progress_callback=batch_progress,
                api_keys=api_keys
            )
            translations = result["translations"]
            input_tokens = result["input_tokens"]
            output_tokens = result["output_tokens"]

            safe_print(f"   Got {len(translations)} translations from Haiku")
            safe_print(f"   Tokens: {input_tokens} input + {output_tokens} output = {input_tokens + output_tokens} total")

            # Apply Haiku translations
            for idx_str, english in translations.items():
                idx_int = int(idx_str)
                if idx_int < len(text_elements):
                    text_elements[idx_int]["translated"] = english
                    text_elements[idx_int]["type"] = "haiku"

        except Exception as e:
            import traceback
            safe_print(f"   Haiku translation failed: {e}")
            safe_print(f"   Full error: {traceback.format_exc()}")
            return False, 0, 0

    # Count results
    haiku_count = sum(1 for e in text_elements if e.get("type") == "haiku")
    untranslated_count = sum(1 for e in text_elements if "translated" not in e)

    safe_print(f"\n--- TRANSLATION STATS ---")
    safe_print(f"   Total elements: {len(text_elements)}")
    safe_print(f"   Translated by Haiku: {haiku_count}")
    safe_print(f"   Skipped (numbers/units): {skipped}")
    safe_print(f"   UNTRANSLATED (gaps): {untranslated_count}")

    # Show untranslated items if any
    if untranslated_count > 0:
        safe_print(f"\n⚠️ WARNING: {untranslated_count} items were NOT translated!")
        safe_print("These are the GAPS we're investigating:")
        for idx, elem in enumerate(text_elements):
            if "translated" not in elem:
                safe_print(f"   - '{elem['text']}'")
                if idx >= 10:
                    safe_print(f"   ... and {untranslated_count - 10} more")
                    break

    # MEMORY OPTIMIZATION: Clear the translation dict as we've applied results to text_elements
    needs_translation.clear()
    del needs_translation
    gc.collect()

    # Apply to PDF
    safe_print("\nApplying translations to PDF...")
    doc = fitz.open(input_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_elements = [e for e in text_elements if e["page"] == page_num]

        # Cover original text with white rectangles (minimal padding to avoid covering graphics)
        for elem in page_elements:
            bbox = elem["bbox"]
            rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))

        # Insert translated text
        try:
            font = fitz.Font("helv")
        except Exception:
            font = fitz.Font()

        success_count = 0
        for elem in page_elements:
            translated = elem.get("translated", elem["text"])
            bbox = elem["bbox"]
            size = elem["size"]

            if not translated:
                continue

            # Sanitize text: replace Unicode characters that PDF fonts don't support
            translated = translated.replace('\u2192', '->')  # → arrow
            translated = translated.replace('\u2013', '-')  # en dash
            translated = translated.replace('\u2014', '--')  # em dash
            translated = translated.replace('\u2018', "'")  # left single quote
            translated = translated.replace('\u2019', "'")  # right single quote
            translated = translated.replace('\u201c', '"')  # left double quote
            translated = translated.replace('\u201d', '"')  # right double quote
            translated = translated.replace('\u2026', '...')  # ellipsis

            # Color conversion
            color_int = elem["color"]
            color = (
                ((color_int >> 16) & 0xFF) / 255.0,
                ((color_int >> 8) & 0xFF) / 255.0,
                (color_int & 0xFF) / 255.0
            )

            try:
                # Calculate available width
                available_width = bbox[2] - bbox[0]
                available_height = bbox[3] - bbox[1]

                # Try to fit text with automatic font size reduction if needed
                current_size = size
                min_size = size * 0.5  # Don't go below 50% of original size

                while current_size >= min_size:
                    # Estimate text width (approximate: 0.5 * fontsize per character)
                    estimated_width = len(translated) * current_size * 0.5

                    if estimated_width <= available_width:
                        break

                    # Reduce font size by 10%
                    current_size *= 0.9

                # Insert text with adjusted font size
                page.insert_text(
                    (bbox[0], bbox[3] - 1),
                    translated,
                    fontsize=current_size,
                    color=color,
                    render_mode=0
                )
                success_count += 1
            except Exception as e:
                # Skip text that can't be inserted (invalid coordinates, font issues, etc.)
                pass

        if page_num == 0:
            safe_print(f"   Inserted {success_count}/{len(page_elements)} texts on page 1")

        # MEMORY OPTIMIZATION: Clear page elements after processing each page
        page_elements.clear()

    # Sanitize output_path for console printing (Windows encoding issue)
    safe_output_path = str(output_path).encode('ascii', 'replace').decode('ascii')
    safe_print(f"\nSaving to: {safe_output_path}")
    # Save PDF
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()

    # MEMORY OPTIMIZATION: Clear text_elements and force garbage collection
    text_elements.clear()
    del text_elements
    gc.collect()

    safe_print("Done!")
    return True, input_tokens, output_tokens

def main():
    """Process PDF with 100% Haiku translation"""
    # Get API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("Set it using: set ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    os.makedirs(TRANSLATED_FOLDER, exist_ok=True)

    # Get files to process
    if len(sys.argv) > 1:
        # Single file mode
        pdf_files = [Path(sys.argv[1])]
    else:
        # Process all PDFs in original folder
        pdf_files = list(Path("original").glob("*.pdf"))

    if not pdf_files:
        print("Error: No PDF files found")
        sys.exit(1)

    print(f"\n{'='*80}")
    print("100% HAIKU TRANSLATION TEST")
    print("Purpose: Identify source of translation gaps")
    print("Method: Translate EVERYTHING with Haiku (no dictionary, no indexed files)")
    print(f"Found {len(pdf_files)} PDF(s) to process")
    print('='*80)

    start_time = time.time()
    success_count = 0
    total_input_tokens = 0
    total_output_tokens = 0

    for idx, pdf_path in enumerate(pdf_files, 1):
        # Show progress with timer
        elapsed = time.time() - start_time
        print(f"\n[{idx}/{len(pdf_files)}] Processing: {pdf_path.name}")
        print(f"⏱️  Elapsed time: {elapsed:.1f}s")

        if not pdf_path.exists():
            print(f"Error: File not found: {pdf_path}")
            continue

        # Create output filename
        output_name = pdf_path.stem + " - HAIKU100TEST.pdf"
        output_path = os.path.join(TRANSLATED_FOLDER, output_name)

        success, input_tokens, output_tokens = process_pdf(str(pdf_path), output_path, api_key)
        if success:
            success_count += 1
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

    # Final summary
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = total_time % 60

    if minutes > 0:
        time_str = f"{minutes}m {seconds:.1f}s"
    else:
        time_str = f"{seconds:.1f}s"

    # Calculate cost (Haiku 4.5 pricing: $1.00/1M input, $5.00/1M output)
    total_tokens = total_input_tokens + total_output_tokens
    cost_input = (total_input_tokens / 1_000_000) * 1.00
    cost_output = (total_output_tokens / 1_000_000) * 5.00
    total_cost = cost_input + cost_output

    print(f"\n{'='*80}")
    print(f"ALL TESTS COMPLETE! Successfully processed {success_count}/{len(pdf_files)} PDFs")
    print(f"⏱️  Total time: {time_str}")
    print(f"\n📊 TOKEN USAGE:")
    print(f"   Input tokens:  {total_input_tokens:,}")
    print(f"   Output tokens: {total_output_tokens:,}")
    print(f"   Total tokens:  {total_tokens:,}")
    print(f"\n💰 ESTIMATED COST:")
    print(f"   Input:  ${cost_input:.4f}")
    print(f"   Output: ${cost_output:.4f}")
    print(f"   TOTAL:  ${total_cost:.4f} USD")
    print(f"\nOutput folder: {TRANSLATED_FOLDER}")
    print("\nNext step: Check the PDFs for any remaining French words")
    print("If there are NO gaps → Problem was missing dictionary/indexed entries")
    print("If there ARE gaps → Problem is PDF text extraction")
    print('='*80)

if __name__ == "__main__":
    main()
