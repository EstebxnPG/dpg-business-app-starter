import argparse
import getpass

from app.database import get_engine
from app.modules.organizations.use_cases import (
    BootstrapValidationError,
    UserEmailConflictError,
    bootstrap_organization,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an organization and its first administrator."
    )
    parser.add_argument("--name", required=True, help="Organization name")
    parser.add_argument("--admin-email", required=True, help="Administrator email")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = getpass.getpass("Administrator password: ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if password != confirmation:
        print("Bootstrap failed: passwords do not match.")
        return 2

    try:
        result = bootstrap_organization(
            get_engine(),
            organization_name=args.name,
            admin_email=args.admin_email,
            admin_password=password,
        )
    except BootstrapValidationError as error:
        print(f"Bootstrap failed: {error}")
        return 2
    except UserEmailConflictError:
        print("Bootstrap failed: the administrator email already exists.")
        return 3

    print(f"Organization created: {result.organization_id}")
    print(f"Administrator created: {result.admin_user_id} ({result.admin_email})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
