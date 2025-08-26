from __future__ import annotations

from .env import get_settings


def main() -> None:
    settings = get_settings()
    print("SECRET=", settings.secret)


if __name__ == "__main__":
    main() 