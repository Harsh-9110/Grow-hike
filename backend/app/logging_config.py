import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = record.msg if isinstance(record.msg, dict) else record.getMessage()
        return json.dumps({'level':record.levelname,'event':event,'time':self.formatTime(record)})


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # Provider query strings can contain API keys; never log external client requests.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
