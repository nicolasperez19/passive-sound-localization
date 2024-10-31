from dataclasses import dataclass, field
from typing import List

@dataclass(frozen=True)
class RealtimeAudioStreamerConfig:
    sample_rate: int = 24000,
    channels: int = 1,
    chunk: int = 1024
    device_indices: List[int] = field(default_factory=lambda: [2, 3, 4, 5]) # Lab configuration