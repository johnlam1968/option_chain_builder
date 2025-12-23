def store(maturity_date: str, call_conid: str, put_conid: str) -> dict[str, tuple[str, str]]:
    _dict: dict[str, tuple[str, str]] = {}
    _dict.setdefault(maturity_date, (call_conid, put_conid))
    return _dict

def write_csv(symbol: str, df, file_path: str = "option_chain_dataset.csv") -> None:
    import csv
    with open(file_path, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        columns = ["symbol", "maturity_date", "strike", "call_conid", "put_conid"]
        writer.writerow(columns)
        for _, row in df.iterrows():
            writer.writerow([row["symbol"], row["maturity_date"], row["strike"], row["call_conid"], row["put_conid"]])
