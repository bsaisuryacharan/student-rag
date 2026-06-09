# app/logging_config.py
import logging
import sys
from contextvars import ContextVar

# Below line creates a context variable called request_id_ctx that will hold the request ID for each request. The default value is set to "-", which will be used when there is no request ID available (e.g., outside of a request context). This allows us to have a consistent way to include the request ID in our log messages, even when we are not within the context of an actual request.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# Below is a custom logging filter that injects the request_id from the context variable into the log record. This allows us to include the request_id in all log messages without having to pass it explicitly each time we log something.  
class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True
    
# The configure_logging function sets up the logging configuration for the application. It creates a StreamHandler that outputs logs to stdout, sets a custom log format that includes the request_id, and adds the RequestIdFilter to ensure that the request_id is included in all log records. 
# Finally, it clears any existing handlers and adds the new handler to the root logger, and sets the logging level to the specified level (default is "INFO"). 
def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | req=%(request_id)s | %(message)s"
    ))
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)