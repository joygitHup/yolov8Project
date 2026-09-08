"""Run: python -m app  (from yolo-service directory) or uvicorn app.main:app"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("YOLO_SERVICE_PORT", "8090"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
