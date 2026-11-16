"""Entry point for ``python -m meow_push``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
