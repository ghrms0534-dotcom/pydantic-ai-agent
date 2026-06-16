import asyncio
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.config import Settings  # noqa: E402


CHECK_INTERVAL_SECONDS = 30


async def check_ollama_connection() -> None:
    settings = Settings()
    print(f"OLLAMA_BASE_URL={settings.ollama_base_url}", flush=True)
    print(f"OLLAMA_MODEL={settings.ollama_model}", flush=True)

    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=10.0) as client:
        response = await client.get("/api/tags")
        response.raise_for_status()
        data = response.json()

    models = {model.get("name") for model in data.get("models", [])}
    print("Ollama connection OK", flush=True)
    print(f"Configured model: {settings.ollama_model}", flush=True)

    if settings.ollama_model in models:
        print("Configured model is available locally.", flush=True)
    else:
        print(f"Configured model was not found locally: {settings.ollama_model}", flush=True)


async def run_worker() -> None:
    print("maos worker started.", flush=True)
    while True:
        try:
            await check_ollama_connection()
        except Exception as exc:
            print(f"Ollama health check failed: {exc}", flush=True)

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        print("maos worker stopped.", flush=True)


if __name__ == "__main__":
    main()
