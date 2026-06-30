from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

DB_URL = os.getenv('DB_URL')

engine = create_engine(DB_URL, pool_pre_ping=True)
with engine.connect() as conn:
    print(conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector';")).scalar())