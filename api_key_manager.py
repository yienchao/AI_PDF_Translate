"""API Key Manager for rotating Anthropic API keys"""
import os
import threading
import time
from typing import Optional, List
from datetime import datetime, timedelta


class APIKeyManager:
    """Manages rotation of multiple Anthropic API keys to avoid rate limits"""

    def __init__(self, api_keys: Optional[List[str]] = None):
        """
        Initialize API Key Manager

        Args:
            api_keys: List of API keys. If None, loads from environment variables
        """
        if api_keys:
            self.api_keys = api_keys
        else:
            # Load from environment - supports ANTHROPIC_API_KEY, ANTHROPIC_API_KEY_1, _2, _3, etc.
            self.api_keys = []

            # Try main key first
            main_key = os.environ.get("ANTHROPIC_API_KEY")
            if main_key:
                self.api_keys.append(main_key)

            # Try numbered keys
            i = 1
            while True:
                key = os.environ.get(f"ANTHROPIC_API_KEY_{i}")
                if key:
                    self.api_keys.append(key)
                    i += 1
                else:
                    break

        if not self.api_keys:
            raise ValueError("No API keys found. Set ANTHROPIC_API_KEY or ANTHROPIC_API_KEY_1, _2, etc.")

        # Track usage per key
        self.key_usage = {key: {
            "requests": 0,
            "last_used": None,
            "tokens": 0,
            "errors": 0,
            "rate_limited_until": None
        } for key in self.api_keys}

        self.current_index = 0
        self.lock = threading.Lock()

        print(f"[OK] API Key Manager initialized with {len(self.api_keys)} key(s)")

    def get_next_key(self) -> str:
        """
        Get next available API key using round-robin rotation

        Returns:
            API key string
        """
        with self.lock:
            # Try up to len(api_keys) times to find non-rate-limited key
            attempts = 0
            while attempts < len(self.api_keys):
                key = self.api_keys[self.current_index]
                usage = self.key_usage[key]

                # Check if key is rate limited
                if usage["rate_limited_until"]:
                    if datetime.now() < usage["rate_limited_until"]:
                        # Still rate limited, try next key
                        self.current_index = (self.current_index + 1) % len(self.api_keys)
                        attempts += 1
                        continue
                    else:
                        # Rate limit expired, clear it
                        usage["rate_limited_until"] = None

                # Found available key
                usage["requests"] += 1
                usage["last_used"] = datetime.now()

                # Move to next key for next request (round-robin)
                self.current_index = (self.current_index + 1) % len(self.api_keys)

                return key

            # All keys are rate limited, return least recently used
            print("[WARNING] All API keys are rate limited, using least recently used")
            return min(
                self.api_keys,
                key=lambda k: self.key_usage[k]["last_used"] or datetime.min
            )

    def mark_rate_limited(self, api_key: str, duration_seconds: int = 60):
        """
        Mark an API key as rate limited

        Args:
            api_key: The API key to mark
            duration_seconds: How long to mark it as limited (default 60s)
        """
        with self.lock:
            if api_key in self.key_usage:
                self.key_usage[api_key]["rate_limited_until"] = (
                    datetime.now() + timedelta(seconds=duration_seconds)
                )
                self.key_usage[api_key]["errors"] += 1
                print(f"[WARNING] API key marked as rate limited for {duration_seconds}s")

    def mark_error(self, api_key: str):
        """
        Mark an error for an API key

        Args:
            api_key: The API key that encountered an error
        """
        with self.lock:
            if api_key in self.key_usage:
                self.key_usage[api_key]["errors"] += 1

    def record_tokens(self, api_key: str, tokens: int):
        """
        Record token usage for an API key

        Args:
            api_key: The API key used
            tokens: Number of tokens used
        """
        with self.lock:
            if api_key in self.key_usage:
                self.key_usage[api_key]["tokens"] += tokens
                # Auto-reset counters if they grow too large to prevent unbounded memory growth
                if self.key_usage[api_key]["tokens"] > 100_000_000:
                    self._reset_counters_unlocked()

    def get_stats(self) -> dict:
        """
        Get usage statistics for all keys

        Returns:
            Dict with stats per key
        """
        with self.lock:
            return {
                f"key_{i+1}": {
                    "requests": usage["requests"],
                    "tokens": usage["tokens"],
                    "errors": usage["errors"],
                    "last_used": usage["last_used"].isoformat() if usage["last_used"] else None,
                    "is_rate_limited": bool(
                        usage["rate_limited_until"] and
                        datetime.now() < usage["rate_limited_until"]
                    )
                }
                for i, (key, usage) in enumerate(self.key_usage.items())
            }

    def get_total_keys(self) -> int:
        """Get total number of API keys"""
        return len(self.api_keys)

    def _reset_counters_unlocked(self):
        """Reset accumulated counters to prevent unbounded growth. Must be called with lock held."""
        for key in self.key_usage:
            self.key_usage[key]["requests"] = 0
            self.key_usage[key]["tokens"] = 0
            self.key_usage[key]["errors"] = 0
        print("[INFO] API key manager counters reset to prevent memory growth")


# Global instance (singleton pattern)
_key_manager_instance: Optional[APIKeyManager] = None
_key_manager_lock = threading.Lock()


def get_key_manager() -> APIKeyManager:
    """
    Get or create the global API Key Manager instance

    Returns:
        APIKeyManager instance
    """
    global _key_manager_instance

    with _key_manager_lock:
        if _key_manager_instance is None:
            _key_manager_instance = APIKeyManager()
        return _key_manager_instance


def reset_key_manager():
    """Reset the global key manager (useful for testing)"""
    global _key_manager_instance
    with _key_manager_lock:
        _key_manager_instance = None
