from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Job


class JobSource(ABC):
    @abstractmethod
    def collect(self, limit: int = 50) -> list[Job]: ...
