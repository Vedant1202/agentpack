import os
from pathlib import Path
from typing import List, Optional
import pathspec

SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf"}

DEFAULT_IGNORES = [
    ".git/",
    ".venv/",
    "venv/",
    "node_modules/",
    "__pycache__/",
    ".agentpack/",
]

def load_ignore_spec(directory: Path, no_gitignore: bool, no_default_patterns: bool) -> pathspec.PathSpec:
    lines = []
    if not no_default_patterns:
        lines.extend(DEFAULT_IGNORES)
    
    if not no_gitignore:
        gitignore_path = directory / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8") as f:
                lines.extend(f.readlines())
                
    agentpackignore_path = directory / ".agentpackignore"
    if agentpackignore_path.exists():
        with open(agentpackignore_path, "r", encoding="utf-8") as f:
            lines.extend(f.readlines())
            
    return pathspec.PathSpec.from_lines('gitignore', lines)

def scan_directory(
    directory: str, 
    include_hidden: bool = False,
    no_gitignore: bool = False,
    no_default_patterns: bool = False,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None
) -> List[Path]:
    """
    Recursively scans a directory and returns a list of supported files, respecting ignore rules.

    Args:
        directory (str): The root directory to scan.
        include_hidden (bool, optional): If True, includes hidden files and directories.
        no_gitignore (bool, optional): If True, skips loading rules from `.gitignore` and `.agentpackignore`.
        no_default_patterns (bool, optional): If True, skips the built-in ignore lists (`.git`, `node_modules`, etc.).
        include_patterns (List[str], optional): If provided, only files matching these gitignore-style patterns are returned.
        exclude_patterns (List[str], optional): If provided, files matching these gitignore-style patterns are skipped.

    Returns:
        List[Path]: A list of absolute or relative Path objects for files that should be packed.
    """
    paths = []
    dir_path = Path(directory)
    
    ignore_spec = load_ignore_spec(dir_path, no_gitignore, no_default_patterns)
    include_spec = pathspec.PathSpec.from_lines('gitignore', include_patterns) if include_patterns else None
    exclude_spec = pathspec.PathSpec.from_lines('gitignore', exclude_patterns) if exclude_patterns else None
    
    for root, dirs, files in os.walk(dir_path):
        rel_root = Path(root).relative_to(dir_path)
        
        valid_dirs = []
        for d in dirs:
            if not include_hidden and d.startswith("."):
                continue
            
            # Use posix path with trailing slash for directory matching
            rel_d = (rel_root / d).as_posix() + "/"
            if rel_d == "./":
                 rel_d = d + "/"
            elif rel_d.startswith("./"):
                 rel_d = rel_d[2:]
                 
            if ignore_spec.match_file(rel_d):
                continue
            
            valid_dirs.append(d)
            
        dirs[:] = valid_dirs
        
        for file in files:
            if not include_hidden and file.startswith("."):
                continue
                
            p = Path(root) / file
            if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
                
            rel_file = p.relative_to(dir_path).as_posix()
            
            if ignore_spec.match_file(rel_file):
                continue
                
            if exclude_spec and exclude_spec.match_file(rel_file):
                continue
                
            if include_spec and not include_spec.match_file(rel_file):
                continue
                
            paths.append(p)
            
    return paths
