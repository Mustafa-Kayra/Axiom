import sys
import os
# Use absolute path to project root (parent of web/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(PROJECT_ROOT, "src"))

import subprocess
import json
import asyncio
from typing import List, Optional, Dict, Any, Union
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path
from rich.console import Console

from axiomai.model.config import MODELS, merge_models_with_user_config, CUSTOM_MODELS_KEY
from axiomai.model.auth import get_user_config, set_user_config
from axiomai.controller import commands
from axiomai.controller.llm_invoker import invoke_llm
from axiomai.controller.llm_handler import process_llm_response

def get_custom_models():
    """Retrieve custom models from user config."""
    try:
        models_raw = get_user_config(CUSTOM_MODELS_KEY, "[]")
        return json.loads(models_raw)
    except:
        return []

app = FastAPI(title="AxiomAI API Wrapper")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper to register routes with and without /v1 prefix to handle double-prefixing tools
def register_route(path: str, methods: List[str] = ["POST"]):
    def decorator(func):
        # Register original path
        app.add_api_route(path, func, methods=methods)
        # Register path with /v1 prefix if it doesn't have it
        if not path.startswith("/v1"):
            app.add_api_route(f"/v1{path}", func, methods=methods)
        # Handle cases where tools add /v1 to a base URL that already has /v1
        if path.startswith("/v1"):
            app.add_api_route(f"/v1{path}", func, methods=methods)
        return func
    return decorator

# --- Models ---

class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]] = ""

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = 0.7
    session_id: Optional[str] = None

class MessageRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 1024
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    session_id: Optional[str] = None

# --- Global State ---
# Maps session_id to Axiom chat_id
SESSION_STORE: Dict[str, int] = {}
CHAT_ID_FILE = Path(PROJECT_ROOT) / ".aye" / "chat_id.tmp"

# --- Logic ---

def get_all_models():
    """Merge built-in and custom models."""
    return merge_models_with_user_config()

def ensure_model_registered(model_id: str):
    """
    Model Seçim ve Kayıt Algoritması (Strict Logic):
    1. Özel Map
    2. Varlık Kontrolü
    3. Dinamik Kayıt Döngüsü (Fallback)
    """
    models = get_all_models()
    
    # 1. Özel Map: x-ai/grok-4.3 -> index 3 (4. model)
    if model_id == "x-ai/grok-4.3" and len(models) >= 4:
        return models[3]["id"]

    # 2. Varlık Kontrolü
    for m in models:
        if m["id"] == model_id:
            return model_id

    # 3. Dinamik Kayıt Döngüsü (Fallback)
    custom_models = get_custom_models()
    
    index = 1
    while True:
        alias = f"kullanıcımodeli{index}"
        if not any(m.get("id") == alias or m.get("name") == alias for m in custom_models):
            break
        index += 1

    # Programmatically add the model to ~/.ayecfg instead of subprocess which requires interaction
    new_model = {
        "id": model_id,
        "name": alias,
        "max_prompt_kb": 200,
        "max_output_tokens": 24000,
        "context_target_kb": 180,
        "type": "chat",
    }
    
    custom_models.insert(0, new_model)
    set_user_config(CUSTOM_MODELS_KEY, json.dumps(custom_models, separators=(",", ":")))
    merge_models_with_user_config()
    
    return model_id

@register_route("/models", methods=["GET"])
async def list_models():
    models = get_all_models()
    return {
        "object": "list",
        "data": [
            {
                "id": m["id"],
                "object": "model",
                "created": 1677610602,
                "owned_by": "axiomai"
            } for m in models
        ]
    }

@register_route("/chat/completions")
async def chat_completions(request: Request):
    # Manually parse JSON to handle inconsistent formats
    try:
        data = await request.json()
        print("MESSAGES Endpoint called. Stream:", data.get("stream"))
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    model_id = data.get("model", "default")
    target_model = ensure_model_registered(model_id)
    
    messages = data.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
        
    # Extract text from the last message
    last_msg = messages[-1]
    content = last_msg.get("content", "")
    
    if isinstance(content, list):
        last_message = "\n".join([
            item["text"] for item in content 
            if isinstance(item, dict) and item.get("type") == "text"
        ])
    else:
        last_message = str(content)
    
    # Session Persistence Logic
    session_id = data.get("session_id") or f"universal_api_session"
    current_chat_id = SESSION_STORE.get(session_id, -1)
    
    try:
        conf = commands.initialize_project_context(Path(PROJECT_ROOT), None, None)
        conf.selected_model = target_model
        conf.verbose = False
        
        console = Console(quiet=True)
        
        llm_response = invoke_llm(
            prompt=last_message,
            conf=conf,
            console=console,
            plugin_manager=conf.plugin_manager,
            chat_id=current_chat_id if current_chat_id != -1 else None,
            verbose=False
        )
        
        content = llm_response.summary if llm_response and llm_response.summary else "No response."
        
        # Update session store with new chat_id from Axiom
        if llm_response and llm_response.chat_id:
            SESSION_STORE[session_id] = llm_response.chat_id

        if llm_response and llm_response.updated_files:
            process_llm_response(llm_response, conf, console, last_message, None)

        openai_payload = {
            "id": f"chatcmpl-{os.urandom(4).hex()}",
            "object": "chat.completion",
            "created": 1677652288,
            "model": model_id,
            "session_id": session_id,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
        return JSONResponse(
            content=openai_payload,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@register_route("/messages")
async def messages_endpoint(request: Request):
    """Anthropic-style /v1/messages endpoint support."""
    try:
        raw_body = await request.body()
        print("INCOMING PAYLOAD:\n", raw_body.decode('utf-8'))
        data = json.loads(raw_body)
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    model_id = data.get("model", "default")
    target_model = ensure_model_registered(model_id)
    
    # Extract full conversation history to give memory to Axiom
    messages = data.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    
    # Process history into a single string for Axiom's simple invoker
    # or we can try to pass it differently. For now, let's reconstruct the context.
    history_context = ""
    for msg in messages[:-1]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text = "\n".join([item["text"] for item in content if isinstance(item, dict) and item.get("type") == "text"])
        else:
            text = str(content)
        history_context += f"{role.capitalize()}: {text}\n"
    
    last_msg = messages[-1]
    last_content = last_msg.get("content", "")
    if isinstance(last_content, list):
        last_message = "\n".join([item["text"] for item in last_content if isinstance(item, dict) and item.get("type") == "text"])
    else:
        last_message = str(last_content)
    
    # Combined prompt with history (Axiom doesn't yet support native history list in invoke_llm easily via this route)
    full_prompt = last_message
    if history_context:
        full_prompt = f"Conversation History:\n{history_context}\n\nCurrent Question: {last_message}"
    
    # Session Persistence Logic
    session_id = data.get("session_id") or "universal_api_session"
    current_chat_id = SESSION_STORE.get(session_id, -1)
    
    try:
        conf = commands.initialize_project_context(Path(PROJECT_ROOT), None, None)
        conf.selected_model = target_model
        conf.verbose = False
        
        console = Console(quiet=True)
        
        llm_response = invoke_llm(
            prompt=full_prompt,
            conf=conf,
            console=console,
            plugin_manager=conf.plugin_manager,
            chat_id=current_chat_id if current_chat_id != -1 else None,
            verbose=False
        )
        
        content_out = llm_response.summary if llm_response and llm_response.summary else "No response."

        # Update session store with new chat_id from Axiom
        if llm_response and llm_response.chat_id:
            SESSION_STORE[session_id] = llm_response.chat_id

        if llm_response and llm_response.updated_files:
            process_llm_response(llm_response, conf, console, last_message, None)

        response_payload = {
            "id": f"msg_{os.urandom(4).hex()}",
            "type": "message",
            "role": "assistant",
            "model": model_id,
            "session_id": session_id,
            "content": [{"type": "text", "text": content_out}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 50}
        }
        
        # Build raw bytes properly encoded
       return JSONResponse(
            content=response_payload,
            headers={"Content-Type": "application/json; charset=utf-8"}
       )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
