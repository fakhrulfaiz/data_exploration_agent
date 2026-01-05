import re
from typing import Optional, Union
from pydantic import BaseModel, Field
from langchain_experimental.tools import PythonAstREPLTool
from realtime import List

import os
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

# Load from env
load_dotenv()

model = init_chat_model("gpt-4o-mini")



# def get_data_preparation_tools(llm: ChatOpenAI, log_path):
#     """
   
#     Args:
#         question (str): The question.
#         context list(str)
#     Returns:
#         dataframe: the dataframe that is needed for a plot genration task.
#     """
#     prompt = ChatPromptTemplate.from_messages(
#         [
#             ("system", _SYSTEM_PROMPT),
#             ("user", "{question}"),
#             ("user", "{context}"),
            
#         ]
#     )
    
#     extractor = create_structured_output_runnable(ExecuteCode, llm, prompt)

# _DESCRIPTION = (
#     " data_preparation (question:str, context: Union[str, List[str],dict])-> str\n"
#     " This tools is a data preparation task. For given data and question, it porcess the data and prepare the proper data structure for a request. \n"
#     " - Minimize the number of `data_preparation` actions as much as possible."
#     " if you want this tools does its job properly, you should include all required information from the user query in previous tasks."
  
    
#     # Context specific rules below"
# )

# # " Plotting or any other visualization request should be done after each analysis.\n"
# _SYSTEM_PROMPT = """You are a data preparation and processing assistant. Create a proper structure for the provided data from the previous steps to answer the request.
# - If the required information has not found in the provided data, ask for replaning and ask from previous tools to include the missing information.
# - You should include all the input data in the code, and prevent of ignoring them by  `# ... (rest of the data)`.
# - You should provide a name or caption for each value in the final output considering the question and the input context."
# - Dont create any sample data in order to answer to the user question.
# - You should print the final data structure.
# - You should save the final data structure at the specified path with a proper filename.
# - You should output the final data structure as a final output.
# """


  
# class ExecuteCode(BaseModel):

#     reasoning: str = Field(
#         ...,
#         description="The reasoning behind the answer, including how context is included, if applicable.",
#     )

#     code: str = Field(
#         ...,
#         description="The simple code expression to execute by python_executor.",
#     )
    
#     data: str = Field(
#         ...,
#         description="The final data structure as a final output.",
#     )



    


# def data_preparation(
#     question: str,
#     context: Union[str, List[str],dict] = None,
#     config: Optional[RunnableConfig] = None,
# ):
    
#     print("context-first:", context,type(context))
#     context_str= str(context).strip()
#     # context_str = _ADDITIONAL_CONTEXT_PROMPT.format(
#     #     context= context_str.strip()
#     # )
#     # if 'data' in context:
#     #     context=context['data']
#     context_str += f"Save the generated data to the following directory: {log_path} and output the final data structure in data filed"
#     chain_input = {"question": question,"context":context_str}
#     # chain_input["context"] = [SystemMessage(content=context)]
                    
#     code_model = extractor.invoke(chain_input, config)

#     if code_model.code=='':
#         return code_model.reasoning 
#     codeExecution_result = python_repl.run(code_model.code)
#     if "Error" in codeExecution_result:
#         _error_handiling_prompt=f"Something went wrong on executing Code: `{code_model.code}`. This is the error I got: `{codeExecution_result}`. \\ Can you fixed the problem and write the fixed python code?"
#         chain_input["info"] =[HumanMessage(content= _error_handiling_prompt)]
#         code_model = extractor.invoke(chain_input)
#         try:
#             return code_model.data
#         except Exception as e:
#             return repr(e)
#     else:
#         # extract data from the code
        
#         return code_model.data

# helper
def _extract_code_from_block(response):
    if '```' not in response:
        return response
    if '```python' in response:
        code_regex = r'```python(.+?)```'
    else:
        code_regex = r'```(.+?)```'
    code_matches = re.findall(code_regex, response, re.DOTALL)
    code_matches = [item for item in code_matches]
    return  "\n".join(code_matches)

# PythonREPL instance
class PythonREPL:
    def __init__(self):
        self.local_vars = {}
        self.python_tool = PythonAstREPLTool()
    def run(self, code: str) -> str:
        code = _extract_code_from_block(code) 
        try:
            result = self.python_tool.run(code)
        except Exception as e:
            return f"Failed to execute. Error: {repr(e)}"
        return result
        
python_repl = PythonREPL()   

# Model for code generation structured output
class CodeGeneratorOutput(BaseModel):
    reasoning: str = Field(..., description="Reasoning for the code generation. State reason even if the code is not generated.")
    code: str = Field(..., description="Code to be executed.")
    file_name: str = Field(..., description="Name of the file where the data is saved. Example: `plot/scatter_plot_of_x_against_y.csv` for a plot. or `data/data_for_scatter_plot_of_x_against_y.csv` for a data file.")
# State to store the filename and description of its content

from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command
from langgraph.prebuilt import ToolRuntime

@tool("data_preparation_tool", description="use this tool to prepare the data for the plotting task. Mention what type of data structure for what type of plot you want.")
def data_preparation_tool(task: str):
    """Use this tool to prepare the data for the plotting task."""

    # use model to reason and generate code. 
    # if no code are given, return the reasoning to the agent (or even, return as feedback to main graph)

    # if code is given, execute the code (save the data to the log_path) and return the file name to the agent.
    pass

@tool("data_plotting_tool", description="use this tool to plot the data from a given csv file. Mentions what type of plot you want.")
def data_plotting_tool(task: str, file_path: str, runtime: ToolRuntime):
    """Use this tool to plot the data from a given csv file."""
    # use statically defined workspace dir for file path saving
    workspace_dir = "/home/afiq/fyp/fafa-repo/backend/app/agents/dev/workspace"
    file_path = os.path.join(workspace_dir, "data", file_path)

    # Get tool call id
    tool_call_id = runtime.tool_call_id

    prompt_template = ChatPromptTemplate.from_messages([
    (
        "system", 
        """You are a data visualization assistant. Create a proper plot to solve the user request accurately and correctly. 
        This is the path to the workspace directory: {workspace_dir}"""
    ),
    (
        "user", 
        """Your GOAL is {task}. 

Create a python code to properly plot for the data provided in the {file_path} csv file to satisfy the goal accurately. 

If the data is not suitable for the goal, return an empty string. 

Include this in your matplotlib import:
import matplotlib
matplotlib.use('Agg') # Call this BEFORE importing pyplot
import matplotlib.pyplot as plt"""
    )
])
    messages = prompt_template.format_messages(task=task, file_path=file_path, workspace_dir=workspace_dir)

    code_generator = model.with_structured_output(CodeGeneratorOutput)
    code_model : CodeGeneratorOutput = code_generator.invoke(messages)

    # check for empty code model (problematic data)
    if code_model.code == "":
        tool_message = ToolMessage(
            content=f"Code generation failed. Reason: {code_model.reasoning}",
            tool_call_id=tool_call_id,
        )
        return Command(
            update={
                "messages": [tool_message],
            }
        )

    else:
        # execute the code
        result = python_repl.run(code_model.code)
        # check for error
        if "Error" in result:
            tool_message = ToolMessage(
                content=f"Code execution failed. Error: {result}",
                tool_call_id=tool_call_id,
            )
            return Command(
                update={
                    "messages": [tool_message],
                }
            )
        tool_message = ToolMessage(
            content=f"Code execution successful. Plot saved to {code_model.file_name}",
            tool_call_id=tool_call_id,)
        return Command(
            update={
                "messages": [tool_message],
            }
        )


# tools = [data_preparation_tool]
tools = [data_plotting_tool]

from langchain_core.messages import SystemMessage, tool
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

# Main agent builder
def build_plotting_agent():
    
    # 2. Define the agent node properly
    def agent_node(state: MessagesState):
        system_prompt = (
            "You are a data visualization assistant. You can prepare data into a csv file and plot the data from a csv file. This are done wit your tools. \n\nUse your tools arsenals to achieve the user goal accurately. "
        )
        messages_for_llm = [SystemMessage(content=system_prompt)] + state["messages"]
        
        # Bind tools (data preparation and plotting)
        response = model.bind_tools(tools).invoke(messages_for_llm)
        
        # Return the response to be added to the state
        return {"messages": [response]}

    # 3. Build Graph
    builder = StateGraph(MessagesState)
    
    builder.add_node("agent", agent_node)
    builder.add_node("tools", ToolNode(tools))
    # builder.add_node("evaluator", evaluator_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        tools_condition,
        # ["tools", "evaluator"],
        )
    builder.add_edge("tools", "agent")
    # builder.add_edge("evaluator", END)

    return builder.compile()

agent = build_plotting_agent()
# Test
if __name__ == "__main__":
    # Example usage
    question = "Plot x and y in a scatter plot from the test.csv file."

    for step in agent.stream(
        {"messages": [{"role": "user", "content": question}]},
        stream_mode="values",
    ):
        step["messages"][-1].pretty_print()