# Lets `pytest` import config.py and the rag package from the project root.
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
