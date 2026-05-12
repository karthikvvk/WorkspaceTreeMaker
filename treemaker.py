#!/usr/bin/env python3
"""
TreeMaker - Python Project Function Call Tree Analyzer

Analyzes a Python project and generates a hierarchical tree of function calls.
Shows which functions call which, marks functions called from multiple places with [],
and lists unused functions.

Dependencies:
- A .gitignore file must exist in the project root
- Python 3.7+

Usage:
    python treemaker.py <project_path>
"""

import ast
import os
import sys
import fnmatch
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set, List, Tuple, Optional


class GitIgnoreParser:
    """Parses .gitignore and checks if paths should be ignored."""
    
    def __init__(self, gitignore_path: str):
        self.patterns: List[str] = []
        self.negations: List[str] = []
        self.base_path = os.path.dirname(gitignore_path)
        
        if not os.path.exists(gitignore_path):
            raise FileNotFoundError(f".gitignore file is required but not found at: {gitignore_path}")
        
        with open(gitignore_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                if line.startswith('!'):
                    self.negations.append(line[1:])
                else:
                    self.patterns.append(line)
        
        # Always ignore common non-essential directories
        self.patterns.extend([
            '.git',
            '__pycache__',
            '*.pyc',
            '.pytest_cache',
            '*.egg-info',
            '.eggs',
            'venv',
            '.venv',
            'env',
            '.env',
            'node_modules',
        ])
    
    def is_ignored(self, path: str) -> bool:
        """Check if a path should be ignored based on .gitignore patterns."""
        rel_path = os.path.relpath(path, self.base_path)
        path_parts = rel_path.split(os.sep)
        
        # Check each pattern
        for pattern in self.patterns:
            # Handle directory patterns (ending with /)
            if pattern.endswith('/'):
                dir_pattern = pattern[:-1]
                for part in path_parts:
                    if fnmatch.fnmatch(part, dir_pattern):
                        # Check if negated
                        if not self._is_negated(rel_path):
                            return True
            else:
                # Check against full path and each component
                if fnmatch.fnmatch(rel_path, pattern):
                    if not self._is_negated(rel_path):
                        return True
                if fnmatch.fnmatch(os.path.basename(path), pattern):
                    if not self._is_negated(rel_path):
                        return True
                # Check if any path component matches
                for part in path_parts:
                    if fnmatch.fnmatch(part, pattern):
                        if not self._is_negated(rel_path):
                            return True
        
        return False
    
    def _is_negated(self, path: str) -> bool:
        """Check if path is negated (un-ignored)."""
        for pattern in self.negations:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path), pattern):
                return True
        return False


class FunctionInfo:
    """Stores information about a function."""
    
    def __init__(self, name: str, file_path: str, line_number: int, 
                 class_name: Optional[str] = None):
        self.name = name
        self.file_path = file_path
        self.line_number = line_number
        self.class_name = class_name
        self.calls: Set[str] = set()  # Functions this function calls
        self.called_by: Set[str] = set()  # Functions that call this function
    
    @property
    def full_name(self) -> str:
        """Get fully qualified name including class if applicable."""
        if self.class_name:
            return f"{self.class_name}.{self.name}"
        return self.name
    
    @property
    def display_name(self) -> str:
        """Get display name with file reference."""
        rel_path = self.file_path
        return f"{self.full_name} ({rel_path}:{self.line_number})"
    
    def __repr__(self):
        return f"FunctionInfo({self.full_name})"


class CallVisitor(ast.NodeVisitor):
    """AST visitor to extract function calls from a function body."""
    
    def __init__(self):
        self.calls: Set[str] = set()
    
    def visit_Call(self, node: ast.Call):
        """Visit a function call node."""
        call_name = self._get_call_name(node.func)
        if call_name:
            self.calls.add(call_name)
        self.generic_visit(node)
    
    def _get_call_name(self, node) -> Optional[str]:
        """Extract the name of the called function."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # Handle method calls like obj.method()
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            parts.reverse()
            # Return just the method name or full chain based on context
            if len(parts) >= 2:
                # For self.method, return just method name
                if parts[0] == 'self':
                    return parts[1]
                # For cls.method, return just method name
                if parts[0] == 'cls':
                    return parts[1]
                # For other cases, return the full chain or just the last part
                return '.'.join(parts)
            return parts[0] if parts else None
        return None


class FunctionVisitor(ast.NodeVisitor):
    """AST visitor to extract function definitions and their calls."""
    
    def __init__(self, file_path: str, base_path: str):
        self.file_path = os.path.relpath(file_path, base_path)
        self.functions: Dict[str, FunctionInfo] = {}
        self.current_class: Optional[str] = None
    
    def visit_ClassDef(self, node: ast.ClassDef):
        """Visit a class definition."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Visit a function definition."""
        self._process_function(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Visit an async function definition."""
        self._process_function(node)
    
    def _process_function(self, node):
        """Process a function or async function definition."""
        func_info = FunctionInfo(
            name=node.name,
            file_path=self.file_path,
            line_number=node.lineno,
            class_name=self.current_class
        )
        
        # Extract calls from function body
        call_visitor = CallVisitor()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_visitor.visit_Call(child)
        
        func_info.calls = call_visitor.calls
        
        # Use full name as key
        self.functions[func_info.full_name] = func_info
        
        # Don't visit nested functions as separate top-level functions
        # They're already processed in the call extraction


class ProjectAnalyzer:
    """Analyzes a Python project and builds function call graphs."""
    
    def __init__(self, project_path: str, extensions: tuple):
        self.project_path = os.path.abspath(project_path)
        self.gitignore = GitIgnoreParser(os.path.join(self.project_path, '.gitignore'))
        self.functions: Dict[str, FunctionInfo] = {}
        self.files_analyzed: List[str] = []
        self.extensions = extensions
    
    def analyze(self):
        """Analyze all Python files in the project."""
        for root, dirs, files in os.walk(self.project_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not self.gitignore.is_ignored(os.path.join(root, d))]
            
            for file in files:
                if file.endswith("." + self.extensions):
                    file_path = os.path.join(root, file)
                    if not self.gitignore.is_ignored(file_path):
                        self._analyze_file(file_path)
        
        # Build the call relationships
        self._build_call_relationships()
    
    def _analyze_file(self, file_path: str):
        """Analyze a single Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            visitor = FunctionVisitor(file_path, self.project_path)
            visitor.visit(tree)
            
            # Merge functions
            for name, func in visitor.functions.items():
                # Handle duplicate names from different files
                unique_key = f"{func.file_path}::{name}"
                self.functions[unique_key] = func
            
            rel_path = os.path.relpath(file_path, self.project_path)
            self.files_analyzed.append(rel_path)
            
        except SyntaxError as e:
            print(f"Warning: Syntax error in {file_path}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Error analyzing {file_path}: {e}", file=sys.stderr)
    
    def _build_call_relationships(self):
        """Build the called_by relationships between functions."""
        # Create a mapping from simple names to function keys
        name_to_keys: Dict[str, List[str]] = defaultdict(list)
        for key, func in self.functions.items():
            name_to_keys[func.name].append(key)
            name_to_keys[func.full_name].append(key)
        
        # Build called_by relationships
        for caller_key, caller_func in self.functions.items():
            for call_name in caller_func.calls:
                # Try to find the called function
                # First try exact match
                if call_name in name_to_keys:
                    for callee_key in name_to_keys[call_name]:
                        if callee_key in self.functions:
                            self.functions[callee_key].called_by.add(caller_key)
                else:
                    # Try just the method name (last part after .)
                    simple_name = call_name.split('.')[-1]
                    if simple_name in name_to_keys:
                        for callee_key in name_to_keys[simple_name]:
                            if callee_key in self.functions:
                                self.functions[callee_key].called_by.add(caller_key)
    
    def get_entry_points(self) -> List[str]:
        """Get functions that are not called by any other function (entry points)."""
        entry_points = []
        for key, func in self.functions.items():
            if not func.called_by:
                entry_points.append(key)
        return sorted(entry_points)
    
    def get_unused_functions(self) -> List[FunctionInfo]:
        """
        Get functions that are truly unused (orphaned).
        
        A function is USED if:
        - It's called by another function in the project, OR
        - It calls other functions in the project (entry point of a call chain)
        
        A function is UNUSED only if:
        - Nobody calls it AND it doesn't call any project functions
        """
        # First, build a set of all functions that have valid calls to project functions
        name_to_keys: Dict[str, List[str]] = defaultdict(list)
        for key, func in self.functions.items():
            name_to_keys[func.name].append(key)
            name_to_keys[func.full_name].append(key)
        
        def has_valid_calls(func: FunctionInfo) -> bool:
            """Check if function calls any other function in the project."""
            for call_name in func.calls:
                # Check exact match
                if call_name in name_to_keys:
                    return True
                # Check simple name (last part after .)
                simple_name = call_name.split('.')[-1]
                if simple_name in name_to_keys:
                    return True
            return False
        
        unused = []
        for key, func in self.functions.items():
            # Skip dunder methods (__init__, __main__, etc.)
            if func.name.startswith('__') and func.name.endswith('__'):
                continue
            
            # A function is USED if:
            # 1. Someone calls it (func.called_by is not empty), OR
            # 2. It calls other project functions (it's an entry point of a call chain)
            is_called_by_others = bool(func.called_by)
            calls_project_functions = has_valid_calls(func)
            
            # Only mark as unused if BOTH conditions are false
            if not is_called_by_others and not calls_project_functions:
                unused.append(func)
        
        return sorted(unused, key=lambda f: (f.file_path, f.line_number))
    
    def get_multi_caller_functions(self) -> Set[str]:
        """Get functions that are called from multiple places."""
        multi_caller = set()
        for key, func in self.functions.items():
            if len(func.called_by) > 1:
                multi_caller.add(key)
        return multi_caller


class TreePrinter:
    """Prints the function call tree."""
    
    def __init__(self, analyzer: ProjectAnalyzer):
        self.analyzer = analyzer
        self.multi_caller = analyzer.get_multi_caller_functions()
        self.printed: Set[str] = set()  # Track printed functions to avoid infinite loops
    
    def print_tree(self):
        """Print the complete function call tree."""
        print("=" * 80)
        print("PYTHON PROJECT FUNCTION CALL TREE")
        print("=" * 80)
        print(f"\nProject: {self.analyzer.project_path}")
        print(f"Files analyzed: {len(self.analyzer.files_analyzed)}")
        print(f"Functions found: {len(self.analyzer.functions)}")
        print("\n" + "-" * 80)
        print("FILES ANALYZED:")
        print("-" * 80)
        for f in sorted(self.analyzer.files_analyzed):
            print(f"  • {f}")
        
        print("\n" + "-" * 80)
        print("LEGEND:")
        print("-" * 80)
        print("  [*] = This function is also called from other places")
        print("  └── = Calls to other functions")
        
        print("\n" + "=" * 80)
        print("FUNCTION CALL TREE (Entry Points)")
        print("=" * 80)
        
        entry_points = self.analyzer.get_entry_points()
        
        if not entry_points:
            print("\nNo entry points found.")
        else:
            for ep in entry_points:
                self.printed.clear()  # Reset for each entry point tree
                self._print_function_tree(ep, 0)
                print()
        
        # Print unused functions
        self._print_unused_functions()
    
    def _print_function_tree(self, func_key: str, depth: int, 
                             prefix: str = "", is_last: bool = True):
        """Recursively print a function and its calls."""
        if func_key not in self.analyzer.functions:
            return
        
        func = self.analyzer.functions[func_key]
        
        # Build the display string
        if depth == 0:
            connector = ""
        else:
            connector = "└── " if is_last else "├── "
        
        # Mark if this function is called from multiple places
        multi_marker = " [*]" if func_key in self.multi_caller else ""
        
        display = f"{prefix}{connector}{func.full_name}{multi_marker}"
        location = f"({func.file_path}:{func.line_number})"
        print(f"{display} {location}")
        
        # Check if we've already printed this function's subtree
        if func_key in self.printed:
            if func.calls:
                child_prefix = prefix + ("    " if is_last else "│   ")
                print(f"{child_prefix}└── ... (already shown above)")
            return
        
        self.printed.add(func_key)
        
        # Get the calls that exist in our function map
        valid_calls = []
        name_to_keys: Dict[str, List[str]] = defaultdict(list)
        for key, f in self.analyzer.functions.items():
            name_to_keys[f.name].append(key)
            name_to_keys[f.full_name].append(key)
        
        for call_name in sorted(func.calls):
            if call_name in name_to_keys:
                for callee_key in name_to_keys[call_name]:
                    if callee_key not in valid_calls:
                        valid_calls.append(callee_key)
            else:
                simple_name = call_name.split('.')[-1]
                if simple_name in name_to_keys:
                    for callee_key in name_to_keys[simple_name]:
                        if callee_key not in valid_calls:
                            valid_calls.append(callee_key)
        
        # Print child calls
        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, callee_key in enumerate(valid_calls):
            is_last_child = (i == len(valid_calls) - 1)
            self._print_function_tree(callee_key, depth + 1, child_prefix, is_last_child)
    
    def _print_unused_functions(self):
        """Print the list of unused functions."""
        print("\n" + "=" * 80)
        print("UNUSED FUNCTIONS")
        print("=" * 80)
        print("(Functions that are not part of any call chain - neither call nor are called by project functions)")
        print("-" * 80)
        
        unused = self.analyzer.get_unused_functions()
        
        if not unused:
            print("\nNo unused functions found.")
        else:
            # Group by file
            by_file: Dict[str, List[FunctionInfo]] = defaultdict(list)
            for func in unused:
                by_file[func.file_path].append(func)
            
            for file_path in sorted(by_file.keys()):
                print(f"\n📁 {file_path}")
                for func in by_file[file_path]:
                    print(f"   ⚠️  {func.full_name} (line {func.line_number})")
        
        print("\n" + "=" * 80)


def main():
    """Main entry point."""
    # if len(sys.argv) != 2:
    #     print("Usage: python treemaker.py <project_path>")
    #     print("\nAnalyzes a Python project and generates a function call tree.")
    #     print("\nRequirements:")
    #     print("  - A .gitignore file must exist in the project root")
    #     sys.exit(1)
    
    project_path = "."
    
    if not os.path.isdir(project_path):
        print(f"Error: '{project_path}' is not a valid directory.")
        sys.exit(1)
    
    gitignore_path = os.path.join(project_path, '.gitignore')
    print(gitignore_path, project_path)
    if not os.path.exists(gitignore_path):
        print(f"Error: .gitignore file is required but not found at: {gitignore_path}")
        print("\nPlease create a .gitignore file in the project root.")
        sys.exit(1)
    extensions = ["py", ]#"cpp", "java", "dart", "jsx", "js", "html"] #anything
    extensions = tuple(extensions)
    try:
        analyzer = ProjectAnalyzer(project_path, extensions)
        analyzer.analyze()
        
        printer = TreePrinter(analyzer)
        printer.print_tree()
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
