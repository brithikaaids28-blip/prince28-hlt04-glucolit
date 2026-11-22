import os
import sys

import httpx


def main():
    base_url = os.getenv("GLUCOLIT_URL", "https://glucolit-main.onrender.com").rstrip("/")

    try:
        response = httpx.get(f"{base_url}/health", timeout=30)
        response.raise_for_status()
        print("Smoke test passed")
        print(response.json())
    except Exception as exc:
        print(f"Smoke test failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
