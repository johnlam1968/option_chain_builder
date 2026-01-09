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

2. The script will retrieve option chain data for the specified symbol (default: "SPX") and save to a PostgreSQL database in a docker container.
3. docker run -d   --name options-db-container   -e POSTGRES_USER=postgres   -e POSTGRES_PASSWORD=secret   -e POSTGRES_DB=options_db   -p 5432:5432   postgre
