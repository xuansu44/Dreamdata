"""dreamdata — versioned management engine for LLM training data.

The public surface is the SDK in :mod:`dreamdata.sdk`. Internal layers
(:mod:`dreamdata.engine`, :mod:`dreamdata.meta`, :mod:`dreamdata.storage`)
are private; user code must not import them directly.
"""

from dreamdata.errors import DreamDataError, SdkError
from dreamdata.sdk import Dataset, Engine

__all__ = ["Dataset", "DreamDataError", "Engine", "SdkError", "__version__"]

__version__ = "0.0.1"
