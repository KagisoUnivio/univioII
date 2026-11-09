import subprocess
import sys
from pathlib import Path


def test_main_prints_greeting():
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "main.py"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == "Hello world, I am Kagiso. \n"
