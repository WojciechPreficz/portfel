import getpass
import secrets

from argon2 import PasswordHasher


def main() -> None:
    password = getpass.getpass("Hasło: ")
    if not password:
        raise SystemExit("Hasło nie może być puste.")

    password_hash = PasswordHasher().hash(password)
    secret_key = secrets.token_urlsafe(32)
    print(f"PORTFEL_PASSWORD_HASH={password_hash}")
    print(f"PORTFEL_SECRET_KEY={secret_key}")


if __name__ == "__main__":
    main()
