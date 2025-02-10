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

def async_handler(async_func):
    """Wrapper to handle async functions in the graph."""
    async def wrapper(state):
        return await async_func(state)
    return wrapper

def create_graph(session_id: str):
# def create_graph():
    # GRAPH INSTANCE
    builder = StateGraph(State)
    

    # ADD NODES TO THE GRAPH
    # builder.add_node("research_query_generator", lambda state: research_query_generator(state, session_id))
    builder.add_node("research_query_generator", research_query_generator)
    builder.add_node("research_query_answerer", research_query_answerer)
    builder.add_node("formatter", formatter)  
    # builder.add_node("human_input_node", async_handler(human_input_node))
    # added below comment for publish api to work
    # builder.add_node("human_input_node", human_input_node)
    builder.add_node("save_changes", save_changes)

    # ADD EDGES TO THE GRAPH
    builder.add_edge(START, "research_query_generator")
    builder.add_edge("research_query_generator", "research_query_answerer")
    builder.add_edge("research_query_answerer", "formatter")
    builder.add_edge("formatter", "save_changes")
    builder.add_edge("save_changes", END)

    return builder


def compile_graph(builder):
    '''COMPILE GRAPH'''
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    return graph

def print_stream(stream):
    """Print all fields from the state, with fallback handling for empty messages"""
    for s in stream:
        print("\n=== State Update ===")
        
        # Handle messages separately with fallback for empty list
        if "messages" in s:
            if s["messages"]:  # If messages list is not empty
                message = s["messages"][-1]
                print("\nLatest Message:")
                if isinstance(message, tuple):
                    print(message)
                else:
                    message.pretty_print()
            else:
                print("\nMessages: []")
        
        # Print all other fields in the state
        for key, value in s.items():
            if key != "messages":  # Skip messages as we handled them above
                print(f"\n{key}:")
                print(value)
        
        print("\n" + "="*20)

