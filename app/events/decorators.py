from .emitter import event_emitter

# For use with static events.
def emits(*args, **kwargs):
    def inner(func):
        result = func()
        event_emitter.emit_future(*args, **kwargs)
        return result
    return inner