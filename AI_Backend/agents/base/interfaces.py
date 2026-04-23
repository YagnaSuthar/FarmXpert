# interfaces.py
from typing import Protocol

class AgentInterface(Protocol):
    def run(self, input_data: dict) -> dict:
        ...

    def validate(self, input_data: dict) -> bool:
        ...