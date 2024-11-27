"""
This helper script checks that the provided `min_version` and `max_version` are supported and released, respectively,
using the API from the great https://github.com/endoflife-date/endoflife.date project.
"""
import sys
import requests
from datetime import datetime


def main() -> None:
    # Fetch supported Python versions and check min/max versions
    try:
        response = requests.get("https://endoflife.date/api/python.json")
        response.raise_for_status()
        eol_data = response.json()
        eol_versions = {entry["cycle"]: {"eol": entry["eol"], "releaseDate": entry["releaseDate"]} for entry in eol_data}

        # Get the currently used Python version
        current_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        eol_date = eol_versions[current_version]["eol"]
        release_date = eol_versions[current_version]["releaseDate"]

        # Get current date to compare with EoL and release dates
        current_date = datetime.now().date()

        # Check EoL status
        if datetime.strptime(eol_date, "%Y-%m-%d").date() <= current_date:
            print(f"Error: The used version {current_version} has reached End-of-Life.")
            sys.exit(1)

        # Check if a release date in the future
        if datetime.strptime(release_date, "%Y-%m-%d").date() > current_date:
            print(f"Error: The used version {current_version} has not been officially released yet.")
            sys.exit(1)

    except requests.RequestException:
        print("Error: Failed to fetch Python version support data.")
        sys.exit(1)

    print(f"Version check passed: the version [{current_version}] is supported and released.")

if __name__ == "__main__":
    main()
