"""pymmich - CLI for uploading/downloading folders and files to/from an Immich server."""

__version__ = "0.2.0"

from pymmich.client import ImmichClient, ImmichError

__all__ = ["ImmichClient", "ImmichError", "__version__"]
