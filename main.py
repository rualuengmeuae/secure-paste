import os
import json
import time
import uuid
from typing import Union, List, Dict, Any
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="SecurePaste Hybrid")

# 配置
DATA_DIR = Path("data/pastes")
DATA_DIR.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---

class EncryptedPayload(BaseModel):
    ct: str
    iv: str
    ek: str


class PasteCreate(BaseModel):
    content: Union[str, EncryptedPayload, Dict[str, Any]]
    is_encrypted: bool
    remark: str = ""  # 新增：备注字段，默认为空


class PasteResponse(BaseModel):
    id: str
    timestamp: int
    is_encrypted: bool
    remark: str = ""  # 新增
    content: Union[str, EncryptedPayload, Dict[str, Any]]


# --- API Endpoints ---

@app.post("/api/paste")
async def create_paste(paste: PasteCreate):
    paste_id = uuid.uuid4().hex
    timestamp = int(time.time())

    filename = f"{timestamp}_{paste_id}.json"
    file_path = DATA_DIR / filename

    data = {
        "id": paste_id,
        "timestamp": timestamp,
        "is_encrypted": paste.is_encrypted,
        "remark": paste.remark[:50],  # 简单截断，防止备注过长
        "content": paste.content if isinstance(paste.content, dict) else paste.content
    }

    if hasattr(paste.content, "dict"):
        data["content"] = paste.content.dict()

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success", "id": paste_id}


@app.get("/api/pastes", response_model=List[PasteResponse])
async def list_pastes():
    pastes = []
    files = sorted(DATA_DIR.glob("*.json"), reverse=True)

    for f in files[:200]:
        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
                # 兼容旧数据（如果旧json没有remark字段）
                if "remark" not in data:
                    data["remark"] = ""
                pastes.append(data)
        except Exception:
            continue

    return pastes


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8070)