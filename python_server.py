#!/usr/bin/env python
"""
Python Server for Local Code Execution
Copy this file to your machine and run: python python_server.py
"""

import tempfile
import os
import shutil
import subprocess
import asyncio
import uvicorn
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Python Runner API")

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Add middleware to handle preflight requests with Private Network Access
from fastapi import Request, Response

@app.middleware("http")
async def add_private_network_access_headers(request: Request, call_next):
    response = await call_next(request)
    # Enable Private Network Access for Chrome/Edge
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

class RunRequest(BaseModel):
    code: str = Field(..., min_length=1)
    input: Optional[str] = Field("", description="Input data for the program")
    timeout: Optional[int] = Field(5, description="Seconds before killing the run (default 5)")

class RunResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: Optional[int]
    timed_out: bool = False
    error: Optional[str] = None

async def run_python(code: str, input_data: str = "", timeout: int = 5) -> RunResult:
    tmpdir = tempfile.mkdtemp(prefix="py-run-")
    script_name = "main.py"
    script_path = os.path.join(tmpdir, script_name)

    try:
        # Ghi code vào file
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Chạy bằng subprocess với input
        proc = await asyncio.create_subprocess_exec(
            "python", script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            # Gửi input data nếu có
            input_bytes = input_data.encode('utf-8') if input_data else b''
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=input_bytes), 
                timeout=timeout
            )
            return RunResult(
                stdout=stdout.decode(errors="ignore"),
                stderr=stderr.decode(errors="ignore"),
                exit_code=proc.returncode,
                timed_out=False
            )
        except asyncio.TimeoutError:
            proc.kill()
            return RunResult(
                stdout="",
                stderr="Process killed due to timeout",
                exit_code=None,
                timed_out=True
            )

    except Exception as e:
        return RunResult(stdout="", stderr="", exit_code=None, timed_out=False, error=str(e))
    finally:
        # Dọn dẹp thư mục tạm
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

@app.post("/run", response_model=RunResult)
async def run_code(req: RunRequest):
    if len(req.code) > 20000:
        raise HTTPException(status_code=400, detail="Code too large (max 20000 characters).")

    print(f"Received code: {req.code[:100]}...")
    print(f"Received input: {repr(req.input)}")
    print(f"Input length: {len(req.input or '')}")
    
    result = await run_python(req.code, req.input or "", req.timeout or 5)
    return result

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    print("Starting Python Code Execution Server...")
    print("Server will run at: http://127.0.0.1:8001")
    print("Make sure you have installed: pip install fastapi uvicorn")
    print("Ready to execute Python code locally!")
    uvicorn.run("__main__:app", host="127.0.0.1", port=8001, reload=False)
