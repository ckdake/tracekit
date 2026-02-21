"""Authentication command for Garmin Connect.

This module provides authentication for Garmin Connect using the garminconnect library.
It stores OAuth tokens in the database (valid for about a year) to avoid frequent
re-authentication.
"""

from getpass import getpass

try:
    import garminconnect
    from garminconnect import (
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )
    from garth.exc import GarthHTTPError
except ImportError:
    garminconnect = None


def get_mfa():
    """Get MFA code from user."""
    return input("MFA one-time code: ")


def run():
    """Authenticate with Garmin Connect and store tokens in the database."""
    if garminconnect is None:
        print("Error: garminconnect library not installed.")
        print("Please install it with: pip install garminconnect")
        return

    from tracekit.appconfig import load_config, save_config

    config = load_config()
    garmin_cfg = config.get("providers", {}).get("garmin", {})
    existing_tokens = garmin_cfg.get("garth_tokens", "").strip()
    email = garmin_cfg.get("email", "").strip()

    # Test existing DB tokens first if present
    if existing_tokens:
        print("Found existing Garmin tokens in database.")
        choice = input("Test existing tokens? (y/n): ").lower().strip()
        if choice == "y":
            try:
                print("Testing existing tokens...")
                garmin = garminconnect.Garmin()
                garmin.login(existing_tokens)
                print(f"✓ Successfully authenticated as: {garmin.get_full_name()}")
                print("Existing tokens are still valid.")
                return
            except (
                GarthHTTPError,
                GarminConnectAuthenticationError,
            ) as e:
                print(f"✗ Existing tokens are expired or invalid: {e}")
                print("Will proceed with fresh authentication...")

    # Prompt for credentials
    if not email:
        email = input("Garmin Connect email: ")
    password = getpass("Garmin Connect password: ")

    try:
        print("\nAuthenticating with Garmin Connect...")

        garmin = garminconnect.Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)

        # Attempt login — returns (result, data) tuple
        result, data = garmin.login()

        # Handle MFA if required
        if result == "needs_mfa":
            print("Multi-factor authentication required.")
            mfa_code = get_mfa()
            garmin.resume_login(data, mfa_code)

        # Serialize tokens and save to DB
        garth_tokens = garmin.garth.dumps()

        providers = config.get("providers", {})
        garmin_updated = providers.get("garmin", {}).copy()
        garmin_updated["email"] = email
        garmin_updated["garth_tokens"] = garth_tokens
        providers["garmin"] = garmin_updated
        save_config({**config, "providers": providers})

        print(f"✓ Successfully authenticated as: {garmin.get_full_name()}")
        print("✓ Garmin tokens saved to database.")

    except GarminConnectAuthenticationError as e:
        print(f"✗ Authentication failed: {e}")
        print("Please check your email and password.")
    except GarminConnectConnectionError as e:
        print(f"✗ Connection error: {e}")
        print("Please check your internet connection.")
    except GarminConnectTooManyRequestsError as e:
        print(f"✗ Rate limit exceeded: {e}")
        print("Please wait and try again later.")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
