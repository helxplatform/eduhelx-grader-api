import asyncio
from typing import Callable
from pydantic import BaseModel
from pymitter import EventEmitter

"""
NOTE: Any exceptions encountered within handlers will bubble up to the emitter.
In general, emits need to be caught by the caller for cleanup/etc. Any handlers
who are ok with failing should not raise exceptions to the emitter.
"""

class PydanticEvent(BaseModel):
    __event_name__: str
    
    class Config:
        arbitrary_types_allowed = True

class PydanticEventEmitter(EventEmitter):
    def _validate_pydantic_event(self, event: PydanticEvent) -> tuple[str, dict]:
        if not isinstance(event, PydanticEvent):
            raise TypeError(f"unrecognized event { event }, only Pydantic events are supported")
        
        # By converting the event to a dict, Pydantic performs validation on it.
        event.dict()

        name, payload = event.__event_name__, event
        return name, payload
    
    def on(self, event: str | BaseModel, *args, **kwargs) -> Callable:
        # Support passing in an event model as an event name.
        if isinstance(event, BaseModel):
            event = event.__event_name__
        
        return super().on(event, *args, **kwargs)

    def emit(self, *args, **kwargs):
        raise NotImplementedError("use `emit_future` instead if you need to dispatch from a sync block")

    """ This method is safe to use within sync and async blocks to trigger async handlers. However,
    you must keep in mind that since it's a future, the event is not necessary processed. """
    def emit_future(self, event: BaseModel) -> asyncio.Task:
        name, payload = self._validate_pydantic_event(event)
        awaitables = self._emit(name, payload)

        if awaitables:
            return asyncio.ensure_future(asyncio.gather(*awaitables))

    async def emit_async(self, event: BaseModel) -> None:
        name, payload = self._validate_pydantic_event(event)
        await super().emit_async(name, payload)

event_emitter = PydanticEventEmitter(wildcard=True, delimiter=":")