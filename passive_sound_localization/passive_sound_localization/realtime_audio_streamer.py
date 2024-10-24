import logging
from typing import AsyncGenerator, Dict, List, Optional
from pyaudio import PyAudio, paInt16, Stream
from scipy.signal import resample
import numpy as np

logger = logging.getLogger(__name__)


class InvalidDeviceIndexError(Exception):
    pass


# TODO: Make it take in Hydra config
class RealtimeAudioStreamer:
    def __init__(self, sample_rate:int=24000, channels:int=1, chunk:int=1024):
        self.sample_rate:int = sample_rate
        self.channels: int = channels
        self.chunk: int = chunk
        self.device_indices: List[int] = []
        self.format = paInt16
        self.audio: Optional[PyAudio] = None
        self.streams: List[Optional[Stream]] = []
        self.streaming: bool = False
        self.original_sample_rates: Dict[int, int] = {}

    async def __aenter__(self):
        self.audio = PyAudio()

        try:
            device_info = self.audio.get_device_info_by_index(self.device_index)
            self.original_sample_rate = int(device_info["defaultSampleRate"])
        except IndexError:
            raise InvalidDeviceIndexError(f"RealtimeAudioStreamer was provided an invalid device index: {self.device_index}")

        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.original_sample_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=self.chunk,
        )
        self.streaming = True
        return self
    
    async def __aexit__(self, *args):
        self.streaming = False
        for stream in self.streams:
            if stream:
                stream.stop_stream()
                stream.close()
        self.streams = []

        if self.audio:
            self.audio.terminate()
            self.audio = None

    def _resample_audio(self, audio_data: bytes, original_sample_rate: int, target_sample_rate: int) -> bytes:
        if original_sample_rate == target_sample_rate:
            return audio_data

        number_of_samples = round(len(audio_data) * float(target_sample_rate) / original_sample_rate)
        resampled_audio = resample(audio_data, number_of_samples)
        return resampled_audio.astype(np.int16).tobytes()
    
    def _mix_audio_chunks(self, audio_arrays: List[np.ndarray]) -> np.ndarray:
        if not audio_arrays:
            return np.array([], dtype=np.int16)
        mixed_data = np.sum(audio_arrays, axis=0) / len(audio_arrays)
        mixed_data = np.clip(mixed_data, -32768, 32767).astype(np.int16)
        return mixed_data
    
    async def multi_channel_gen(self) -> AsyncGenerator[Dict[int, bytes], None]:
        try:
            while self.streaming:
                audio_data = {}
                for device_index, stream in zip(self.device_indices, self.streams):
                    try:
                        data = stream.read(self.chunk, exception_on_overflow=False)
                        resampled_data = self._resample_audio(
                            data, 
                            self.original_sample_rates[device_index], 
                            self.sample_rate
                        )
                        audio_data[device_index] = resampled_data
                    except Exception as e:
                        print(f"Error reading from device {device_index}: {e}")
                if audio_data:
                    yield audio_data
        except Exception as e:
            print(f"Error in audio_generator: {e}")

    async def single_channel_gen(self) -> AsyncGenerator[bytes, None]:
        try:
            while self.streaming:
                audio_arrays = []
                for device_index, stream in zip(self.device_indices, self.streams):
                    try:
                        data = stream.read(self.chunk, exception_on_overflow=False)
                        resampled_data = self._resample_audio(
                            data, 
                            self.original_sample_rates[device_index], 
                            self.sample_rate
                        )
                        audio_array = np.frombuffer(resampled_data, dtype=np.int16)
                        audio_arrays.append(audio_array)
                    except Exception as e:
                        print(f"Error reading from device {device_index}: {e}")
                if audio_arrays:
                    mixed_data = self._mix_audio_chunks(audio_arrays)
                    yield mixed_data.tobytes()
        except Exception as e:
            print(f"Error in mixed_audio_generator: {e}")