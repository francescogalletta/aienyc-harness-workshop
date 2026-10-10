"""The core (layer 0): session, lanes, waiting slot and the plan state document."""
from .session import (NO_ROUTE, BadAction, Closed, NotNow, Session, View, Work, add_message, add_thread,
                      get_message, list_messages, list_threads, number_of, set_thread_status, update_message)

Core = Session      # the name ARCHITECTURE.md 4.3 gives the object layers are handed

__all__ = ["NO_ROUTE", "BadAction", "Closed", "Core", "NotNow", "Session", "View", "Work", "add_message",
           "add_thread", "get_message", "list_messages", "list_threads", "number_of", "set_thread_status",
           "update_message"]
