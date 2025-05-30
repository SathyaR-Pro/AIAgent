from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Any

class ChatRequest(BaseModel):
    message: str = Field(..., example="What are the executive orders published today?")

class ToolCall(BaseModel):
    function_name: str = Field(..., example="search_federal_executive_orders")
    arguments: Dict[str, Any] = Field(..., example={"query_keywords": "cybersecurity"})

class ChatResponse(BaseModel):
    response: str = Field(..., example="Here are the executive orders...")
    tool_calls: Optional[List[ToolCall]] = Field(None, example=[])
    error: Optional[str] = Field(None, example="An error occurred during API call.")

