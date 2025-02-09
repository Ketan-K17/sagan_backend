import json
import logging
from typing import List
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from colorama import init, Fore, Style

# Python-docx imports.
from docx import Document
from docx.oxml import OxmlElement
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH



'''LOCAL IMPORTS'''
from schemas import State
from prompts.prompts import PROMPT_PARSER_PROMPT, ABSTRACT_QUESTIONS_GENERATOR_PROMPT, ABSTRACT_ANSWERS_GENERATOR_PROMPT, SECTION_TOPIC_EXTRACTOR_PROMPT, SECTION_WISE_QUESTION_GENERATOR_PROMPT, SECTION_WISE_ANSWERS_GENERATOR_PROMPT, PLAN_PROMPT, WRITER_PROMPT
from models.chatgroq import BuildChatGroq, BuildChatOpenAI
from .node_utils import save_state_for_testing, copy_figures

'''IMPORT ALL TOOLS HERE AND CREATE LIST OF TOOLS TO BE PASSED TO THE AGENT.'''
from tools.script_executor import run_script
from tools.file_tree import get_file_tree
from tools.query_chromadb import query_chromadb
from tools.multimodal_query import NomicVisionQuerier
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
from schemas import State

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
init()

logger = logging.getLogger(__name__)

# Define tools for terminal and research nodes
terminal_tools = [run_script, get_file_tree]
research_tools = [query_chromadb]

'''LLM TO USE'''
from smolagents import ToolCallingAgent, HfApiModel
# select model
# model_id = "meta-llama/Llama-3.3-70B-Instruct"
# model_id = "Qwen/Qwen2.5-72B-Instruct"
model_id = "meta-llama/Meta-Llama-3.1-70B-Instruct"
# model_id = "mistralai/Mistral-7B-Instruct-v0.3"
# model_id = "NousResearch/Hermes-3-Llama-3.1-8B"
model = HfApiModel(model_id=model_id)   

MODEL = "gpt-4o"
llm = BuildChatOpenAI(model=MODEL, temperature=0)

def prompt_parser(state: State) -> State:
    """
    Given a user prompt, this node parses the prompt to extract the project title and description based on the project title.
    """
    print(f"{Fore.YELLOW}################ PROMPT PARSER BEGIN #################")
    empty_prompt = """"""
    agent = ToolCallingAgent(
        model=model, 
        tools=[], 
        prompt_templates={"system_prompt": empty_prompt}
    )

    # logging the system prompt to ensure it's empty. text will be yellow.
    print(f"HERE'S THE SYSTEM PROMPT: {agent.system_prompt}")

    try:
        user_prompt = state["user_prompt"]

        combined_user_prompt = PROMPT_PARSER_PROMPT + "\n" + user_prompt

        # llm call.
        response = agent.provide_final_answer(combined_user_prompt, images=None)
        print(f"HERE'S THE PROMPT PARSER RESPONSE: {response}")
        response_json = json.loads(response)
        
        print(f"HERE'S THE RESPONSE: {response}")
        
        # updating state before end-of-node logging
        state["project_title"] = response_json["project_title"]
        state["project_description"] = response_json["project_description"]

        # saving state in human readable format and machine readable format under outputpdf/nodewise_output
        save_state_for_testing(state, "prompt_parser")

        print(f"################ PROMPT PARSER END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error in prompt_parser: {e}")
        raise

def abstract_questions_generator(state: State) -> State:
    """
    Given the project title and description, this node creates a list of questions that may help it understand the project better. The answers to these questions will then be used to create a project abstract.
    """
    print(f"{Fore.RED}################ ABSTRACT QUESTIONS GENERATOR BEGIN #################")
    project_title = state.get("project_title", "")
    project_description = state.get("project_description", "")
    
    empty_prompt = """"""
    agent = ToolCallingAgent(
        model=model, 
        tools=[], 
        prompt_templates={"system_prompt": empty_prompt}
    )
    user_prompt = f"""
    Project Title: {project_title}
    Project Description: {project_description}
    """
    combined_prompt = ABSTRACT_QUESTIONS_GENERATOR_PROMPT + user_prompt
    print(f"HERE'S THE COMBINED PROMPT: {combined_prompt}")

    try:
        response = agent.provide_final_answer(combined_prompt, images=None)
        
        # if not response or not hasattr(response, 'content'):
        #     raise ValueError("Invalid response from LLM.")

        response_json = json.loads(response)
        
        # Update state before end-of-node logging
        state["abstract_questions"] = response_json["abstract_questions"]

        # saving state in human readable format and machine readable format under outputpdf/nodewise_output
        save_state_for_testing(state, "abstract_questions_generator")

        print(f"################ ABSTRACT QUESTIONS GENERATOR END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error in abstract_questions_generator: {e}")
        print(f"################ ABSTRACT QUESTIONS GENERATOR END #################{Style.RESET_ALL}")
        state["messages"].append(SystemMessage(content=f"Error: {e}"))
        state["abstract_questions"] = None
        return state

def abstract_answers_generator(state: State) -> State:
    """
    Given the list of questions, this node creates answers to the questions generated by the abstract_questions_generator node.
    """
    print(f"{Fore.BLUE}################ ABSTRACT ANSWERS GENERATOR BEGIN #################")
    abstract_questions = state["abstract_questions"]
    sys_prompt = ABSTRACT_ANSWERS_GENERATOR_PROMPT
    empty_prompt = """"""

    try:
        agent = ToolCallingAgent(
            model=model, 
            tools=[], 
            prompt_templates={"system_prompt": empty_prompt}
        )
        # Use the research tools to actually query the database
        qa_pairs = {}
        for question in abstract_questions:
            result = query_chromadb(
                str(config.VECTOR_DB_PATHS['astro_db']),  # Use path from config
                config.MODEL_SETTINGS['SENTENCE_TRANSFORMER'],  # Use model setting from config
                question
            )
            # refactoring answer documents into one cohesive answer
            answer = agent.provide_final_answer(f"Frame the following texts into one cohesive answer: {result}. The question was: {question}", images=None)
            answer_text = answer.to_string() if hasattr(answer, 'to_string') else str(answer)
            qa_pairs[question] = answer_text
            print(f"Question: {question}\nAnswer: {answer_text}\n\n\n\n")

        # Now use the LLM to generate an abstract based on the retrieved answers
        state["abstract_qa_pairs"] = qa_pairs
        user_prompt = f"""
        Project Title: {state["project_title"]}
        Project Description: {state["project_description"]}

        Here's the list of question-answer pairs:
        {qa_pairs}
        """
        combined_prompt = sys_prompt + "\n" + user_prompt
        print(f"HERE'S THE COMBINED PROMPT: {combined_prompt}")
        response = agent.provide_final_answer(combined_prompt, images=None)
        response_json = json.loads(response)
        abstract_text = response_json["abstract_text"]
        print(f"Abstract Text: {abstract_text}")
        # Updating state before end-of-node logging
        state["abstract_text"] = abstract_text

        # saving state in human readable format and machine readable format under outputpdf/nodewise_output
        save_state_for_testing(state, "abstract_answers_generator")

        print(f"################ ABSTRACT ANSWERS GENERATOR END #################{Style.RESET_ALL}")

        return state


    except Exception as e:
        print(f"Error occurred: {e}")
        print(f"################ ABSTRACT ANSWERS GENERATOR END #################{Style.RESET_ALL}")
        #state["messages"] = [str(e)]
        #state["abstract_text"] = None
        return state

def section_topic_extractor(state: State) -> State:
    """
    This node extracts the topics for each section of the project from the template pdf given by the user.
    """
    print(f"{Fore.CYAN}################ SECTION TOPIC EXTRACTOR BEGIN #################")
    empty_prompt = """"""
    agent = ToolCallingAgent(
        model=model, 
        tools=[], 
        prompt_templates={"system_prompt": empty_prompt}
    )

    try:
        # using the chromadb tool on the response template doc to fetch corpus of text that may hopefully contain the section topics
        result = query_chromadb(
                str(config.VECTOR_DB_PATHS['fnr_template_db']),  # Use path from config
                config.MODEL_SETTINGS['SENTENCE_TRANSFORMER'],  # Use model setting from config
                "What are the sections/topics present in this template document?"
            )
        state["section_topics_corpus"] = result
        # Format the result list into a single string
        formatted_result = "\n".join(result) if isinstance(result, list) else str(result)
        # Combine the prompt and formatted result
        combined_prompt = f"{SECTION_TOPIC_EXTRACTOR_PROMPT}\n\nContext:\n{formatted_result}"
        
        response = agent.provide_final_answer(combined_prompt, images=None)
        print(f"HERE'S THE SECTION TOPIC EXTRACTOR RESPONSE: {response}")
        response_json = json.loads(response)
        section_topics_list = response_json["section_topics"]

        #if not response or not hasattr(response, 'content'):
        #    raise ValueError("Invalid response from LLM.")

        # Updating state before end-of-node logging
        state["section_topics"] = section_topics_list

        # saving state in human readable format and machine readable format under outputpdf/nodewise_output
        save_state_for_testing(state, "section_topic_extractor")

        print(f"################ SECTION TOPIC EXTRACTOR END #################{Style.RESET_ALL}")


        return state

    except Exception as e:
        print(f"Error occurred: {e}")
        print(f"################ SECTION TOPIC EXTRACTOR END #################{Style.RESET_ALL}")
        state["section_topics"] = None
        return state

def section_wise_question_generator(state: State) -> State:
    """
    Given the list of sections, this node creates a list of questions for each section.
    """
    print(f"{Fore.MAGENTA}################ SECTION WISE QUESTION GENERATOR BEGIN #################")
    section_topics = state["section_topics"]
    project_title = state["project_title"]
    project_description = state["project_description"]
    abstract_text = state["abstract_text"]
    # Convert section_topics list to a formatted string
    formatted_topics = "\n".join(section_topics)
    combined_prompt = SECTION_WISE_QUESTION_GENERATOR_PROMPT + "\nsection_topics: " + formatted_topics + "\nproject_title: " + project_title + "\nproject_description: " + project_description + "\nabstract_text: " + abstract_text

    empty_prompt = """"""
    agent = ToolCallingAgent(
        model=model, 
        tools=[], 
        prompt_templates={"system_prompt": empty_prompt}
    )
    try:
        response = agent.provide_final_answer(combined_prompt, images=None)
        
        # Parse and validate JSON response
        try:
            section_questions_list = json.loads(response)
            
            # Validate the structure: should be dict[str, list[str]]
            if not isinstance(section_questions_list, dict):
                raise ValueError("Response must be a dictionary")
            
            for section, questions in section_questions_list.items():
                if not isinstance(section, str):
                    raise ValueError(f"Section key must be string, got {type(section)}")
                if not isinstance(questions, list):
                    raise ValueError(f"Questions must be a list for section {section}")
                if not all(isinstance(q, str) for q in questions):
                    raise ValueError(f"All questions must be strings in section {section}")

        except json.JSONDecodeError:
            print("Failed to parse JSON response")
            raise
        except ValueError as ve:
            print(f"Invalid response structure: {ve}")
            raise

        print(f"HERE'S THE SECTION WISE QUESTION GENERATOR RESPONSE: {response}")

        # Updating state before end-of-node logging
        state["section_questions"] = section_questions_list
        
        # saving state in human readable format and machine readable format under outputpdf/nodewise_output
        save_state_for_testing(state, "section_wise_question_generator")

        print(f"################ SECTION WISE QUESTION GENERATOR END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error occurred: {e}")
        print(f"################ SECTION WISE QUESTION GENERATOR END #################{Style.RESET_ALL}")
        #state["section_questions"] = None
        return state

def section_wise_answers_generator(state: State) -> State:
    """
    Generates answers for section-wise questions using the multimodal_vectordb_query tool.
    Integrates results into the 'section_answers' schema.
    """
    print(f"{Fore.GREEN}################ SECTION WISE ANSWERS GENERATOR BEGIN #################")
    
    section_questions = state.get("section_questions")
    if not section_questions:
        error_msg = "No section questions found in state. Previous node may have failed."
        print(f"Error: {error_msg}")
        state["messages"].append(SystemMessage(content=error_msg))
        state["section_answers"] = None
        return state

    try:
        # Initialize the multimodal query tool
        multimodal_tool = NomicVisionQuerier()
        section_answers = {}

        # Define the output file path
        output_path = config.NODEWISE_OUTPUT_PATH / "section_wise_answers_generator_logging.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists

        with output_path.open("w", encoding="utf-8") as file:
            # Iterate over each section and its questions
            for section, questions in section_questions.items():
                file.write(f"\nProcessing section: {section}\n")
                section_answers[section] = []
                
                for question in questions:
                    file.write(f"\nQuerying for question: \n{question}\n")
                    
                    try:
                        # Use the multimodal_vectordb_query tool with correct parameters
                        results = multimodal_tool.multimodal_vectordb_query(
                            persist_dir=str(config.VECTOR_DB_PATHS['astro_ai2']),
                            query=question,
                            k=5
                        )
                        
                        file.write(f"Query results: {results}\n")
                        
                        if results and "Results" in results:
                            # Process each result and format according to schema
                            for result in results["Results"]:
                                answer_entry = {
                                    "content": result.get("content", ""),
                                    "images": result.get("images", [])
                                }
                                
                                # Only add non-empty results
                                if answer_entry["content"] or answer_entry["images"]:
                                    section_answers[section].append(answer_entry)
                                    file.write(f"Added answer entry with content length: {len(answer_entry['content'])}\n")
                                    file.write(f"Number of images: {len(answer_entry['images'])}\n")
                        else:
                            file.write("No results found for query\n")
                            
                    except Exception as query_error:
                        file.write(f"Error processing query: {query_error}\n")
                        continue

                # If no answers were found for the section, add a placeholder
                if not section_answers[section]:
                    section_answers[section] = [{
                        "content": "No relevant information found.",
                        "images": []
                    }]

                file.write(f"Completed answers for section: {section}\n")
                file.write(f"Number of answers: {len(section_answers[section])}\n")

            # Update state with the collected answers
            state["messages"].append(SystemMessage(content="Section-wise answers generated successfully"))
            state["section_answers"] = section_answers

            # Debug output
            file.write("\nFinal section answers structure:\n")
            for section, answers in section_answers.items():
                file.write(f"\nSection: {section}\n")
                file.write(f"Number of answers: {len(answers)}\n")
                for idx, answer in enumerate(answers):
                    file.write(f"Answer {idx + 1} - Content length: {len(answer['content'])}\n")
                    file.write(f"Number of images: {len(answer['images'])}\n")

        # saving state in human readable format and machine readable format under outputpdf/nodewise_output
        save_state_for_testing(state, "section_wise_answers_generator")

        print(f"################ SECTION WISE ANSWERS GENERATOR END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        print(f"################ SECTION WISE ANSWERS GENERATOR END #################{Style.RESET_ALL}")
        state["messages"].append(str(e))
        state["section_answers"] = None
        return state

def plan_node(state: State):
    print(f"{Fore.LIGHTYELLOW_EX}################ PLAN NODE BEGIN #################")
    
    empty_prompt = """"""
    agent = ToolCallingAgent(
        model=model, 
        tools=[], 
        prompt_templates={"system_prompt": empty_prompt}
    )
    try:
        # Construct prompt with project info
        user_prompt = f"""
        Project Title: {state["project_title"]}
        Project Description: {state["project_description"]}
        Abstract: {state["abstract_text"]}
        Section Topics = {state["section_topics"]}
        Section Content: {state["section_answers"]}
        """
        combined_prompt = PLAN_PROMPT + "\n" + user_prompt

        # Get response from agent
        response = agent.provide_final_answer(combined_prompt, images=None)
        print(f"Here's the response: {response}")

        # Extract JSON from markdown code block and parse
        json_str = response.replace('```json\n', '').replace('\n```', '').strip()
        plan_dict = json.loads(json_str)
        
        state["plan"] = plan_dict
        save_state_for_testing(state, "plan")
        return state
            
    except Exception as e:
        print(f"Error in plan_node: {e}")
        raise


class GenerationError(Exception):
    """Custom exception for generation-related errors."""
    pass



def generation_node(state: dict) -> dict:
    """
    Generates LaTeX sections iteratively for each section using the plan structure.
    Returns updated state with generated sections.
    """
    print(f"{Fore.LIGHTYELLOW_EX}################ GENERATION NODE BEGIN #################")
    
    empty_prompt = """"""
    agent = ToolCallingAgent(
        model=model, 
        tools=[], 
        prompt_templates={"system_prompt": empty_prompt}
    )
    
    try:
        plan = state.get("plan")
        if not plan:
            raise ValueError("No plan found in state")

        generated_sections = {}

        document_so_far = ""

        for section_title, steps in plan.items():
            print(f"Generating content for section: {section_title}")
            document_so_far += f"## {section_title}\n"
            
            # Format section plan
            section_plan_formatted = "\n".join(f"- {step}" for step in steps)
            
            # Construct prompt
            project_information = f"""
            Project Title: {state["project_title"]}
            Project Description: {state["project_description"]}
            Abstract: {state["abstract_text"]}
            Current Section: {section_title}
            Section Plan:
            {section_plan_formatted}
            Project Document So Far:
            {document_so_far}
            """
            
            combined_prompt = WRITER_PROMPT + "\n" + project_information
            
            # Get response from agent
            response = agent.provide_final_answer(combined_prompt, images=None)
            print(f"Successfully generated content for {section_title}")

            document_so_far += response
            generated_sections[section_title] = response

        state["generated_sections"] = generated_sections
        save_state_for_testing(state, "generation")
        
        print(f"{Fore.LIGHTYELLOW_EX}################ GENERATION NODE END #################{Style.RESET_ALL}")
        return state
            
    except Exception as e:
        print(f"Error in generation_node: {e}")
        state["messages"].append(str(e))
        state["generated_sections"] = None
        return state


def formatting_node(state: State) -> State:
    print(f"{Fore.LIGHTYELLOW_EX}################ FORMATTING NODE BEGIN #################")
    base_output_path = config.OUTPUT_PDF_PATH
    # Create a new Document
    doc = Document()

    project_title = state["project_title"]
    abstract_text = state["abstract_text"]
    generated_sections = state.get("generated_sections", {})

    # Add a title to the document
    title = doc.add_heading(project_title, 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Add abstract to the document
    doc.add_heading("Abstract", 1)
    doc.add_paragraph(abstract_text)

    # Add generated sections to the document
    if generated_sections:
        for section_header, section_content in generated_sections.items():
            doc.add_heading(section_header, level=1)
            doc.add_paragraph(section_content)

    # Save the document to the base_output_path
    output_docx_path = base_output_path / "output.docx"
    doc.save(output_docx_path)
    print(f"Word document written to: {output_docx_path}")
    # make 'figures' folder under output_pdf_path if not there already
    figures_path = Path(base_output_path / "figures")
    figures_path.mkdir(parents=True, exist_ok=True)

    os.environ["TOKENIZERS_PARALLELISM"] = "false"


    print(f"################ FORMATTING NODE END #################{Style.RESET_ALL}")

    # Save state in both human-readable and machine-readable formats
    save_state_for_testing(state, "formatting_node")

    return state






