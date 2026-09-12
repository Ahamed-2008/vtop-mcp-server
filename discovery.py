"""Root CLI entry point for VTOP endpoint discovery."""
import sys
from pathlib import Path

# Ensure vtop-endpoint-discovery src is in sys.path
discovery_src = Path(__file__).parent / "vtop-endpoint-discovery" / "src"
if discovery_src.exists() and str(discovery_src) not in sys.path:
    sys.path.insert(0, str(discovery_src))

from vtop_discovery.main import main

if __name__ == "__main__":
    main()
