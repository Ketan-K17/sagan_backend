from sagan_workflow.spaider_agent_temp.nodes_and_conditional_edges.node_utils import load_state_for_testing, print_state
from sagan_workflow.spaider_agent_temp.nodes_and_conditional_edges.nodes import formatting_node
from dotenv import load_dotenv

import json
import logging
from typing import List
from langgraph.prebuilt import ToolNode
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from colorama import init, Fore, Style

'''LOCAL IMPORTS'''
from sagan_workflow.spaider_agent_temp.schemas import State
from sagan_workflow.spaider_agent_temp.prompts.prompts import *
from sagan_workflow.spaider_agent_temp.models.chatgroq import BuildChatGroq, BuildChatOpenAI
from sagan_workflow.spaider_agent_temp.nodes_and_conditional_edges.node_utils import save_state_for_testing, copy_figures
from sagan_workflow.spaider_agent_temp.utils.latex_to_markdown import create_markdown_pipeline

'''IMPORT ALL TOOLS HERE AND CREATE LIST OF TOOLS TO BE PASSED TO THE AGENT.'''
from sagan_workflow.spaider_agent_temp.tools.script_executor import run_script
from sagan_workflow.spaider_agent_temp.tools.file_tree import get_file_tree
from sagan_workflow.spaider_agent_temp.tools.query_chromadb import query_chromadb
from sagan_workflow.spaider_agent_temp.tools.multimodal_query import NomicVisionQuerier
#from utils.latextopdf import latex_to_pdf

import logging
from langchain_core.messages import SystemMessage, HumanMessage
from colorama import Fore, Style
#from utils.latextopdf import latex_to_pdf

import logging
from typing import Dict, Any
from colorama import Fore, Style
from langchain_core.messages import SystemMessage, HumanMessage
import os
from sagan_workflow.spaider_agent_temp.utils.latex_utils import extract_latex_and_message, build_content_summary, latex_to_pdf, latex_to_pdf_pandoc, verify_image_paths, verify_miktex_installation


from pathlib import Path
import importlib.util

# Dynamically resolve the path to config.py
CURRENT_FILE = Path(__file__).resolve()
SAGAN_MULTIMODAL = CURRENT_FILE.parent.parent.parent.parent
CONFIG_PATH = SAGAN_MULTIMODAL / "config.py"

# Load config.py dynamically
spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

load_dotenv(dotenv_path=config.ENV_PATH)

from smolagents import ToolCallingAgent, HfApiModel
########## import end here ##########



def section_topic_extractor(state: State) -> State:
    """
    This node extracts the topics for each section of the project from the template pdf given by the user.
    """
    print(f"{Fore.CYAN}################ SECTION TOPIC EXTRACTOR BEGIN #################")
    system_prompt = SystemMessage(SECTION_TOPIC_EXTRACTOR_PROMPT.format(
        vector_store_path=str(config.VECTOR_DB_PATHS['fnr_template_db']),  # Use path from config
        llm_name=config.MODEL_SETTINGS['SENTENCE_TRANSFORMER']  # Use model setting from config
    ))
    state["messages"].append(system_prompt)

    # select model
    model_id = "meta-llama/Llama-3.3-70B-Instruct"
    model = HfApiModel(model_id=model_id)   
    agent = ToolCallingAgent(model=model, tools=[query_chromadb])
    try:
        # response = llm_with_research_tools.invoke(state["messages"])
        response = agent.run(state["messages"])

        if not response or not hasattr(response, 'content'):
            raise ValueError("Invalid response from LLM.")

        llm_with_structured_output = llm.with_structured_output(SectionTopicExtractorOutput)
        structured_response = llm_with_structured_output.invoke(response.content)

        if not hasattr(structured_response, 'section_topics'):
            raise ValueError("Section topics not found in the structured output.")

        # Updating state before end-of-node logging
        state["messages"].append(response)
        state["section_topics"] = structured_response.section_topics

        # saving state in human readable format and machine readable format under outputpdf/nodewise_output
        save_state_for_testing(state, "section_topic_extractor")

        print(f"################ SECTION TOPIC EXTRACTOR END #################{Style.RESET_ALL}")


        return state

    except Exception as e:
        print(f"Error occurred: {e}")
        print(f"################ SECTION TOPIC EXTRACTOR END #################{Style.RESET_ALL}")
        state["messages"] = [str(e)]
        state["section_topics"] = None
        return state