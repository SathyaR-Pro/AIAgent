import sqlite3
import os
import sys
import logging

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from config.settings import settings

logger = logging.getLogger(__name__)


def get_db_connection():
    db_path = settings.DATABASE_URL 
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row # Allows accessing columns by name (e.g., row['title'])
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database at {db_path}: {e}")
        raise # Re-raise the exception so calling functions can handle it


def initialize_db():
    conn = None
    try:
        conn = get_db_connection() # Get a connection using the corrected path
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS federal_documents (
                document_number TEXT PRIMARY KEY,
                document_type TEXT NOT NULL,
                title TEXT NOT NULL,
                publication_date TEXT NOT NULL,
                abstract TEXT,
                html_url TEXT NOT NULL UNIQUE,
                retrieval_date TEXT NOT NULL
            )
        ''')
        conn.commit()
        logger.info(f"Database '{settings.DATABASE_URL}' initialized successfully. Table 'federal_documents' ensured.")
    except sqlite3.Error as e:
        logger.error(f"Error initializing database: {e}")
        raise 
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # This block runs only when db_setup.py is executed directly
    print(f"Database path from settings: {settings.DATABASE_URL}")
    try:
        initialize_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='federal_documents';")
        if cursor.fetchone():
            print("Table 'federal_documents' exists and is ready.")
        else:
            print("Table 'federal_documents' does NOT exist (initialization failed).")
        conn.close()
    except Exception as e:
        print(f"Test connection or database initialization failed: {e}")