"""Create only the disposable integration database, never drop user data."""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    if url.database != "grow_test":
        raise RuntimeError("Refusing to manage a database not named grow_test")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        if not connection.scalar(text("SELECT 1 FROM pg_database WHERE datname='grow_test'")):
            connection.execute(text("CREATE DATABASE grow_test"))
    admin.dispose()


if __name__ == "__main__":
    main()
