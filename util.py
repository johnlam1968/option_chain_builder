def store(maturity_date: str, call_conid: str, put_conid: str) -> dict[str, tuple[str, str]]:
    _dict: dict[str, tuple[str, str]] = {}
    _dict.setdefault(maturity_date, (call_conid, put_conid))
    return _dict

def write_csv(symbol: str, dict: dict[str, dict[str, tuple[str, str]]], file_path: str = "option_chain_dataset.csv") -> None:
    import csv
    with open(file_path, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        columns = ["symbol", "expiration", "strike", "right", "conid"]
        writer.writerow(columns)
        for expiration, strike_dict in dict.items():
            call_conid, put_conid = strike_dict[expiration]
            writer.writerow([symbol, expiration, "call", call_conid])
            writer.writerow([symbol, expiration, "put", put_conid])

