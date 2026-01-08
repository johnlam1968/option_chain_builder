from config import DATABASE_URL
from sqlmodel import Field, SQLModel, create_engine, Session
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

def store_data(option_data: List[Dict[str, str]]) -> None:
    with Session(engine) as orm_session:
        for data in option_data:
            orm_session.merge(OptionChain(**data))
        orm_session.commit()