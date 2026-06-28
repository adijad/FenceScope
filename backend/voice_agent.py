# backend/voice_agent.py

import os
import tempfile
from pathlib import Path

from fastapi import UploadFile
from openai import OpenAI


MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB safety limit


def _suffix_from_filename(filename: str | None) -> str:
    if not filename:
        return ".wav"

    suffix = Path(filename).suffix.lower()

    if suffix in [".wav", ".mp3", ".m4a", ".webm", ".ogg", ".mp4", ".mpeg", ".mpga"]:
        return suffix

    return ".wav"


async def transcribe_project_audio(audio_file: UploadFile) -> dict:
    """
    Transcribes customer voice intake into text.

    This function only transcribes audio.
    It does not extract estimate fields, calculate pricing, save an estimate,
    or run compliance.
    """

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    audio_bytes = await audio_file.read()

    if not audio_bytes:
        raise ValueError("No audio file was uploaded.")

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise ValueError("Audio file is too large. Please record a shorter message.")

    model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    suffix = _suffix_from_filename(audio_file.filename)

    prompt = (
        "The speaker is describing a residential fence quote request. "
        "Important terms may include wood privacy fence, vinyl privacy fence, "
        "chain link, aluminum, split rail, backyard, front yard, side yard, "
        "linear feet, gates, double gates, old fence removal, slope, access, "
        "HOA, permit, property line, dogs, pool, and timeline."
    )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        client = OpenAI()

        with open(temp_path, "rb") as file_handle:
            transcription = client.audio.transcriptions.create(
                model=model,
                file=file_handle,
                prompt=prompt,
            )

        transcript_text = getattr(transcription, "text", "")

        if not transcript_text or not transcript_text.strip():
            raise RuntimeError("Transcription completed, but no text was returned.")

        return {
            "transcript": transcript_text.strip(),
            "model": model,
            "filename": audio_file.filename or "voice_project.wav",
            "content_type": audio_file.content_type,
        }

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)