from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.database import get_engine
from src import models

engine = get_engine()
Session = sessionmaker(bind=engine, future=True)

def main() -> None:
    with Session() as session:
        for airport in session.scalars(select(models.Airport)):
            print(f"{airport.icao}: {airport.name} in {airport.country}")
    print("Query vuota")

if __name__ == "__main__":
    main()
