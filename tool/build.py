"""Real syntax/build gate for this Python WSGI + static JS project; no network."""
import ast
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
python_files = sorted(list(root.glob('*.py')) + list((root / 'tool').glob('*.py'))
                      + list((root / 'tests').glob('*.py')))
for path in python_files:
    ast.parse(path.read_bytes(), filename=str(path))
javascript_files = sorted((root / 'static').rglob('*.js')) + sorted((root / 'tool').glob('*.js'))
for path in javascript_files:
    subprocess.run(['node', '--check', str(path)], check=True)
print(f'BUILD PASS: {len(python_files)} Python files parsed; {len(javascript_files)} JavaScript files checked.')
