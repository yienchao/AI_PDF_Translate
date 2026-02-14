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
        file_size_bytes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Log a translation job to the database

        Args:
            user_id: UUID of the user
            original_filename: Original PDF filename
            translated_filename: Translated PDF filename
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
            file_size_bytes: Size of original file in bytes

        Returns:
            Dict with the created translation record
        """
        # Only insert columns that exist in the translations table
        data = {
            "original_filename": original_filename,
            "translated_filename": translated_filename,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

        if user_id is not None:
            data["user_id"] = user_id

        if file_size_bytes is not None:
            data["file_size_bytes"] = file_size_bytes

        # Calculate costs
        cost_input = (input_tokens / 1_000_000) * 1.00
        cost_output = (output_tokens / 1_000_000) * 5.00
        data["cost_input_usd"] = round(cost_input, 6)
        data["cost_output_usd"] = round(cost_output, 6)

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
        query = self.client.table("translations").select("*")
        if user_id is not None:
            query = query.eq("user_id", user_id)
        response = query.order("created_at", desc=True).limit(limit).offset(offset).execute()
        return response.data

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get translation statistics for a user

        Args:
            user_id: UUID of the user

        Returns:
            Dict with stats (total_translations, total_tokens_used, total_cost_usd, etc.)
        """
        # Query translations table directly for stats
        query = self.client.table("translations").select("input_tokens, output_tokens, total_tokens")
        if user_id is not None:
            query = query.eq("user_id", user_id)
        response = query.execute()

        if response.data:
            total_translations = len(response.data)
            total_tokens = sum(r.get("total_tokens", 0) or 0 for r in response.data)
            return {
                "total_translations": total_translations,
                "total_tokens_used": total_tokens,
            }
        else:
            return {
                "total_translations": 0,
                "total_tokens_used": 0,
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

    def create_job(
        self,
        user_id: str,
        original_filename: str,
        file_path: str,
        source_language: str,
        target_language: str,
        file_size_bytes: Optional[int] = None,
        priority: int = 0
    ) -> Dict[str, Any]:
        """
        Create a new translation job in the queue

        Args:
            user_id: UUID of the user
            original_filename: Original PDF filename
            file_path: Path to uploaded file
            source_language: Source language
            target_language: Target language
            file_size_bytes: Size of file in bytes
            priority: Job priority (higher = processed first)

        Returns:
            Dict with the created job record
        """
        data = {
            "user_id": user_id,
            "original_filename": original_filename,
            "file_path": file_path,
            "source_language": source_language,
            "target_language": target_language,
            "status": "pending",
            "priority": priority
        }

        if file_size_bytes:
            data["file_size_bytes"] = file_size_bytes

        response = self.client.table("translation_jobs").insert(data).execute()
        return response.data[0] if response.data else {}

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        translated_filename: Optional[str] = None,
        output_path: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        error_message: Optional[str] = None,
        assigned_api_key_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update a translation job

        Args:
            job_id: UUID of the job
            status: New status
            translated_filename: Translated filename
            output_path: Path to output file
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            error_message: Error message if failed
            assigned_api_key_id: Which API key was used

        Returns:
            Updated job record
        """
        data = {}

        if status:
            data["status"] = status
            if status == "processing":
                data["started_at"] = datetime.utcnow().isoformat()
            elif status in ["completed", "failed"]:
                data["completed_at"] = datetime.utcnow().isoformat()

        if translated_filename:
            data["translated_filename"] = translated_filename
        if output_path:
            data["output_path"] = output_path
        if input_tokens is not None:
            data["input_tokens"] = input_tokens
        if output_tokens is not None:
            data["output_tokens"] = output_tokens
        if error_message:
            data["error_message"] = error_message
        if assigned_api_key_id:
            data["assigned_api_key_id"] = assigned_api_key_id

        response = (
            self.client.table("translation_jobs")
            .update(data)
            .eq("id", job_id)
            .execute()
        )
        return response.data[0] if response.data else {}

    def get_user_jobs(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get translation jobs for a user

        Args:
            user_id: UUID of the user
            status: Filter by status (pending, processing, completed, failed)
            limit: Maximum number of records

        Returns:
            List of job records
        """
        query = (
            self.client.table("translation_jobs")
            .select("*")
            .eq("user_id", user_id)
        )

        if status:
            query = query.eq("status", status)

        response = query.order("created_at", desc=True).limit(limit).execute()
        return response.data


# Convenience function to get a configured client
def get_supabase_client() -> SupabaseHelper:
    """Get a configured Supabase client from environment variables"""
    return SupabaseHelper()
