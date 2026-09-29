# Ensure project root is in PYTHONPATH for pytest imports
import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
