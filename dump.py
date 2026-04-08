import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

def dump_all_files():
    output_path = ROOT / "full_codebase_dump.txt"
    ignore_dirs = {".git", ".pytest_cache", "__pycache__", "venv", "temp", "logs", "backups", "storage"}
    ignore_extensions = {".pyc", ".pyo", ".sqlite3", ".db", ".log", ".mp4"}
    
    with open(output_path, "w", encoding="utf-8") as f_out:
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for file in files:
                if Path(file).suffix in ignore_extensions:
                    continue
                if file == "full_codebase_dump.txt" or file == "codebase_dump.txt":
                    continue
                    
                file_path = Path(root) / file
                rel_path = file_path.relative_to(ROOT)
                
                try:
                    with open(file_path, "r", encoding="utf-8") as f_in:
                        content = f_in.read()
                        f_out.write(f"\n{'=' * 80}\n")
                        f_out.write(f"FILE: {rel_path}\n")
                        f_out.write(f"{'=' * 80}\n")
                        f_out.write(content)
                        f_out.write("\n")
                except UnicodeDecodeError:
                    # Skip binary files that slip through
                    pass

    print(f"Дамп кода успешно создан: {output_path}")

if __name__ == "__main__":
    dump_all_files()
