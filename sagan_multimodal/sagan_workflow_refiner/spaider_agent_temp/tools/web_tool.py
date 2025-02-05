# import os
# from typing import Annotated
# from typing_extensions import TypedDict
# import langchain
# from langchain_community.llms import HuggingFaceHub
# from langchain_huggingface import ChatHuggingFace
# from langchain.schema import HumanMessage, SystemMessage
# from langchain_community.tools import DuckDuckGoSearchResults
# from langgraph.graph import StateGraph
# from langgraph.graph.message import add_messages
# from langgraph.prebuilt import ToolNode, tools_condition
# from langchain_core.messages import BaseMessage
# from langchain.tools import BaseTool
# from dotenv import load_dotenv
# from pydantic import Field

# load_dotenv()

# langchain.debug = False

# # LLM setup
# llm = HuggingFaceHub(
#     repo_id="meta-llama/Meta-Llama-3-8B-Instruct",
#     task="text-generation",
#     model_kwargs={
#         "max_new_tokens": 2000,
#         "top_k": 30,
#         "temperature": 0.1,
#         "repetition_penalty": 1.03,
#         "stream": True
#     },
# )

# # Define the messages
# messages = [
#     SystemMessage(content="You're a helpful assistant equipped with a web search tool. For any query do a semantic search and give an accurate technical answer backed with sound logic."),
#     HumanMessage(content="Answer my query using web-search tool with accurate and factual response."),
# ]

# # Initialize chat model
# chat_model = ChatHuggingFace(llm=llm)

# # Custom WebSearchTool
# class WebSearchTool(BaseTool):
#     name: str = Field(default="web_search")
#     description: str = Field(default="Useful for searching the web for current information.")
#     search: DuckDuckGoSearchResults = Field(default_factory=DuckDuckGoSearchResults)
    
#     def _run(self, query: str) -> str:
#         return self.search.run(query)

#     async def _arun(self, query: str) -> str:
#         return await self.search.arun(query)

# # Create an instance of the custom tool
# web_search_tool = WebSearchTool()
# # tools = [web_search_tool]

# # class State(TypedDict):
# #     messages: Annotated[list, add_messages]

# # graph_builder = StateGraph(State)
# # llm_with_tools = chat_model.bind_tools(tools)

# # def chatbot(state: State):
# #     messages = state["messages"]
# #     response = llm_with_tools.invoke(messages)
# #     return {"messages": messages + [response]}

# # graph_builder.add_node("chatbot", chatbot)

# # tool_node = ToolNode(tools=[web_search_tool])
# # graph_builder.add_node("tools", tool_node)

# # graph_builder.add_conditional_edges(
# #     "chatbot",
# #     tools_condition,
# # )
# # graph_builder.add_edge("tools", "chatbot")
# # graph_builder.set_entry_point("chatbot")
# # graph = graph_builder.compile()

# # def stream_responses(user_input):
# #     response_stream = graph.stream({"messages": [HumanMessage(content=user_input)]})
# #     for event in response_stream:
# #         for value in event.values():
# #             if isinstance(value["messages"][-1], BaseMessage):
# #                 yield value["messages"][-1].content

# # # Example usage
# # if __name__ == "__main__":
# #     user_input = "Who is Roger Federer?"
# #     for response in stream_responses(user_input):
# #         print(response, end="", flush=True)
