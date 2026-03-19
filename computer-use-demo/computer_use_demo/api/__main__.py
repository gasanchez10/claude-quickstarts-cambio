"""Run the FastAPI backend: python -m computer_use_demo.api"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "computer_use_demo.api.main:app",
        host="0.0.0.0",
        port=int(__import__("os").environ.get("PORT", "8000")),
        reload=__import__("os").environ.get("RELOAD", "").lower() == "1",
    )
