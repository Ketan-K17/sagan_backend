import json
import logging
from typing import List, Dict,Optional
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, AnyMessage, HumanMessage
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from colorama import init, Fore, Back, Style
from fastapi import WebSocket,WebSocketDisconnect,HTTPException
import asyncio

'''LOCAL IMPORTS'''
from schemas import State
from prompts.prompts import *
from models.chatgroq import BuildChatGroq, BuildChatOpenAI

'''IMPORT ALL TOOLS HERE AND CREATE LIST OF TOOLS TO BE PASSED TO THE AGENT.'''
from tools.script_executor import run_script
from tools.file_tree import get_file_tree
# from tools.web_tool import web_search_tool
from tools.query_chromadb import query_chromadb
# from utils.mdtopdf import convert_md_to_pdf
from utils.latextopdf import LaTeXPipeline
from pathlib import Path
import importlib.util
import certifi
import os

# Dynamically resolve the path to config.py
CURRENT_FILE = Path(__file__).resolve()
SAGAN_MULTIMODAL = CURRENT_FILE.parent.parent.parent.parent
CONFIG_PATH = SAGAN_MULTIMODAL / "config.py"

os.environ['SSL_CERT_FILE'] = certifi.where()

# Load config.py dynamically
spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

load_dotenv()
init()

terminal_tools = [run_script, get_file_tree]
research_tools = [query_chromadb]

'''LLM TO USE'''
from smolagents import ToolCallingAgent, HfApiModel
# select model
model_id = "meta-llama/Llama-3.3-70B-Instruct"
# model_id = "Qwen/Qwen2.5-72B-Instruct"
# model_id = "mistralai/Mistral-7B-Instruct-v0.3"
# model_id = "NousResearch/Hermes-3-Llama-3.1-8B"
model = HfApiModel(model_id=model_id)  
# MODEL = "llama-3.1-70b-versatile"
# MODEL = "llama-3.1-8b-instant"
# MODEL = "gemma2-9b-it"
# MODEL = "llama3-groq-70b-8192-tool-use-preview"
# MODEL = "mixtral-8x7b-32768"
MODEL = "gpt-4o"
# llm = BuildChatGroq(model=MODEL, temperature=0)
llm = BuildChatOpenAI(model=MODEL, temperature=0)

llm_with_terminal_tools = llm.bind_tools(terminal_tools)
llm_with_research_tools = llm.bind_tools(research_tools)

research_tools_node = ToolNode(research_tools)

message_queues = {}

class WebSocketManager:
    def __init__(self):
        self.active_connections = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept and track a WebSocket connection."""
        # async with self.lock:
        if session_id in self.active_connections:
            
            # await self.disconnect(session_id)
            print("connect to seesion id already exist")
            await websocket.accept()
            self.active_connections[session_id] = websocket
            self.lock = asyncio.Lock()

            message_queues[session_id] = asyncio.Queue()
            return
        await websocket.accept()
        self.active_connections[session_id] = websocket
        message_queues[session_id] = asyncio.Queue()
        print(f"Connected: {session_id}")

    async def disconnect(self, session_id: str):
        """Remove a disconnected WebSocket."""
        async with self.lock:
            if session_id in self.active_connections:
                self.active_connections.pop(session_id)
                del message_queues[session_id]
                print(f"Disconnected: {session_id}")

    # async def send_message(self, session_id: str, message: str):
    #     """Send a message to a specific client."""
    #     async with self.lock:
    #         websocket = self.active_connections.get(session_id)
    #         if websocket:
    #             try:
    #                 await websocket.send_text(message)
    #                 print(f"Sent to {session_id}: {message}")
    #             except Exception as e:
    #                 print(f"Error sending to {session_id}: {e}")
    #         else:
    #             print(f"Session {session_id} not connected.")
    async def send_message(self, session_id: str, message: str):
        """Send a message to a specific client."""
        # async with self.lock:
        websocket = self.active_connections.get(session_id)
        if websocket:
            try:
                json_message = json.dumps(message)
                await websocket.send_text(json_message)
                print(f"Sent to {session_id}: {json_message}")
            except Exception as e:
                print(f"Error sending to {session_id}: {e}")
        else:
            print(f"Session {session_id} not connected.")

    async def receive_message(self, session_id: str):
        """Receive a message from a specific client."""
        async with self.lock:
            websocket = self.active_connections.get(session_id)
            print(websocket,"websocket 117")
            if websocket:
                try:
                    message = await websocket.receive_text()
                    message_data = json.loads(message)
                    key = message_data.get("key")
                    value = message_data.get("value")
                    print("Received key:", key, "Received value:", value)
                    await message_queues[session_id].put((key, value))
                    print(f"Received from {session_id}: {message_data}")
                    return message_data
                except WebSocketDisconnect:
                    print(f"Error receiving from {session_id}: WebSocket disconnected")
                    await self.disconnect(session_id)  # Clean up
                    return None
                except Exception as e:
                    print(f"Error receiving from {session_id}: {e}")
                    return None
            else:
                print(f"Session {session_id} not connected.")
                await ws_manager.active_connections.clear()
                await websocket.active_connections.clear()
                return None
            
    async def get_message(self, session_id: str, key: str, timeout: int = 500):
        queue = message_queues.get(session_id)
        print(queue,"queue 141")
        if not queue:
            raise HTTPException(status_code=404, detail="Session not found.")
        
        try:
            # Wait for a message with a timeout
            while True:
                key_value = await asyncio.wait_for(queue.get(), timeout=timeout)
                print(key_value,"key_value 150")
                if key_value[0] == key:
                    return key_value[1]
                # Put back unmatched keys
                await queue.put(key_value)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=408, detail=f"No message received within {timeout} seconds.")
ws_manager = WebSocketManager()

async def research_query_generator(state: State) -> State:
    """
    Node to generate research queries and allow user modification via WebSocket.
    """
    session_id = "1234"
    print(f"{Fore.YELLOW}################ RESEARCH QUERY GENERATOR BEGIN #################")
    empty_prompt = """{{managed_agents_descriptions}}"""
    # create the agent; this is equivalent of the llm object we previously used.
    agent = ToolCallingAgent(model=model, tools=[], system_prompt=empty_prompt)
    user_prompt = f"""
    Section Title: {state['section_title']}
    Section Text: {state['section_text']}
    """
    state["user_prompt"] = state["messages"][1].content

    combined_prompt = RESEARCH_QUERY_GENERATOR_PROMPT + "\n" + user_prompt

    try:
        # Generate queries with LLM
        #response = llm.invoke(state["messages"])
        response = agent.provide_final_answer(combined_prompt)
        if not response or not hasattr(response, 'content'):
            raise ValueError("Invalid response from LLM.")

        # Extract research queries
        response_content = json.loads(response)
        research_queries = response_content.get('research_queries', [])
        print("Generated Research Queries:", research_queries)

        # Ask the user via WebSocket if they want to modify queries
        print("323")
        await ws_manager.send_message("1234",{
            "type":"question1",
            "data":"Would you like to modify or add queries? (yes/no)"
        })
        # user_input = await ws_manager.wait_for_response(
        #     "1234"
        # )
        # print("327",user_input)
        user_input_str = await ws_manager.get_message(session_id, 'question1')
        print(user_input_str,"user_input_str 434")
        # user_input = json.loads(user_input_str)
                   
        # user_input_value = user_input.get("value")
        # print( user_input_value,"user input 434", user_input_value and  user_input_value.lower() == 'yes')
        print(f"------------------------Received message: {user_input_str}")
        if  user_input_str and  user_input_str.lower() == 'yes':
            modified_queries = []
            
            # Modify existing queries
            for i, query in enumerate(research_queries, start=1):
                print('do this later')
                # await ws_manager.send_message("1234",{
                #     "type":"question",
                #     "data":f"Modify query {i} (or leave blank to keep it unchanged):"
                # })
                # new_query = await ws_manager.wait_for_response(
                #     "1234"
                # )
                # modified_queries.append(new_query or query)
            
            # Add new queries
            while True:
               
                await ws_manager.send_message("1234",{
                    "type":"question2",
                    "data":"Would you like to add a new query? (yes/no)"
                })
                add_more= await ws_manager.get_message(session_id, 'question2')
                # add_more = await ws_manager.wait_for_response(
                #     "1234"
                # )

                print("351",add_more)
                # add_more = await ws_manager.query_user(
                #     session_id, "Would you like to add a new query? (yes/no)"
                # )
                if add_more and add_more.lower() != 'yes':
                    break
                await ws_manager.send_message(session_id,{
                    "type":"question3",
                    "data":f"Enter new query {len(modified_queries) + 1}:"
                })

                new_query = await ws_manager.get_message(session_id,"question3")
                print(new_query,"new_query")
                # new_query = await ws_manager.query_user(
                #     session_id, f"Enter new query {len(modified_queries) + 1}:"
                # )

                if new_query:
                    modified_queries.append(new_query)

            research_queries = modified_queries

        # Update state
        state["research_needed"] = bool(research_queries)
        state["research_queries"] = research_queries
        print(f"Final Research Queries: {research_queries}")

        return state

    except Exception as e:
        print(f"Error in research_query_generator: {str(e)}")
        state["messages"] = [str(e)]
        return state


# new code below be aware llm code ahead

# def research_query_generator(state: dict, research_queries: List[str]) -> dict:
#     """
#     Process the state and research queries synchronously.
#     This function assumes that all necessary inputs have been provided beforehand.
#     """
#     try:
#         # Update the state with the finalized research queries
#         state["research_needed"] = len(research_queries) > 0
#         state["research_queries"] = research_queries

#         # Log the updated state
#         print("\nFinal research queries:")
#         for i, query in enumerate(research_queries, start=1):
#             print(f"{i}. {query}")

#         return state

#     except Exception as e:
#         print(f"Error in research_query_generator: {str(e)}")
#         state["messages"] = [str(e)]
#         state["research_needed"] = False
#         state["research_queries"] = []
#         return state

# my code ahead
def research_query_answerer(state: State) -> State:
    """
    Takes the generated queries and executes them against the vector database.
    Only runs if research_needed is True.
    """
    print(f"{Fore.BLUE}################ RESEARCH QUERY ANSWERER BEGIN #################")

    try:
        if not state.get("research_needed"):
            state["context"] = []
            return state

        section_title=state.get("section_title"),
        section_text=state.get("section_text"),
        research_queries=state.get("research_queries")
        # Add the query answerer prompt to messages

        user_prompt = """
        Section Title: {section_title}
        Section Text: {section_text}
        Research Queries: {research_queries}"""

        research_query_answerer_prompt = RESEARCH_QUERY_ANSWERER_PROMPT + "\n" + user_prompt
        state["messages"].append(research_query_answerer_prompt)

        context = []
        for query in state["research_queries"]:
            result = query_chromadb(
                str(config.VECTOR_DB_PATHS['astro_db']),  # Use path from config
                config.MODEL_SETTINGS['SENTENCE_TRANSFORMER'],  # Use model setting from config
                query
            )
            context.extend(result)

        state["context"] = context

        print(f"\n\n\n\nstate at the end of query answerer: \n")
        ## printing messages
        print("Messages: ")
        messages = state["messages"]
        if len(messages) >= 3:
            for message in messages[-3:]:
                print(f"{message.type}: {message.content}")
        else:
            for message in messages:
                print(f"{message.type}: {message.content}")

        ## printing fields other than messages.
        for field_name, field_value in state.items():
            if field_name != "messages":
                print(f"- {field_name.capitalize()}: {field_value}")
        print(f"################ QUERY ANSWERER END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error occurred: {e}")
        print(f"################ QUERY ANSWERER END #################{Style.RESET_ALL}")
        state["messages"] = [str(e)]
        state["section_title"] = None
        state["section_text"] = None
        state["rough_draft"] = None
        state["research_queries"] = None
        state["context"] = None
        return state


def formatter(state: State):
    print(f"{Fore.LIGHTGREEN_EX}################ FORMATTING NODE BEGIN #################")
    empty_prompt = """{{managed_agents_descriptions}}"""
    # create the agent; this is equivalent of the llm object we previously used.
    agent = ToolCallingAgent(model=model, tools=[], system_prompt=empty_prompt)

    # Ensure state values are not None
    section_title = state.get("section_title", "")
    user_prompt = state.get("user_prompt", "")
    section_text = state.get("section_text", "")
    context = state.get("context", "")


    formatter_user_prompt = f"""
    Section Title: {section_title}
    Section Text: {section_text}
    User Prompt: {user_prompt}
    Context: {context}
    """
    

    # populating the agent prompt
    # formatter_prompt = FORMATTER_PROMPT.format(
    #     user_prompt=user_prompt,
    #     section_text=section_text,
    #     context=context
    # )

    combined_prompt = FORMATTER_PROMPT + "\n" + formatter_user_prompt

    # appending the formatter prompt to list of messages
    state["messages"].append(SystemMessage(content=combined_prompt))
    
    # invoking the llm, response in json.
    #response = llm.invoke(state["messages"])
    response = agent.provide_final_answer(combined_prompt)
    raw_response = response

    try:
        # Parse the JSON response
        json_str = raw_response
        if '```json' in json_str:
            json_str = json_str.split('```json')[1].split('```')[0].strip()
        
        
        # Parse JSON
        response_json = json.loads(json_str)
        
        # Extract modified_section_text
        state["modified_section_text"] = response_json.get("modified_section_text")
        
        state["ai_message"] = response_json.get("ai_message")

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        state["modified_section_text"] = None
        state["ai_message"] = f"Error processing your request: {str(e)}"
    except Exception as e:
        print(f"Error processing response: {e}")
        state["modified_section_text"] = None
        state["ai_message"] = f"Error processing your request: {str(e)}"

    print(f"################ FORMATTING NODE END #################{Style.RESET_ALL}")
    return state


# original code below 
# def human_input_node(state: State):
#     print(f"{Fore.LIGHTMAGENTA_EX}################ HUMAN INPUT NODE BEGIN #################")

#     response = input("Saves Changes to the section text? (yes/no): ")
#     state["user_approval"] = response
#     print(f"################ HUMAN INPUT NODE END #################{Style.RESET_ALL}")
#     return state

# gpt code belwo 

async def human_input_node(state: State):
    print(f"{Fore.LIGHTMAGENTA_EX}################ HUMAN INPUT NODE BEGIN #################")
    await ws_manager.send_message("1234",{
        "type":"question4",
        "data":"Saves Changes to the section text? (yes/no): "
    })

    response = await ws_manager.get_message("1234","question4")
    print(response,"response 655")
    # response = input("Saves Changes to the section text? (yes/no): ")

    state["user_approval"] = response
    print(f"################ HUMAN INPUT NODE END #################{Style.RESET_ALL}")
    return state



def save_changes(state: State):
    print(f"{Fore.CYAN}################ SAVING CHANGES NODE BEGIN #################")
    try:
        # Only save if user approved
        if state.get("user_approval") == 'yes':
            tex_file_path = state.get("rough_draft_path")
            if not tex_file_path:
                raise ValueError("No LaTeX file path provided in state")

            # Read the entire LaTeX file
            with open(tex_file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            # Extract the document content between \begin{document} and \end{document}
            doc_start = content.find('\\begin{document}')
            doc_end = content.find('\\end{document}')

            if doc_start == -1 or doc_end == -1:
                raise ValueError("Could not find document environment in LaTeX file")

            preamble = content[:doc_start + len('\\begin{document}')]
            postamble = content[doc_end:]
            main_content = content[doc_start + len('\\begin{document}'):doc_end]

            # Split the content into sections based on \section commands
            import re
            section_pattern = r'(\\section\{[^}]*\}[\s\S]*?)(?=\\section\{|$)'
            sections = re.findall(section_pattern, main_content)

            # Validate section number
            section_number = state.get("section_number", 0)
            if section_number < 1 or section_number > len(sections):
                raise ValueError(f"Section number {section_number} is out of range. File has {len(sections)} sections.")

            # Get the modified section text from state
            modified_text = state.get("modified_section_text")
            if not modified_text:
                raise ValueError("No modified text provided in state")

            # Replace the section content while preserving the section command
            section_header_match = re.match(r'(\\section\{[^}]*\})', sections[section_number - 1])
            if section_header_match:
                section_header = section_header_match.group(1)
                sections[section_number - 1] = f"{section_header}\n{modified_text}\n"
            else:
                # If the section does not have a header, replace the content directly
                sections[section_number - 1] = modified_text

            # Reconstruct the document
            new_main_content = ''.join(sections)
            new_content = preamble + new_main_content + postamble

            # Write back to file
            with open(tex_file_path, 'w', encoding='utf-8') as file:
                file.write(new_content)

            print("Changes saved successfully to LaTeX file!")
            state["save_success"] = True
        else:
            print("User disapproved changes. No changes saved.")
            state["save_success"] = False

    except Exception as e:
        print(f"Error saving changes to LaTeX file: {str(e)}")
        state["save_success"] = False
        state["save_error"] = str(e)

    # Debugging: print state information
    for field_name, field_value in state.items():
        if field_name != "messages":
            print(f"- {field_name.capitalize()}: {field_value}")

    print(f"################ SAVING CHANGES NODE END #################{Style.RESET_ALL}")
    return state

