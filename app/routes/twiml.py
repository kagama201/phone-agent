"""
app/routes/twiml.py
"""
import os
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()


@router.post("/incoming-call")
async def incoming_call(request: Request):
    base_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")

    if base_url:
        ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/media-stream"
    else:
        host  = request.headers.get("host", "localhost")
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        scheme = "wss" if proto == "https" else "ws"
        ws_url = f"{scheme}://{host}/media-stream"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="From" value="{{{{From}}}}"/>
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")
