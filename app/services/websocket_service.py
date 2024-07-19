from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from app.services import UserService
from app.models.user import UserModel, UserType
from app.schemas import WebsocketMessage, WebsocketErrorMessage

class WebsocketManagerService:
    clients = []

    def __init__(self, session: Session):
        self.session = session

    async def get_connected_users(self) -> list[UserModel]:
        return [
            await UserService(self.session).get_user_by_onyen(client.user.onyen)
            for client in self.clients
        ]

    async def get_user_from_connection(self, client: WebSocket) -> UserModel:
        return await UserService(self.session).get_user_by_onyen(client.user.onyen)

    async def get_connections_for_user(self, user: UserModel) -> list[WebSocket]:
        return [
            client for client in self.clients
            if client.user.onyen == user.onyen
        ]
    
    async def get_connections_for_user_type(self, user_type: UserType):
        return [
            client for client in self.clients
            if (await self.get_connection_user(client)).user_type == user_type
        ]
    
    async def get_student_connections(self):
        return await self.get_connections_for_user_type(UserType.STUDENT)
    
    async def get_instructor_connections(self):
        return await self.get_connections_for_user_type(UserType.STUDENT)

    async def connect(self, client: WebSocket):
        await client.accept()
        self.clients.append(client)

    async def disconnect(self, client: WebSocket):
        self.clients.remove(client)


    async def process_message(self, client: WebSocket):
        # If a client sends invalid JSON in the payload, it will close the connection.
        data = await client.receive_json()
        event_name = data["event_name"]

    """ Send a message to every active websocket connection, or a specific user type. """
    async def broadcast_message(self, message: WebsocketMessage, user_type: UserType | None = None):
        clients = await self.get_connections_for_user_type(user_type) if user_type is not None else self.clients
        for client in clients: await self.send_message_to_client(message, clients)

    """ Send a message to an individual websocket connection """
    async def send_message_to_client(self, websocket: WebSocket, message: WebsocketMessage):
        await websocket.send_json(self._serialize_websocket_message(message))

    """ Send a message to all active websocket connections for a user """
    async def send_message_to_user(self, user: UserModel, message: WebsocketMessage):
        clients = await self.get_connections_for_user(user)
        for client in clients: await self.send_message_to_client(client, message)

    @staticmethod
    def _serialize_websocket_message(message: WebsocketMessage) -> dict:
        return jsonable_encoder({
            **message.dict(),
            "event_name": message.__event_name__
        })