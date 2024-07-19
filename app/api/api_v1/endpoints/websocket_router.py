from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, Depends
from sqlalchemy.orm import Session
from websockets.exceptions import ConnectionClosed
from app.core.dependencies import get_db, PermissionDependency, RequireLoginPermission
from app.services import WebsocketManagerService

router = APIRouter()

@router.websocket("/websocket")
async def accept_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db),
    perm: None = Depends(PermissionDependency(RequireLoginPermission))
):
    websocket_manager = WebsocketManagerService(db)
    await websocket_manager.connect(websocket)
    try:
        while True:
            await websocket_manager.process_message(websocket)
            
    except (WebSocketDisconnect, ConnectionClosed):
        await websocket_manager.disconnect(websocket)