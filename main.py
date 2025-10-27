import os
import sys
import logging
import traceback

# Add project root to path
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.orchestrator import ESIMDeactivationOrchestrator

# Configure main logger
logger = logging.getLogger(__name__)

def main():
    """
    Entry point for the eSIM deactivation process.
    """
    try:
        # Create and run orchestrator
        orchestrator = ESIMDeactivationOrchestrator()
        exit_code = orchestrator.run()

        # Exit with appropriate code
        sys.exit(exit_code)

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
