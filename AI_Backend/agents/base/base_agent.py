# base_agent.py
import logging
from datetime import datetime

class BaseAgent:
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)

    def log(self, message: str):
        self.logger.info(f"[{self.name}] {message}")

    def preprocess(self, input_data: dict) -> dict:
        # Common preprocessing
        return input_data

    def postprocess(self, output: dict) -> dict:
        # Common formatting
        output["processed_at"] = str(datetime.utcnow())
        return output