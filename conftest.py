import os
import sys

# Ensure project root is first in sys.path so local types.py shadows the stdlib types module.
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
