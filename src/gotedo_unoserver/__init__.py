from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("gotedo-unoserver")
except PackageNotFoundError:
    __version__ = "1.0.0-dev"   # fallback for local development