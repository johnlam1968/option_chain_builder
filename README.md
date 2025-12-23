# Option Chain App

This is a simple app to build an option chain using IBKR Web API, via ibind client which handles OAuth.

## Feature:
    Secret files are pre-made and store locally. No user login is required.

## Setup

1. Install the required dependencies:
   ```bash
   pip install ibind
   ```

2. Configure the API client:
   - Update the `config.py` file with your API base URL and authentication token.

## Usage

1. Run the main script:
   ```bash
   python src/infrastructure/option_chain_app/main.py
   ```

2. The script will retrieve option chain data for the specified symbol (default: "SPX") and save the Contract IDs to a CSV file named `option_chain_dataset.csv`.

## Files

- `config.py`: Configuration file for the API client.
- `api_client.py`: Handles interactions with the IBKR API.
- `data_loader.py`: Retrieves and processes option chain data.
- `main.py`: Entry point of the application.
- `README.md`: This file.
