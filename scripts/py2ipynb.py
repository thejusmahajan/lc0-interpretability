"""
Script to convert percent-format Python script (e.g. colab/diagnose_on_gpu.py)
into a Jupyter notebook (colab/diagnose_on_gpu.ipynb).
"""
import sys
import json
from pathlib import Path


def convert_py_to_ipynb(py_path: Path, ipynb_path: Path):
    content = py_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    cells = []
    current_type = None
    current_lines = []

    def flush_cell():
        nonlocal current_type, current_lines
        if current_type is not None:
            # strip trailing empty lines
            while current_lines and not current_lines[-1].strip():
                current_lines.pop()
            if current_lines:
                # Format lines with trailing \n except for last line
                formatted_source = [
                    line + "\n" for line in current_lines[:-1]
                ] + [current_lines[-1]]
                if current_type == "markdown":
                    cells.append({
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": formatted_source
                    })
                elif current_type == "code":
                    cells.append({
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": formatted_source
                    })
        current_lines = []
        current_type = None

    for line in lines:
        if line.startswith("# %% [markdown]"):
            flush_cell()
            current_type = "markdown"
        elif line.startswith("# %%"):
            flush_cell()
            current_type = "code"
        else:
            if current_type == "markdown":
                # Strip leading '# ' or '#' if present for markdown text
                if line.startswith("# "):
                    current_lines.append(line[2:])
                elif line.startswith("#"):
                    current_lines.append(line[1:])
                else:
                    current_lines.append(line)
            elif current_type == "code":
                current_lines.append(line)
            else:
                # Top level outside cells -> treat as markdown
                current_type = "markdown"
                if line.startswith("# "):
                    current_lines.append(line[2:])
                elif line.startswith("#"):
                    current_lines.append(line[1:])
                else:
                    current_lines.append(line)

    flush_cell()

    notebook_data = {
        "cells": cells,
        "metadata": {
            "language_info": {
                "name": "python"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 2
    }

    ipynb_path.write_text(json.dumps(notebook_data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Successfully generated {ipynb_path} from {py_path} ({len(cells)} cells)")


if __name__ == "__main__":
    src = Path("colab/diagnose_on_gpu.py")
    dst = Path("colab/diagnose_on_gpu.ipynb")
    convert_py_to_ipynb(src, dst)
