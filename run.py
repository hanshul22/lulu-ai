import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import main

if __name__ == "__main__":
    main.run_app()