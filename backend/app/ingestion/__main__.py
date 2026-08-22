"""app.ingestion.__main__ — entry-point de `python -m app.ingestion` (`make ingest`).

Delega enteramente en `app.ingestion.cli.main()`; sin lógica propia.
"""

import sys

from app.ingestion.cli import main

if __name__ == "__main__":
    sys.exit(main())
