import os
import tempfile
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from markitdown import MarkItDown
from pydantic import BaseModel

_bearer_scheme = HTTPBearer()


def _get_api_token() -> str | None:
    """Return the configured API token, or None if auth is disabled."""
    token = os.getenv("MARKITDOWN_API_TOKEN", "").strip()
    return token if token else None


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
):
    """Dependency that enforces Bearer token auth when MARKITDOWN_API_TOKEN is set."""
    expected = _get_api_token()
    if expected is None:
        return
    if credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def _plugins_enabled() -> bool:
    return os.getenv("MARKITDOWN_ENABLE_PLUGINS", "true").strip().lower() in (
        "true",
        "1",
        "yes",
    )


def _get_converter() -> MarkItDown:
    kwargs: dict = {"enable_plugins": _plugins_enabled()}
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if api_key:
        from openai import OpenAI

        kwargs["llm_client"] = OpenAI(
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        )
        kwargs["llm_model"] = os.getenv("LLM_MODEL", "gpt-4o-mini")
    return MarkItDown(**kwargs)


class ConvertRequest(BaseModel):
    uri: str


class ConvertResponse(BaseModel):
    markdown: str
    title: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    _get_converter()
    yield


app = FastAPI(
    title="MarkItDown REST API",
    description="Convert files and URIs to Markdown using Microsoft's MarkItDown library.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    token_required = _get_api_token() is not None
    return {
        "service": "markitdown-rest-api",
        "version": "1.0.0",
        "auth": "Bearer token required" if token_required else "disabled",
        "endpoints": {
            "POST /convert": "Convert a URI to Markdown",
            "POST /convert/file": "Upload a file and convert to Markdown",
            "GET /health": "Health check",
            "GET /docs": "Interactive API documentation (Swagger UI)",
        },
    }


@app.get("/health")
async def health():
    llm_configured = bool(os.getenv("LLM_API_KEY", "").strip())
    return {
        "status": "ok",
        "ocr_enabled": llm_configured,
        "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini") if llm_configured else None,
    }


@app.post("/convert", response_model=ConvertResponse, dependencies=[Depends(verify_token)])
async def convert_uri(request: ConvertRequest):
    """Convert a resource at an http:, https:, file:, or data: URI to Markdown."""
    try:
        result = _get_converter().convert_uri(request.uri)
        return ConvertResponse(markdown=result.markdown, title=result.title)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/convert/file", response_model=ConvertResponse, dependencies=[Depends(verify_token)])
async def convert_file(file: UploadFile = File(...)):
    """Upload a file and convert its contents to Markdown."""
    suffix = ""
    if file.filename:
        suffix = os.path.splitext(file.filename)[1]

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        result = _get_converter().convert(tmp_path)
        return ConvertResponse(markdown=result.markdown, title=result.title)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if "tmp_path" in locals():
            os.unlink(tmp_path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
