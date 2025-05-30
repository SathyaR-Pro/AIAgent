import requests
import sqlite3
from datetime import datetime, timedelta
import os
import sys
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from data_pipeline.db_setup import get_db_connection, initialize_db

logger = logging.getLogger(__name__)

def fetch_executive_orders_and_load(days: int = 60):
    logger.info("Starting data pipeline: Fetching executive orders...")
    initialize_db() 

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days -1)

    params = {
        'per_page': 50,
        'order': 'newest',
        
        'conditions[publication_date][gte]': start_date.strftime('%Y-%m-%d'),
        'conditions[publication_date][lte]': end_date.strftime('%Y-%m-%d'),
        'conditions[type]': settings.EXECUTIVE_ORDER_DOCUMENT_TYPE
    }

    logger.info(f"Fetching from Federal Register API for dates {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")
    
    conn = None
    try:
        response = requests.get(settings.FEDERAL_REGISTER_API_BASE_URL, params=params)
        response.raise_for_status() 
        data = response.json()
        
        documents = data.get('results', [])
        logger.info(f"Found {len(documents)} executive orders in the API response.")

        conn = get_db_connection()
        cursor = conn.cursor()

        inserted_count = 0
        
        for doc in documents:
            document_number = doc.get('document_number')
            document_type = doc.get('type')
            title = doc.get('title')
            publication_date = doc.get('publication_date')
            abstract_html_url = doc.get('abstract_html_url')
            html_url = doc.get('html_url')
            retrieval_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            abstract_text = None
            if abstract_html_url:
                try:
                    abstract_response = requests.get(abstract_html_url, timeout=5)
                    abstract_response.raise_for_status()
                    abstract_text = abstract_response.text.strip()
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Could not fetch abstract for {document_number} from {abstract_html_url}: {e}")
                    abstract_text = "Abstract fetch failed."

            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO federal_documents (
                        document_number, document_type, title, publication_date, abstract, html_url, retrieval_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (document_number, document_type, title, publication_date, abstract_text, html_url, retrieval_date))
                
                inserted_count += 1 
                    
            except sqlite3.Error as e:
                logger.error(f"Error inserting/updating document {document_number}: {e}")


        conn.commit()
        logger.info(f"Data ingestion complete. Processed and stored/updated: {inserted_count} documents from API.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching data from Federal Register API: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during data fetching: {e}")
    finally:
        if conn:
            conn.close()
        logger.info("Data pipeline finished.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    logger.info("Running data loading script directly.")
    fetch_executive_orders_and_load(days=60)
    
    # Add a check to confirm data in the database
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM federal_documents")
        count = cursor.fetchone()[0]
        logger.info(f"Currently {count} documents in the 'federal_documents' table.")
        conn.close()
    except Exception as e:
        logger.error(f"Error checking document count in database: {e}")