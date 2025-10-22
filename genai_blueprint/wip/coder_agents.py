"""OLD CODE !"""

from textwrap import dedent
from typing import Optional

from genai_tk.core.prompts import dedent_ws
from langchain.agents.agent_types import AgentType
from langchain.tools import BaseTool
from langchain_core.callbacks.manager import CallbackManagerForToolRun
from langchain_experimental.agents.agent_toolkits import (
    create_python_agent,
)
from langchain_experimental.tools.python.tool import PythonAstREPLTool

from genai_blueprint.GenAI_Lab import app_conf

PREFIX = """
    You are an agent designed to write and execute python code to generate a diagram using streamlit and matplotlib.
    You have access to a python REPL, which you can use to execute python code.
    If you get an error, debug your code and try again.
    The generated diagram is displayed in streamlit container named '{st_container_name}' and it should fit inside.
    So your code should end with '{st_container_name}.pyplot(fig, width="stretch")'.
    Don't import any package. Don't write 'main'.
    If it does not seem like you can write or execute code, just return "I can't create diagram', and provide explanation.
"""


class DiagramGeneratorTool(BaseTool):
    name: str = "diagram_generator"
    description: str = "display a diagram"

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        globals = None
        if st_container := run_manager.metadata.get("st_container"):
            name = st_container[0]
            obj = st_container[1]
            globals = {name: obj}
            if app_conf.use_functions:
                agent_type = AgentType.OPENAI_FUNCTIONS
            else:
                agent_type = AgentType.ZERO_SHOT_REACT_DESCRIPTION
            agent_executor = create_python_agent(
                llm=app_conf.chat_gpt,  # type: ignore
                tool=PythonAstREPLTool(return_direct=True, globals=globals, locals=globals),  # type: ignore
                agent_type=agent_type,
                prefix=dedent_ws(PREFIX.format(st_container_name=name)),
                verbose=True,
                agent_executor_kwargs={"handle_parsing_errors": True},
            )
            cmd = """display a graphic with random values in Y and time in Z"""
            prompt = f"""
            Your goal is: {cmd}
            """
            prompt = dedent(prompt)
            print(prompt, agent_executor)
            result = agent_executor.run(prompt)
        else:
            result = "no know ST container"
        return result


# dataframe_agent = create_pandas_dataframe_agent(
#     config.chat_gpt,
#     df,
#     verbose=True,
#     agent_type=AgentType.OPENAI_FUNCTIONS,
# )
