from app.db.base import Base, engine
from app.db import models  # noqa: F401  (import so the models register on Base.metadata)

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("Tables created.")