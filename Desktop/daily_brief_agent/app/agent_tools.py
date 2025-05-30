import logging
import sqlite3
import json 
from datetime import datetime, timedelta

logger = logging.getLogger(__name__) 
DATABASE_NAME = 'federal_register.db'

# --- Define tool schema as a plain Python Dictionary for Ollama ---
SEARCH_FEDERAL_EXECUTIVE_ORDERS_SCHEMA_DICT = {
    "type": "function",
    "function": {
        "name": "search_federal_executive_orders",
        "description": (
            "Searches for federal executive orders in the database based on optional keywords and a date range. "
            "Use this to find specific executive orders or those published recently. "
            "Supported date ranges: 'today', 'yesterday', 'last_7_days' (default), 'last_30_days', "
            "'last_year', or a specific date in 'YYYY-MM-DD' format. "
            "Example usage: 'search executive orders for the last 30 days', "
            "'find executive orders related to climate change in 2023', "
            "'executive orders about healthcare since January 1, 2024'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date_range_str": {
                    "type": "string",
                    "description": (
                        "The date range for the search. Options: 'today', 'yesterday', 'last_7_days' (default), "
                        "'last_30_days', 'last_year', or a specific date in 'YYYY-MM-DD' format. "
                        "If not specified, defaults to 'last_7_days'."
                    )
                },
                "query_keywords": {
                    "type": "string",
                    "description": (
                        "Optional keywords to search for in the title or abstract of executive orders. "
                        "E.g., 'national security' or 'economy healthcare'. "
                        "If no specific keywords, this can be omitted or an empty string."
                    )
                }
            },
        }
    }
}

# THIS IS THE VARIABLE THAT main.py SHOULD IMPORT for tool definitions passed to Ollama
ollama_tool_definitions = [
    SEARCH_FEDERAL_EXECUTIVE_ORDERS_SCHEMA_DICT
]
# --- End of Tool Schema Definition ---

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row 
    return conn

def search_federal_executive_orders(query_keywords: str = None, date_range_str: str = "last_7_days") -> str:
    logger.info(f"[Tool Executing] search_federal_executive_orders | Keywords: '{query_keywords}', Date Range: '{date_range_str}'")
    conn = None 
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        today = datetime.now()
        start_date_dt, end_date_dt = None, None

        if date_range_str == "today": start_date_dt = end_date_dt = today
        elif date_range_str == "yesterday": start_date_dt = end_date_dt = today - timedelta(days=1)
        elif date_range_str == "last_7_days": end_date_dt, start_date_dt = today, today - timedelta(days=6)
        elif date_range_str == "last_30_days": end_date_dt, start_date_dt = today, today - timedelta(days=29)
        elif date_range_str == "last_year": end_date_dt, start_date_dt = today, today - timedelta(days=365)
        else:
            try:
                parsed_date = datetime.strptime(date_range_str, "%Y-%m-%d")
                start_date_dt = end_date_dt = parsed_date
            except ValueError:
                logger.warning(f"Unrecognized date_range_str '{date_range_str}', defaulting to last_7_days.")
                end_date_dt, start_date_dt = today, today - timedelta(days=6)

        start_date_str = start_date_dt.strftime("%Y-%m-%d")
        end_date_str = end_date_dt.strftime("%Y-%m-%d")

        query_parts = ["document_type = ?"]
        params = ['Presidential Document'] 

        if start_date_str and end_date_str:
            query_parts.append("SUBSTR(publication_date, 1, 10) BETWEEN ? AND ?")
            params.extend([start_date_str, end_date_str])
        
        if query_keywords and query_keywords.strip():
            keyword_conditions = []
            processed_keywords = query_keywords.strip().lower().split()
            for kw in processed_keywords:
                keyword_conditions.append("(LOWER(title) LIKE ? OR LOWER(abstract) LIKE ?)")
                params.extend([f"%{kw}%", f"%{kw}%"])
            if keyword_conditions:
                query_parts.append("(" + " OR ".join(keyword_conditions) + ")")

        base_sql = "SELECT document_number, title, publication_date, abstract, html_url FROM federal_documents"
        if query_parts:
            query = base_sql + " WHERE " + " AND ".join(query_parts)
        else:
            query = base_sql 
        query += " ORDER BY publication_date DESC LIMIT 10"

        logger.info(f"Executing SQL: {query} with params: {tuple(params)}")
        cursor.execute(query, tuple(params))
        documents_raw = cursor.fetchall()
        documents = []
        for row_raw in documents_raw:
            row_dict = dict(row_raw)
            row_dict['abstract'] = row_dict.get('abstract') or "No abstract available."
            if row_dict.get('publication_date'):
                row_dict['publication_date'] = row_dict['publication_date'].split(' ')[0]
            documents.append(row_dict)
            
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}", exc_info=True)
        return json.dumps({"error": "A database error occurred."}) 
    except Exception as e:
        logger.error(f"Unexpected tool error: {e}", exc_info=True)
        return json.dumps({"error": "An unexpected error occurred in the tool."}) 
    finally:
        if conn: conn.close()

    if not documents:
        logger.info("No documents found.")
        return json.dumps({"message": "No relevant executive orders found matching your criteria in the database."})
    
    logger.info(f"Found {len(documents)} documents.")
    return json.dumps(documents, indent=2)

# This dictionary maps tool names to their callable functions.
available_tools = {
    "search_federal_executive_orders": search_federal_executive_orders,
}