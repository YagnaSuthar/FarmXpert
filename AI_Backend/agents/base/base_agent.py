# base_agent.py
import logging
from datetime import datetime

class BaseAgent:
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        if self.logger.level == logging.NOTSET:
            self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
    async def __call__(self, state):

        return await self.run(state)
    def log(self, message: str):
        self.logger.info(f"[{self.name}] {message}")

    def preprocess(self, input_data: dict) -> dict:
        # Common preprocessing
        return input_data

    def postprocess(self, output: dict) -> dict:
        # Common formatting
        output["processed_at"] = str(datetime.utcnow())
        return output