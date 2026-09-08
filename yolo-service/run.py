import os
import sys

# Ensure yolo-service root is on path when run as script
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("YOLO_SERVICE_PORT", "8090"))
    uvicorn.run("app.main:app", host=os.environ.get("YOLO_SERVICE_HOST", "127.0.0.1"), port=port, reload=False)
