# app/main.py (Implementing Option 1 for chat output)
import os
import sys
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional 

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

LOG_LEVEL_FROM_ENV = os.environ.get('LOG_LEVEL', 'INFO').upper()
numeric_level = getattr(logging, LOG_LEVEL_FROM_ENV, logging.INFO)
logging.basicConfig(
    level=numeric_level, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__) 
logger.info(f"Application starting. CWD: {os.getcwd()}, Project Root: {project_root}")

dotenv_path = find_dotenv()
if not dotenv_path: logger.warning(".env file not found.")
else: logger.info(f"Loading .env file from: '{dotenv_path}'")
load_dotenv(dotenv_path)

from config.settings import settings 
from app.agent_tools import ollama_tool_definitions, available_tools 
from data_pipeline.db_setup import initialize_db 

logger.info(f"Log level set to: {settings.LOG_LEVEL}") 
logger.info(f"Ollama Model (from settings): '{settings.GEMINI_MODEL_NAME}'")

ollama_client: Any = None 
if settings.GEMINI_MODEL_NAME: 
    try:
        import ollama
        ollama_client = ollama.Client(host=settings.OLLAMA_API_BASE_URL)
        logger.info(f"Ollama client initialized. Model: '{settings.GEMINI_MODEL_NAME}', URL: {settings.OLLAMA_API_BASE_URL}")
    except ImportError: logger.error("ollama package not found."); ollama_client = None
    except Exception as e: logger.error(f"Ollama client init failed: {e}", exc_info=True); ollama_client = None
else:
    logger.warning("Ollama model name not configured. Ollama client not initialized.")

app = FastAPI(
    title="Daily Brief Agent API",
    description="API for interacting with the Daily Brief Agent.",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json" 
)

@app.on_event("startup")
async def startup_event():
    try: initialize_db(); logger.info("DB init check completed.")
    except Exception as e: logger.error(f"DB init failed: {e}", exc_info=True)

frontend_dir = os.path.join(project_root, "frontend")
if not os.path.isdir(frontend_dir): logger.error(f"Frontend dir not found: {frontend_dir}")
else: logger.info(f"Frontend dir confirmed: {os.path.abspath(frontend_dir)}")
templates = Jinja2Templates(directory=frontend_dir)
logger.info(f"Jinja2Templates initialized from: {os.path.abspath(frontend_dir)}")

chat_history: List[Dict[str, str]] = [] 

@app.get("/", response_class=HTMLResponse, summary="Chat interface")
async def read_root(request: Request): 
    logger.info("GET / - Serving index.html")
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logger.error(f"Render index.html error: {e}", exc_info=True)
        return HTMLResponse("<h1>Error</h1><p>Could not load page.</p>", status_code=500)

@app.post("/chat", summary="Process chat message", response_model=None) 
async def chat(user_message: str = Form(...)) -> JSONResponse: 
    global chat_history
    logger.info(f"POST /chat - User message: '{user_message}'")
    
    current_turn_messages: List[Dict[str, Any]] = [] 

    # System prompt focused ONLY on tool invocation for the first call
    system_instruction_text_tool_invocation = """You are an AI assistant with access to a tool called 'search_federal_executive_orders'.
Your primary function is to determine if the user's request requires searching for federal executive orders.
- If the user asks about executive orders, especially with dates or keywords, you MUST call the 'search_federal_executive_orders' tool.
- When calling the tool:
    - For 'query_keywords': Use specific keywords from the user's query. If none, use an empty string.
    - For 'date_range_str': Extract date information (e.g., "last_30_days", "YYYY-MM-DD"). Default to "last_7_days" if unclear.
- If the request is not about finding executive orders, respond conversationally.
- **Do NOT answer about executive order listings from your own knowledge. If a search is needed, your ONLY action is to call the tool.**
"""
    current_turn_messages.append({"role": "system", "content": system_instruction_text_tool_invocation})
    for entry in chat_history: current_turn_messages.append(entry) 
    current_turn_messages.append({"role": "user", "content": user_message})

    final_agent_response_text = "I'm sorry, an issue occurred." 

    if ollama_client:
        try:
            logger.info(f"Processing with Ollama: {settings.GEMINI_MODEL_NAME}")
            tools_for_this_call: Optional[List[Dict[str, Any]]] = list(ollama_tool_definitions) if ollama_tool_definitions else None
            
            if tools_for_this_call: logger.info(f"Tools for Ollama: {json.dumps(tools_for_this_call, indent=2)}")
            else: logger.info("No tools for Ollama.")

            logger.debug(f"Messages to Ollama (1st): {json.dumps(current_turn_messages, indent=2)}")
            ollama_response_data: Dict[str, Any] = await asyncio.to_thread(
                ollama_client.chat, model=settings.GEMINI_MODEL_NAME, messages=current_turn_messages,
                tools=tools_for_this_call, options={"temperature": 0.0} 
            )
            logger.debug(f"Ollama response (1st) CONTENT: {ollama_response_data}")
            
            raw_assistant_message_dict: Dict[str, Any] = ollama_response_data.get('message', {})
            assistant_message_for_history: Dict[str, Any] = {
                'role': raw_assistant_message_dict.get('role', 'assistant'),
                'content': raw_assistant_message_dict.get('content', None) 
            }
            if raw_assistant_message_dict.get('tool_calls'):
                assistant_message_for_history['tool_calls'] = raw_assistant_message_dict.get('tool_calls')
            
            tool_call_candidates: List[Dict[str, Any]] = []
            tool_executed_this_turn = False

            if assistant_message_for_history.get('tool_calls'): 
                logger.info("Structured tool_calls detected.")
                tool_call_candidates = assistant_message_for_history['tool_calls']
                tool_executed_this_turn = True
            elif assistant_message_for_history.get('content'):
                content_text = assistant_message_for_history['content'].strip()
                if content_text.startswith('<toolcall>') and content_text.endswith('</toolcall>'):
                    content_text = content_text.removeprefix('<toolcall>').removesuffix('</toolcall>').strip()
                    logger.info("Stripped <toolcall> tags.")
                try:
                    parsed_content_from_string: Dict[str, Any] = json.loads(content_text) 
                    if isinstance(parsed_content_from_string, dict) and \
                         parsed_content_from_string.get('type') == 'function' and \
                         'arguments' in parsed_content_from_string and \
                         not parsed_content_from_string.get('function') and \
                         tools_for_this_call and len(tools_for_this_call) == 1: 
                        assumed_tool_name = tools_for_this_call[0]['function']['name'] 
                        logger.info(f"Args-only tool call. Assuming: '{assumed_tool_name}'. Args: {parsed_content_from_string['arguments']}")
                        tool_call_candidates = [{"id": f"content_assumed_tool_{assumed_tool_name}", "type": "function", 
                                                 "function": {"name": assumed_tool_name, "arguments": parsed_content_from_string['arguments']}}]
                        tool_executed_this_turn = True
                    else: 
                        final_agent_response_text = content_text 
                        logger.info(f"Agent direct text (JSON, not tool): '{final_agent_response_text}'")
                except json.JSONDecodeError: 
                    final_agent_response_text = content_text
                    logger.info(f"Agent direct text (plain): '{final_agent_response_text}'")
            else: 
                if assistant_message_for_history.get('role') == 'assistant': logger.warning("Ollama assistant message empty."); final_agent_response_text = "AI empty response."
                else: logger.warning("Ollama response unexpected."); final_agent_response_text = "AI unexpected response."

            if tool_executed_this_turn and tool_call_candidates:
                logger.info(f"Executing {len(tool_call_candidates)} tool candidate(s).")
                formatted_markdown_for_final_response = "Error processing tool results." # Default

                for tool_call in tool_call_candidates: # Expecting one tool call
                    if not isinstance(tool_call, dict) or 'function' not in tool_call: logger.warning(f"Malformed tool_call: {tool_call}"); continue
                    tool_function_data: Dict[str, Any] = tool_call['function'] 
                    tool_name: Optional[str] = tool_function_data.get('name')
                    tool_args_raw: Any = tool_function_data.get('arguments', {}) 
                    tool_id: str = tool_call.get("id", f"tool_{tool_name}" if tool_name else "unknown_tool_id") 
                    
                    if not tool_name: 
                        logger.warning(f"Tool call no name: {tool_call}")
                        formatted_markdown_for_final_response = "Error: Tool call was malformed (missing name)."
                        break # Exit loop as we can't proceed

                    tool_args: Dict[str, Any] = {}; 
                    if isinstance(tool_args_raw, str): 
                        try: tool_args = json.loads(tool_args_raw)
                        except json.JSONDecodeError: 
                            logger.error(f"Tool args parse error for {tool_name}: {tool_args_raw}", exc_info=True)
                            formatted_markdown_for_final_response = f"Error: Invalid arguments for tool {tool_name}."
                            break
                    elif isinstance(tool_args_raw, dict): tool_args = tool_args_raw
                    else: 
                        logger.warning(f"Tool args for {tool_name} not str/dict: {type(tool_args_raw)}. Using empty.")
                        # Potentially treat as error or proceed with empty args depending on tool design
                        # For now, let's assume this might be an error state for presentation
                        formatted_markdown_for_final_response = f"Error: Tool arguments for {tool_name} had an unexpected type."
                        break

                    if tool_name in available_tools:
                        logger.info(f"Executing: '{tool_name}', ID: '{tool_id}', Args: {tool_args}")
                        tool_function_to_call = available_tools[tool_name]
                        try:
                            tool_result_json_string: str = await asyncio.to_thread(tool_function_to_call, **tool_args)
                            
                            # --- PYTHON-SIDE FORMATTING OF TOOL OUTPUT ---
                            try:
                                tool_data = json.loads(tool_result_json_string)
                                if isinstance(tool_data, dict) and tool_data.get("message"): 
                                    formatted_markdown_for_final_response = tool_data["message"]
                                elif isinstance(tool_data, dict) and tool_data.get("error"):
                                     formatted_markdown_for_final_response = f"Error from tool: {tool_data['error']}"
                                elif isinstance(tool_data, list) and tool_data: 
                                    md_items = []
                                    for doc in tool_data: # Iterate through all documents
                                        md_items.append(
                                            f"- **Title:** {doc.get('title', 'N/A')}\n"
                                            f"- **Document Number:** {doc.get('document_number', 'N/A')}\n"
                                            f"- **Publication Date:** {doc.get('publication_date', 'N/A')}\n"
                                            f"- **Link:** [Read Document]({doc.get('html_url', '#')})"
                                        )
                                    formatted_markdown_for_final_response = "\n---\n".join(md_items) 
                                elif isinstance(tool_data, list) and not tool_data: 
                                     formatted_markdown_for_final_response = "No executive orders found for the given criteria."
                                else: 
                                    logger.warning(f"Tool returned unexpected data: {tool_result_json_string[:200]}")
                                    formatted_markdown_for_final_response = "Received an unusual response from search."
                            except json.JSONDecodeError:
                                logger.error(f"Tool returned non-JSON: {tool_result_json_string[:200]}")
                                formatted_markdown_for_final_response = "Error: Tool data invalid."
                            
                            logger.info(f"Tool '{tool_name}' pre-formatted output ready (len: {len(formatted_markdown_for_final_response)}).")
                        except Exception as e:
                            logger.error(f"Error executing/formatting tool '{tool_name}': {e}", exc_info=True)
                            formatted_markdown_for_final_response = f"System error during {tool_name} execution."
                    else: 
                        logger.warning(f"Tool '{tool_name}' not found.")
                        formatted_markdown_for_final_response = f"Error: Tool '{tool_name}' not available."
                    break # Assuming only one tool call per turn for now
                
                # --- Use Python-formatted output directly ---
                if "No executive orders found" in formatted_markdown_for_final_response or \
                   "Error from tool" in formatted_markdown_for_final_response or \
                   "Error: Tool data invalid" in formatted_markdown_for_final_response or \
                   "System error during" in formatted_markdown_for_final_response or \
                   "Error: Tool call was malformed" in formatted_markdown_for_final_response or \
                   "Error: Invalid arguments for tool" in formatted_markdown_for_final_response or \
                   "Error: Tool arguments for" in formatted_markdown_for_final_response or \
                   "Error: Tool '" in formatted_markdown_for_final_response: # Check for our error messages
                    final_agent_response_text = formatted_markdown_for_final_response
                else:
                    final_agent_response_text = "Okay, I found the following executive orders based on your request:\n\n" + formatted_markdown_for_final_response
                
                logger.info(f"Final agent response constructed in Python: '{final_agent_response_text[:300]}...'")

            # If no tool was executed, final_agent_response_text was set by earlier logic (direct LLM reply)
            
        except Exception as e:
            logger.error(f"Ollama processing error: {e}", exc_info=True)
            final_agent_response_text = f"Unexpected error: {e}"
    else:
        logger.warning("Ollama client not initialized.")
        final_agent_response_text = "AI assistant not configured."

    chat_history.append({"role": "user", "content": user_message})
    chat_history.append({"role": "assistant", "content": final_agent_response_text})
    if len(chat_history) > 20: chat_history = chat_history[-20:]

    return JSONResponse(content={"response": final_agent_response_text})