"""Supabase Client Helper for PDF Translation App"""
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from supabase import create_client, Client

class SupabaseHelper:
    """Helper class for Supabase operations"""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """
        Initialize Supabase client

        Args:
            url: Supabase project URL (defaults to SUPABASE_URL env var)
            key: Supabase anon key (defaults to SUPABASE_KEY env var)
        """
        self.url = url or os.environ.get("SUPABASE_URL")
        self.key = key or os.environ.get("SUPABASE_KEY")

        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables must be set")

        self.client: Client = create_client(self.url, self.key)

    def sign_in(self, email: str, password: str) -> Dict[str, Any]:
        """
        Sign in user with email and password

        Args:
            email: User email
            password: User password

        Returns:
            Dict with user data and session info

        Raises:
            Exception if sign in fails
        """
        response = self.client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return response

    def sign_out(self) -> None:
        """Sign out current user"""
        self.client.auth.sign_out()

    def get_user(self) -> Optional[Dict[str, Any]]:
        """
        Get current authenticated user

        Returns:
            User data dict or None if not authenticated
        """
        try:
            user = self.client.auth.get_user()
            return user
        except Exception:
            return None

    def log_translation(
        self,
        user_id: str,
        original_filename: str,
        translated_filename: str,
        input_tokens: int,
        output_tokens: int,
        file_size_bytes: Optional[int] = None,
        status: str = "completed",
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Log a translation job to the database

        Args:
            user_id: UUID of the user
            original_filename: Original French PDF filename
            translated_filename: Translated English PDF filename
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
            file_size_bytes: Size of original file in bytes
            status: Status of translation (processing, completed, failed)
            error_message: Error message if failed

        Returns:
            Dict with the created translation record
        """
        data = {
            "user_id": user_id,
            "original_filename": original_filename,
            "translated_filename": translated_filename,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "status": status,
        }

        if file_size_bytes is not None:
            data["file_size_bytes"] = file_size_bytes

        if status == "completed":
            data["completed_at"] = datetime.utcnow().isoformat()

        if error_message:
            data["error_message"] = error_message

        response = self.client.table("translations").insert(data).execute()
        return response.data[0] if response.data else {}

    def get_user_translations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get translation history for a user

        Args:
            user_id: UUID of the user
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of translation records
        """
        response = (
            self.client.table("translations")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .offset(offset)
            .execute()
        )
        return response.data

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get translation statistics for a user

        Args:
            user_id: UUID of the user

        Returns:
            Dict with stats (total_translations, total_tokens_used, total_cost_usd, etc.)
        """
        response = (
            self.client.table("user_translation_stats")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )

        if response.data:
            return response.data[0]
        else:
            # Return empty stats if user has no translations yet
            return {
                "user_id": user_id,
                "total_translations": 0,
                "total_tokens_used": 0,
                "total_cost_usd": 0.0,
                "last_translation_at": None
            }

    def update_translation_status(
        self,
        translation_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update translation status (e.g., from processing to completed)

        Args:
            translation_id: UUID of the translation record
            status: New status (processing, completed, failed)
            error_message: Error message if failed

        Returns:
            Updated translation record
        """
        data = {"status": status}

        if status == "completed":
            data["completed_at"] = datetime.utcnow().isoformat()

        if error_message:
            data["error_message"] = error_message

        response = (
            self.client.table("translations")
            .update(data)
            .eq("id", translation_id)
            .execute()
        )
        return response.data[0] if response.data else {}


# Convenience function to get a configured client
def get_supabase_client() -> SupabaseHelper:
    """Get a configured Supabase client from environment variables"""
    return SupabaseHelper()
