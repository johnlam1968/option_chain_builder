from settings.config import DATABASE_URL
from sqlmodel import Field, SQLModel, create_engine, Session, select
from typing import List, Dict

# Replace 'localhost' with 'db' if Python is inside the Docker network
engine = create_engine(DATABASE_URL)
SQLModel.metadata.create_all(engine)


class OptionChain(SQLModel, table=True):
    conid: str = Field(primary_key=True)
    symbol: str
    maturity_date: str
    strike: str
    right: str

def store_data(option_data: List[Dict[str, str | None]]) -> None:
    """Store option chain data in the database.
    
    Args:
        option_data: List of dictionaries containing option contract data
    """
    with Session(engine) as orm_session:
        for data in option_data:
            # Filter out None values before creating OptionChain
            filtered_data = {k: v for k, v in data.items() if v is not None}
            if filtered_data:  # Only merge if we have valid data
                orm_session.merge(OptionChain(**filtered_data))
        orm_session.commit()

def query_option_chain(symbol: str) -> List[Dict[str, str]]:
    """
    Query option chain data from the database for a specific symbol (underlier).
    
    Args:
        symbol: Stock/ETF/Index symbol to query (e.g., "SPY", "CL", "ES")
        
    Returns:
        List of dictionaries containing option contract data for the symbol.
        Each dictionary contains: conid, symbol, maturity_date, strike, right
    """
    with Session(engine) as orm_session:
        # Query all records matching the symbol
        statement = select(OptionChain).where(OptionChain.symbol == symbol)
        results = orm_session.exec(statement).all()
        
        # Convert to list of dictionaries
        data = []
        for result in results:
            data.append({
                "conid": result.conid,
                "symbol": result.symbol,
                "maturity_date": result.maturity_date,
                "strike": result.strike,
                "right": result.right
            })
        
        return data
