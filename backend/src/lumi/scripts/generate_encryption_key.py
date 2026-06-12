"""Print a Fernet ENCRYPTION_KEY. Run: python -m lumi.scripts.generate_encryption_key"""

from cryptography.fernet import Fernet


def main() -> None:
    print(Fernet.generate_key().decode())


if __name__ == "__main__":
    main()
