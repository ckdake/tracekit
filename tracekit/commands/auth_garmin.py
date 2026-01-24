"""Authentication command for Garmin Connect.

This module provides authentication for Garmin Connect using the garminconnect library.
It stores OAuth tokens that are valid for about a year to avoid frequent re-authentication.

Remove Garmin env vars from your .evn file to re-authenticate!
"""

import os
from getpass import getpass
from pathlib import Path

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
    """Authenticate with Garmin Connect and store tokens."""
    if garminconnect is None:
        print("Error: garminconnect library not installed.")
        print("Please install it with: pip install garminconnect")
        return

    # Check for existing tokens first
    tokenstore = os.getenv("GARMINTOKENS", "~/.garminconnect")
    tokenstore_path = Path(tokenstore).expanduser()

    if tokenstore_path.exists():
        print(f"Found existing Garmin tokens in: {tokenstore_path}")
        choice = input("Test existing tokens? (y/n): ").lower().strip()
        if choice == "y":
            try:
                print("Testing existing tokens...")
                garmin = garminconnect.Garmin()
                garmin.login(str(tokenstore_path))
                print(f"✓ Successfully authenticated as: {garmin.get_full_name()}")
                print("Existing tokens are still valid!")
                print("\nAdd these to your .env file if not already present:")
                print(f"GARMINTOKENS={tokenstore_path}")
                return
            except (
                FileNotFoundError,
                GarthHTTPError,
                GarminConnectAuthenticationError,
            ) as e:
                print(f"✗ Existing tokens are expired or invalid: {e}")
                print("Will proceed with fresh authentication...")

    # Get credentials
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email:
        email = input("Garmin Connect email: ")
    if not password:
        password = getpass("Garmin Connect password: ")

    try:
        print("\nAuthenticating with Garmin Connect...")

        # Create Garmin client with MFA support
        garmin = garminconnect.Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)

        # Attempt login - returns (result, data) tuple in v0.2.28
        result, data = garmin.login()

        # Handle MFA if required
        if result == "needs_mfa":
            print("Multi-factor authentication required.")
            mfa_code = get_mfa()
            garmin.resume_login(data, mfa_code)

        # Save tokens
        garmin.garth.dump(str(tokenstore_path))

        print(f"✓ Successfully authenticated as: {garmin.get_full_name()}")
        print(f"✓ Tokens saved to: {tokenstore_path}")

        print("\nAdd these lines to your .env file:")
        print(f"GARMIN_EMAIL={email}")
        print(f"GARMINTOKENS={tokenstore_path}")
        print("\nNote: Password is not stored - tokens are valid for about a year")

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
