from langgraph.graph import StateGraph, END, START
from langgraph.constants import END
from langgraph.checkpoint.memory import MemorySaver

from dotenv import load_dotenv

# LOCAL IMPORTS
from nodes_and_conditional_edges.nodes import *
from nodes_and_conditional_edges.conditional_edges import *
from tools import *
from schemas import State


load_dotenv()

# def create_graph(session_id: str):
def create_graph():
    # GRAPH INSTANCE
    builder = StateGraph(State)
    

    # ADD NODES TO THE GRAPH
    # builder.add_node("research_query_generator", lambda state: research_query_generator(state, session_id))
    builder.add_node("research_query_generator", research_query_generator)
    builder.add_node("research_query_answerer", research_query_answerer)
    builder.add_node("formatter", formatter)
    builder.add_node("research_tools_node", research_tools_node)  
    # builder.add_node("human_input_node", lambda state: human_input_node(state, session_id))
    # added below comment for publish api to work
    # builder.add_node("human_input_node", human_input_node)
    # builder.add_node("save_changes", save_changes)

    # ADD EDGES TO THE GRAPH
    builder.add_edge(START, "research_query_generator")
    builder.add_edge("research_query_generator", "research_query_answerer")
    builder.add_conditional_edges(
        "research_query_answerer",
        research_tools_condition,
        {
            "research_tools_node": "research_tools_node",
            "formatter": "formatter"
        }
    )
    builder.add_edge("research_tools_node", "research_query_answerer")
    builder.add_edge("formatter", END)
    # added below comment for publish api to work
    # builder.add_edge("formatter", "human_input_node")
    # builder.add_edge("save_changes", END)
    # builder.add_edge("human_input_node", END)
#     builder.add_conditional_edges(
#     "human_input_node",  # The node to evaluate
#     routing_function,    # The routing function
#     {                 # Mapping of outputs to next nodes
#         "yes": "save_changes",
#         "no": "formatter"
#     }
# )
    return builder


def compile_graph(builder):
    '''COMPILE GRAPH'''
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    return graph

def print_stream(stream):
    for s in stream:
        message = s["messages"][-1]
        if isinstance(message, tuple):
            print(message)
        else:
            message.pretty_print()

