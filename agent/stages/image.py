"""Stage 6: hero image generation via fal.ai Flux Schnell.

Flux Schnell is the cheapest dependable text-to-image model on fal.ai
(~$0.003 per 1MP image) and renders in 1-2 seconds at 4 inference steps.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from agent.config import settings
from agent.db import Topic
from agent.progress import bus


FAL_MODEL = "fal-ai/flux/schnell"
IMAGE_DOWNLOAD_TIMEOUT_S = 30.0


def run(*, topic: Topic, slug: str, date_str: str, run_id: str) -> Path:
    """Generate the hero image and persist it. Returns the saved path."""
    bus.emit(run_id, "image", "Generating hero image...", level="info")
    prompt = _build_image_prompt(topic=topic)
    image_bytes = _call_fal_for_image(prompt=prompt)
    if not image_bytes:
        raise ValueError("fal.ai returned empty image bytes")
    path = _save_image(image_bytes, slug=slug, date_str=date_str)
    bus.emit(run_id, "image", f"Image saved: {path.name}", level="success")
    return path


def _build_image_prompt(*, topic: Topic) -> str:
    """Build a fal.ai prompt that biases for usable blog hero imagery."""
    return (
        f"Editorial photography hero image for a skincare blog post about "
        f"{topic.title}. {topic.category} category aesthetic. "
        "Soft natural lighting, minimal composition, neutral background, "
        "shallow depth of field, no text, no logos, no faces, "
        "magazine quality, high resolution."
    )


def _call_fal_for_image(*, prompt: str) -> bytes:
    """Boundary: invoke fal.ai and return PNG bytes. Mocked in tests."""
    import fal_client

    result = fal_client.run(
        FAL_MODEL,
        arguments={
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "num_inference_steps": 4,  # Schnell is optimised for 1-4 steps
            "num_images": 1,
            "enable_safety_checker": True,
        },
    )
    images = result.get("images") or []
    if not images:
        raise RuntimeError("fal.ai returned no images")
    image_url = images[0]["url"]
    with httpx.Client(timeout=IMAGE_DOWNLOAD_TIMEOUT_S, follow_redirects=False) as client:
        response = client.get(image_url)
        response.raise_for_status()
        return response.content


def _save_image(image_bytes: bytes, *, slug: str, date_str: str) -> Path:
    settings.drafts_dir.mkdir(parents=True, exist_ok=True)
    path = settings.drafts_dir / f"{date_str}-{slug}-hero.png"
    path.write_bytes(image_bytes)
    return path
