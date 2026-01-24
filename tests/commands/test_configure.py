import json
import os
import tempfile

import tracekit.commands.configure as configure


def test_run_creates_config_file(monkeypatch):
    """Test that configure.run() prompts for input and creates a config file."""

    # Prepare fake user input for all prompts
    inputs = iter(
        [
            "US/Pacific",  # Home timezone
            "y",  # Debug mode
            "",  # Database path (use default)
            "Y",  # Enable spreadsheet provider
            "/tmp/fake_spreadsheet.xlsx",  # Spreadsheet path
            "1",  # Spreadsheet priority
            "Y",  # Enable file provider
            "./fake_glob/*",  # File glob
            "Y",  # Enable Strava provider
            "3",  # Strava priority
            "Y",  # Enable RideWithGPS provider
            "2",  # RideWithGPS priority
            "Y",  # Enable Garmin provider
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    # Use a temp directory for config file
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "tracekit_config.json")
        monkeypatch.setattr("os.path.abspath", lambda path: config_path)

        configure.run()

        assert os.path.exists(config_path)
        with open(config_path) as f:
            config = json.load(f)

        # Check top-level settings
        assert config["home_timezone"] == "US/Pacific"
        assert config["debug"]
        assert config["provider_priority"] == "spreadsheet,ridewithgps,strava"

        # Check providers block
        assert "providers" in config

        # Check spreadsheet provider
        assert config["providers"]["spreadsheet"]["enabled"]
        assert config["providers"]["spreadsheet"]["path"] == "/tmp/fake_spreadsheet.xlsx"
        assert config["providers"]["spreadsheet"]["priority"] == 1

        # Check file provider
        assert config["providers"]["file"]["enabled"]
        assert config["providers"]["file"]["glob"] == "./fake_glob/*"

        # Check Strava provider
        assert config["providers"]["strava"]["enabled"]
        assert config["providers"]["strava"]["priority"] == 3

        # Check RideWithGPS provider
        assert config["providers"]["ridewithgps"]["enabled"]
        assert config["providers"]["ridewithgps"]["priority"] == 2

        # Check Garmin provider
        assert config["providers"]["garmin"]["enabled"]

        # Check StravaJSON provider (should be disabled by default)
        assert not config["providers"]["stravajson"]["enabled"]
