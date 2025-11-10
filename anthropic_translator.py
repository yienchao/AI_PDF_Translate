"""Anthropic API Translation Helper using Claude Haiku 4.5"""
import json
from anthropic import Anthropic

# Configuration constants
HAIKU_MODEL = "claude-haiku-4-5-20251001"
HAIKU_MAX_OUTPUT_TOKENS = 8000
HAIKU_DEFAULT_BATCH_SIZE = 50
HAIKU_MAX_TOKENS_PER_BATCH = 15000
CHARS_PER_TOKEN = 3  # Conservative estimate: 1 token per 3 chars

def estimate_tokens(text: str) -> int:
    """
    Rough token estimation: ~1 token per 3 characters
    This is a conservative estimate to avoid hitting limits
    """
    return len(text) // CHARS_PER_TOKEN

def translate_with_haiku(texts: dict, api_key: str, source_lang: str = "French", target_lang: str = "English") -> dict:
    """
    Translate texts using Claude Haiku 4.5

    Args:
        texts: Dict of {index: text_to_translate}
        api_key: Anthropic API key
        source_lang: Source language (e.g., "French", "English", "Spanish")
        target_lang: Target language (e.g., "English", "French", "Spanish")

    Returns:
        Dict of {index: translated_text}
    """
    client = Anthropic(api_key=api_key)

    # Prepare prompt
    prompt = f"""You are translating architectural/construction documents from {source_lang} to {target_lang}.

Translate the following {source_lang} texts to {target_lang}. Return ONLY a JSON object with the same keys.

**IMPORTANT RULES:**
- Complete translations only - NO {source_lang} words in output
- Maintain technical terminology accuracy
- "SIC" means "AS SUCH" or "SUCH"
- Keep abbreviations like "mm", "GA", "TYP."
- Preserve formatting (parentheses, dashes, etc.)
- Material codes stay as-is (DOM, INTL, etc.)
- DO NOT use emojis or special Unicode characters - text only
- DO NOT use arrow symbols, en/em dashes, smart quotes, or ellipsis
- Use ONLY basic ASCII characters: regular hyphens (-), regular quotes ("), regular apostrophes (')

{source_lang} texts to translate:
{json.dumps(texts, ensure_ascii=False, indent=2)}

Return format:
{{
  "index1": "English translation 1",
  "index2": "English translation 2",
  ...
}}

Return ONLY the JSON, no markdown code blocks."""

    # Call Claude Haiku 4.5
    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=HAIKU_MAX_OUTPUT_TOKENS,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    # Parse response
    response_text = message.content[0].text.strip()

    # Remove markdown code blocks if present
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])  # Remove first and last lines
    if response_text.startswith("json"):
        response_text = response_text[4:].strip()

    # Parse JSON
    try:
        translations = json.loads(response_text)

        # Sanitize all translated text: replace Unicode characters that cause PDF encoding issues
        sanitized_translations = {}
        for key, text in translations.items():
            if isinstance(text, str):
                # Replace problematic Unicode characters with ASCII equivalents
                text = text.replace('\u2192', '->')  # → arrow
                text = text.replace('\u2013', '-')  # en dash
                text = text.replace('\u2014', '--')  # em dash
                text = text.replace('\u2018', "'")  # left single quote
                text = text.replace('\u2019', "'")  # right single quote
                text = text.replace('\u201c', '"')  # left double quote
                text = text.replace('\u201d', '"')  # right double quote
                text = text.replace('\u2026', '...')  # ellipsis
            sanitized_translations[key] = text

        # Return translations with token usage
        return {
            "translations": sanitized_translations,
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens
        }
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse API response as JSON: {e}\n\nResponse:\n{response_text}")


def translate_batch(texts: dict, api_key: str, batch_size: int = HAIKU_DEFAULT_BATCH_SIZE, source_lang: str = "French", target_lang: str = "English", progress_callback=None, max_tokens_per_batch: int = HAIKU_MAX_TOKENS_PER_BATCH) -> dict:
    """
    Translate texts in batches to avoid token limits

    Args:
        texts: Dict of {index: text_to_translate}
        api_key: Anthropic API key
        batch_size: Maximum number of texts per API call (overridden by token limit)
        source_lang: Source language
        target_lang: Target language
        progress_callback: Optional callback function(current, total) for progress updates
        max_tokens_per_batch: Maximum estimated tokens per batch (default 15000, safe for 200K context)

    Returns:
        Dict with "translations" and token usage stats
    """
    all_translations = {}
    total_input_tokens = 0
    total_output_tokens = 0

    # Convert to list of items for batching
    items = list(texts.items())

    # Create dynamic batches based on token estimation
    batches = []
    current_batch = {}
    current_tokens = 0

    for key, text in items:
        estimated_tokens = estimate_tokens(text)

        # If adding this item would exceed limits, start new batch
        if current_batch and (len(current_batch) >= batch_size or current_tokens + estimated_tokens > max_tokens_per_batch):
            batches.append(current_batch)
            current_batch = {}
            current_tokens = 0

        current_batch[key] = text
        current_tokens += estimated_tokens

    # Add final batch if not empty
    if current_batch:
        batches.append(current_batch)

    total_batches = len(batches)

    # Process batches
    for batch_num, batch in enumerate(batches, 1):
        result = translate_with_haiku(batch, api_key, source_lang=source_lang, target_lang=target_lang)
        all_translations.update(result["translations"])
        total_input_tokens += result["input_tokens"]
        total_output_tokens += result["output_tokens"]

        # Call progress callback if provided
        if progress_callback:
            progress_callback(batch_num, total_batches)

    return {
        "translations": all_translations,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens
    }


if __name__ == "__main__":
    # Test
    test_texts = {
        "1": "NOTES GÉNÉRALES",
        "2": "SALLE D'EMBARQUEMENT - DOM",
        "3": "SIC, TOUS LES CONDUITS ÉLECTRIQUE ET MÉCANIQUE SONT ENCASTRÉS."
    }

    # You need to set your API key
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        result = translate_with_haiku(test_texts, api_key)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Set ANTHROPIC_API_KEY environment variable to test")
