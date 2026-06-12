"""Print a random APP_SECRET_KEY. Run: python -m lumi.scripts.generate_secret_key"""

import secrets


def main() -> None:
    print(secrets.token_urlsafe(48))


if __name__ == "__main__":
    main()
