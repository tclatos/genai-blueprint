"""
Deep Coding Agent Example

This module demonstrates how to use the deepagents integration to create
a powerful coding agent that can write, debug, refactor, and test code.
"""

import ast
import asyncio
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from genai_tk.core.deep_agents import DeepAgentConfig, deep_agent_factory, run_deep_agent
from langchain.tools import tool
from loguru import logger


class CodingAgentExample:
    """Example implementation of a deep coding agent with specialized capabilities"""

    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize the coding agent example.

        Args:
            project_path: Optional path to the project directory
        """
        self.project_path = Path(project_path) if project_path else Path.cwd()
        self.agent = None

    def _create_code_analysis_tools(self):
        """Create tools for code analysis"""

        @tool
        def analyze_python_syntax(code: str) -> Dict[str, Any]:
            """
            Analyze Python code syntax and return any errors.

            Args:
                code: Python code to analyze

            Returns:
                Analysis results including syntax errors if any
            """
            try:
                ast.parse(code)
                return {"valid": True, "message": "Syntax is valid", "errors": []}
            except SyntaxError as e:
                return {
                    "valid": False,
                    "message": "Syntax error found",
                    "errors": [{"line": e.lineno, "offset": e.offset, "message": str(e.msg), "text": e.text}],
                }

        @tool
        def count_code_metrics(code: str) -> Dict[str, int]:
            """
            Count basic code metrics.

            Args:
                code: Source code to analyze

            Returns:
                Dictionary with code metrics
            """
            lines = code.split("\n")
            return {
                "total_lines": len(lines),
                "code_lines": len([l for l in lines if l.strip() and not l.strip().startswith("#")]),
                "comment_lines": len([l for l in lines if l.strip().startswith("#")]),
                "blank_lines": len([l for l in lines if not l.strip()]),
                "functions": code.count("def "),
                "classes": code.count("class "),
            }

        @tool
        def extract_functions(code: str) -> List[Dict[str, str]]:
            """
            Extract function definitions from Python code.

            Args:
                code: Python source code

            Returns:
                List of function definitions
            """
            try:
                tree = ast.parse(code)
                functions = []

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        functions.append(
                            {
                                "name": node.name,
                                "args": [arg.arg for arg in node.args.args],
                                "docstring": ast.get_docstring(node) or "No docstring",
                                "line_number": node.lineno,
                            }
                        )

                return functions
            except Exception as e:
                return [{"error": str(e)}]

        return [analyze_python_syntax, count_code_metrics, extract_functions]

    def _create_testing_tools(self):
        """Create tools for testing code"""

        @tool
        def run_python_code(code: str, timeout: int = 5) -> Dict[str, Any]:
            """
            Run Python code and capture output.

            Args:
                code: Python code to execute
                timeout: Execution timeout in seconds

            Returns:
                Execution results
            """
            try:
                result = subprocess.run(["python", "-c", code], capture_output=True, text=True, timeout=timeout)
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.returncode,
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "error": "Execution timed out"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @tool
        def generate_test_cases(function_name: str, function_code: str) -> str:
            """
            Generate basic test cases for a function.

            Args:
                function_name: Name of the function
                function_code: The function implementation

            Returns:
                Generated test cases template
            """
            test_template = f"""import unittest

class Test{function_name.capitalize()}(unittest.TestCase):
    
    def test_{function_name}_basic(self):
        # TODO: Add basic test case
        pass
    
    def test_{function_name}_edge_cases(self):
        # TODO: Add edge case tests
        pass
    
    def test_{function_name}_invalid_input(self):
        # TODO: Add invalid input tests
        pass

if __name__ == '__main__':
    unittest.main()
"""
            return test_template

        return [run_python_code, generate_test_cases]

    def _create_refactoring_tools(self):
        """Create tools for code refactoring"""

        @tool
        def suggest_variable_names(code: str) -> List[Dict[str, str]]:
            """
            Suggest better variable names based on common conventions.

            Args:
                code: Source code to analyze

            Returns:
                List of naming suggestions
            """
            suggestions = []

            # Simple heuristics for demo
            bad_names = ["x", "y", "z", "a", "b", "c", "temp", "var", "val"]

            for name in bad_names:
                if f" {name} " in code or f"{name}=" in code:
                    suggestions.append(
                        {"current": name, "suggestion": f"Consider using a more descriptive name instead of '{name}'"}
                    )

            return suggestions or [{"message": "No obvious naming issues found"}]

        @tool
        def add_type_hints(function_signature: str) -> str:
            """
            Add type hints to a function signature.

            Args:
                function_signature: Function signature without type hints

            Returns:
                Function signature with suggested type hints
            """
            # Simple template for demo
            if "->" not in function_signature:
                function_signature = function_signature.rstrip(":") + " -> None:"

            return f"# Consider adding type hints:\n{function_signature}"

        return [suggest_variable_names, add_type_hints]

    def create_agent(self, specialized_subagents: bool = True):
        """
        Create the coding agent with optional specialized subagents.

        Args:
            specialized_subagents: Whether to include specialized subagents

        Returns:
            The created agent
        """
        # Combine all tools
        tools = self._create_code_analysis_tools() + self._create_testing_tools() + self._create_refactoring_tools()

        # Create configuration
        config = DeepAgentConfig(
            name="Expert Coding Agent",
            instructions=f"""You are an expert software developer specializing in Python.

## Your Capabilities:

1. **Code Writing**: Write clean, efficient, well-documented code
2. **Debugging**: Identify and fix bugs in existing code
3. **Refactoring**: Improve code structure and readability
4. **Testing**: Write comprehensive test cases
5. **Documentation**: Create clear documentation and docstrings
6. **Code Review**: Provide constructive feedback on code

## Working Directory: {self.project_path}

## Best Practices to Follow:

- Write type hints for all functions
- Include comprehensive docstrings
- Follow PEP 8 style guidelines
- Write unit tests for critical functions
- Use meaningful variable and function names
- Keep functions small and focused
- Handle errors gracefully
- Add comments for complex logic

## Process:

1. Understand the requirements thoroughly
2. Plan the implementation using the planning tool
3. Write the code incrementally
4. Test each component
5. Refactor for clarity and efficiency
6. Document everything properly
7. Create a summary of changes

Always strive for code that is readable, maintainable, and efficient.""",
            enable_file_system=True,
            enable_planning=True,
        )

        # Add specialized subagents if requested
        if specialized_subagents:
            config.subagents = [
                {
                    "name": "test-writer",
                    "description": "Specialized in writing comprehensive test cases",
                    "prompt": """You are a test engineering specialist. Your job is to:
1. Write comprehensive unit tests
2. Create integration tests
3. Design test fixtures and mocks
4. Ensure high code coverage
5. Test edge cases and error conditions

Always use pytest or unittest frameworks and follow testing best practices.""",
                },
                {
                    "name": "code-reviewer",
                    "description": "Specialized in code review and quality assurance",
                    "prompt": """You are a senior code reviewer. Your job is to:
1. Review code for bugs and issues
2. Check adherence to best practices
3. Suggest performance improvements
4. Ensure code readability
5. Verify security considerations

Be constructive and provide specific, actionable feedback.""",
                },
                {
                    "name": "documentation-writer",
                    "description": "Specialized in writing documentation",
                    "prompt": """You are a technical documentation specialist. Your job is to:
1. Write clear API documentation
2. Create user guides and tutorials
3. Document code with comprehensive docstrings
4. Create README files
5. Write architectural documentation

Focus on clarity, completeness, and usefulness for different audiences.""",
                },
            ]

        # Create the agent
        self.agent = deep_agent_factory.create_agent(config=config, tools=tools, async_mode=True)

        logger.info("Coding agent created successfully")
        return self.agent

    async def write_function(
        self, description: str, requirements: Optional[List[str]] = None, examples: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Write a new function based on description.

        Args:
            description: Description of what the function should do
            requirements: Optional list of specific requirements
            examples: Optional input/output examples

        Returns:
            Generated function and related artifacts
        """
        if not self.agent:
            self.create_agent()

        query = f"Write a Python function that: {description}\n\n"

        if requirements:
            query += "Requirements:\n"
            for req in requirements:
                query += f"- {req}\n"
            query += "\n"

        if examples:
            query += "Examples:\n"
            for input_val, output_val in examples.items():
                query += f"- Input: {input_val} -> Output: {output_val}\n"
            query += "\n"

        query += "Please include:\n"
        query += "1. The function implementation\n"
        query += "2. Comprehensive docstring\n"
        query += "3. Type hints\n"
        query += "4. Unit tests\n"
        query += "5. Usage examples"

        messages = [{"role": "user", "content": query}]

        logger.info("Generating function: {}...", description[:50])
        result = await run_deep_agent(agent=self.agent, messages=messages, stream=False)

        return result

    async def debug_code(
        self, code: str, error_description: str, expected_behavior: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Debug problematic code.

        Args:
            code: The problematic code
            error_description: Description of the error or issue
            expected_behavior: Optional description of expected behavior

        Returns:
            Debugging results and fixed code
        """
        if not self.agent:
            self.create_agent()

        query = f"""Debug the following code that has issues:

```python
{code}
```

Error/Issue: {error_description}
"""

        if expected_behavior:
            query += f"\nExpected behavior: {expected_behavior}"

        query += "\n\nPlease:\n"
        query += "1. Identify the root cause of the issue\n"
        query += "2. Explain what's wrong\n"
        query += "3. Provide the fixed code\n"
        query += "4. Add tests to verify the fix\n"
        query += "5. Suggest improvements to prevent similar issues"

        messages = [{"role": "user", "content": query}]

        logger.info("Debugging code...")
        result = await run_deep_agent(agent=self.agent, messages=messages, stream=False)

        return result

    async def refactor_code(self, code: str, focus_areas: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Refactor code for better quality.

        Args:
            code: Code to refactor
            focus_areas: Optional specific areas to focus on

        Returns:
            Refactored code and explanation
        """
        if not self.agent:
            self.create_agent()

        query = f"""Refactor the following code for better quality:

```python
{code}
```
"""

        if focus_areas:
            query += "\nFocus on these areas:\n"
            for area in focus_areas:
                query += f"- {area}\n"
        else:
            query += "\nConsider:\n"
            query += "- Code readability\n"
            query += "- Performance optimization\n"
            query += "- Following best practices\n"
            query += "- Reducing complexity\n"
            query += "- Improving modularity\n"

        query += "\nProvide:\n"
        query += "1. The refactored code\n"
        query += "2. Explanation of changes made\n"
        query += "3. Benefits of the refactoring\n"
        query += "4. Any trade-offs considered"

        messages = [{"role": "user", "content": query}]

        logger.info("Refactoring code...")
        result = await run_deep_agent(agent=self.agent, messages=messages, stream=False)

        return result


async def main():
    """Main function demonstrating the coding agent"""

    # Create the coding agent
    coder = CodingAgentExample()

    # Example 1: Write a new function
    print("\n" + "=" * 50)
    print("Example 1: Writing a New Function")
    print("=" * 50)

    result = await coder.write_function(
        description="Calculate the Fibonacci sequence up to n terms",
        requirements=[
            "Handle both iterative and recursive approaches",
            "Include memoization for the recursive version",
            "Handle edge cases (n <= 0)",
            "Return a list of Fibonacci numbers",
        ],
        examples={"5": "[0, 1, 1, 2, 3]", "10": "[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]"},
    )

    if "messages" in result:
        print(result["messages"][-1].content)

    # Example 2: Debug code
    print("\n" + "=" * 50)
    print("Example 2: Debugging Code")
    print("=" * 50)

    buggy_code = """
def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)

# This fails with empty list
result = calculate_average([])
print(result)
"""

    result = await coder.debug_code(
        code=buggy_code,
        error_description="ZeroDivisionError when list is empty",
        expected_behavior="Should handle empty lists gracefully",
    )

    if "messages" in result:
        print(result["messages"][-1].content)

    # Example 3: Refactor code
    print("\n" + "=" * 50)
    print("Example 3: Refactoring Code")
    print("=" * 50)

    code_to_refactor = """
def process_data(data):
    result = []
    for i in range(len(data)):
        if data[i] > 0:
            temp = data[i] * 2
            if temp < 100:
                result.append(temp)
    return result
"""

    result = await coder.refactor_code(
        code=code_to_refactor,
        focus_areas=[
            "Use more Pythonic constructs",
            "Improve readability",
            "Add type hints",
            "Add proper documentation",
        ],
    )

    if "messages" in result:
        print(result["messages"][-1].content)

    # Show created files if any
    if "files" in result:
        print("\n" + "=" * 50)
        print("Files Created:")
        print("=" * 50)
        for filename, content in result["files"].items():
            print(f"\n📄 {filename}:")
            print(content[:500] + "..." if len(content) > 500 else content)


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())
