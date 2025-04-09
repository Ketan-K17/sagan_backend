import os
import json
import logging
from dotenv import load_dotenv
from colorama import init, Fore, Style
import base64
from pathlib import Path
import importlib.util
from types import ModuleType
import shutil

# llm/langchain/agent related imports
from langchain_core.messages import SystemMessage
from smolagents import ToolCallingAgent, HfApiModel

# Python-docx imports.
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

'''LOCAL IMPORTS'''
from schemas import State
from prompts.prompts import PROMPT_PARSER_PROMPT, ABSTRACT_QUESTIONS_GENERATOR_PROMPT, ABSTRACT_ANSWERS_GENERATOR_PROMPT, SECTION_TOPIC_EXTRACTOR_PROMPT, SECTION_WISE_QUESTION_GENERATOR_PROMPT, PLAN_PROMPT, WRITER_PROMPT, PROJECT_PLAN_BODY_GENERATOR_PROMPT, PROJECT_PLAN_SCHEMA_GENERATOR_PROMPT
from .node_utils import save_state_for_testing, copy_figures, replace_wp_markers_preserving_format

'''IMPORT ALL TOOLS HERE AND CREATE LIST OF TOOLS TO BE PASSED TO THE AGENT.'''
from tools.script_executor import run_script
from tools.file_tree import get_file_tree
from tools.query_chromadb import query_chromadb
from tools.multimodal_query import NomicVisionQuerier
from schemas import State

# helper function to load the config.py file dynamically
def load_config_file() -> ModuleType:
    CURRENT_FILE = Path(__file__).resolve()
    project_root = CURRENT_FILE.parent.parent.parent.parent
    CONFIG_PATH = project_root / "config.py"
    spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    return config

# helper function to clean the JSON response from the LLM to ensure it's valid.
def clean_json_response(response: str) -> str:
    """
    Cleans the JSON response from the LLM to ensure it's valid.
    Handles complex JSON structures with proper error handling.
    """
    # First, strip whitespace
    json_str = response.strip()
    
    # Remove markdown code block formatting if present
    if json_str.startswith('```'):
        # Handle multiple variants of code block identifiers
        json_str = json_str.split('\n', 1)[-1]  # Remove first line with ```json or similar
        json_str = json_str.rstrip('`').strip()  # Remove trailing backticks
        
        # In case there are trailing backticks on their own line
        if json_str.endswith('```'):
            json_str = json_str[:-3].strip()
    
    # Remove invalid control characters (ASCII < 32 except tabs, newlines, carriage returns)
    clean_str = ''
    for ch in json_str:
        if ord(ch) >= 32 or ch in '\n\r\t':
            clean_str += ch
    json_str = clean_str
    
    # Try to validate JSON structure
    try:
        # Parse and re-stringify to normalize the JSON format
        parsed_json = json.loads(json_str)
        return json.dumps(parsed_json)
    except json.JSONDecodeError as e:
        # If we can't parse it, do some additional cleaning
        print(f"Warning: JSON parsing failed: {e}")
        
        # Try to fix common issues with LLM-generated JSON
        # 1. Unescaped quotes within string values
        # 2. Trailing commas in arrays or objects
        # 3. Comments in JSON
        
        # Remove potential comments
        json_str = '\n'.join([line for line in json_str.split('\n') 
                             if not line.strip().startswith('//')])
        
        # Fix trailing commas in arrays and objects
        json_str = json_str.replace(',]', ']').replace(',}', '}')
        
        # Return the best-effort cleaned string
        return json_str

configfile = load_config_file()
load_dotenv(dotenv_path=configfile.ENV_PATH)
init()

'''LLM TO USE'''
model_id = "meta-llama/Llama-3.3-70B-Instruct"
# model_id = "Qwen/Qwen2.5-72B-Instruct"
# model_id = "Qwen/QwQ-32B"
# model_id = "mistralai/Mistral-7B-Instruct-v0.3"
model = HfApiModel(model_id=model_id)

empty_prompt = """ """

agent = ToolCallingAgent(
    model=model, 
    tools=[], 
    prompt_templates={"system_prompt": empty_prompt}
)

def prompt_parser(state: State) -> State:
    """
    Given a user prompt, this node parses the prompt to extract the project title and description based on the project title.
    """
    print(f"{Fore.YELLOW}################ PROMPT PARSER BEGIN #################")
    user_prompt = state["user_prompt"]
    
    try:
        combined_user_prompt = PROMPT_PARSER_PROMPT + "\n" + user_prompt
        print(f"PROMPT PARSER PROMPT\n: {combined_user_prompt}\n\n\n")
        # llm call.
        response = agent.provide_final_answer(combined_user_prompt, images=None)
        print(f"PROMPT PARSER RESPONSE\n: {response}\n\n\n")
        response_json = json.loads(response)
        
        # updating state before end-of-node logging
        state["project_title"] = response_json["project_title"]
        state["project_description"] = response_json["project_description"]

        save_state_for_testing(state, "prompt_parser")

        print(f"################ PROMPT PARSER END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error in prompt_parser: {e}")
        print(f"################ PROMPT PARSER END #################{Style.RESET_ALL}")
        raise

def abstract_questions_generator(state: State) -> State:
    """
    Given the project title and description, this node creates a list of questions that may help it understand the project better. The answers to these questions will then be used to create a project abstract.
    """
    print(f"{Fore.RED}################ ABSTRACT QUESTIONS GENERATOR BEGIN #################")
    project_title = state.get("project_title", "")
    project_description = state.get("project_description", "")

    user_prompt = f"""
    Project Title: {project_title}
    Project Description: {project_description}
    """
    combined_prompt = ABSTRACT_QUESTIONS_GENERATOR_PROMPT + user_prompt
    print(f"ABSTRACT QUESTIONS GENERATOR PROMPT\n: {combined_prompt}\n\n\n")

    try:
        response = agent.provide_final_answer(combined_prompt, images=None)
        print(f"ABSTRACT QUESTIONS GENERATOR RESPONSE\n: {response}\n\n\n")
        response_json = json.loads(response)
        
        # Update state before end-of-node logging
        state["abstract_questions"] = response_json["abstract_questions"]

        save_state_for_testing(state, "abstract_questions_generator")

        print(f"################ ABSTRACT QUESTIONS GENERATOR END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error in abstract_questions_generator: {e}")
        print(f"################ ABSTRACT QUESTIONS GENERATOR END #################{Style.RESET_ALL}")
        raise

def abstract_answers_generator(state: State) -> State:
    """
    Given the list of questions, this node creates answers to the questions generated by the abstract_questions_generator node.
    """
    print(f"{Fore.BLUE}################ ABSTRACT ANSWERS GENERATOR BEGIN #################")
    
    configfile = load_config_file()
    current_project_id = configfile.get_current_project_id()
    updated_paths = configfile.update_project_paths(current_project_id)
    
    abstract_questions = state["abstract_questions"]

    try:
        # Use the research tools to actually query the database
        qa_pairs = {}
        for question in abstract_questions:
            result = query_chromadb(
                str(updated_paths['vector_db_paths']['data_db']),  # Use path from config
                updated_paths['model_settings']['SENTENCE_TRANSFORMER'],  # Use model setting from config
                question
            )
            # refactoring answer documents into one cohesive answer
            answer = agent.provide_final_answer(f"Frame the following texts into one cohesive answer: {result}. The question was: {question}", images=None)
            answer_text = answer.to_string() if hasattr(answer, 'to_string') else str(answer)
            qa_pairs[question] = answer_text

        # Now use the LLM to generate an abstract based on the retrieved answers
        user_prompt = f"""
        Project Title: {state["project_title"]}
        Project Description: {state["project_description"]}

        Here's the list of question-answer pairs:
        {qa_pairs}
        """
        combined_prompt = str(ABSTRACT_ANSWERS_GENERATOR_PROMPT) + "\n" + str(user_prompt)
        print(f"ABSTRACT ANSWERS GENERATOR PROMPT\n: {combined_prompt}\n\n\n")
        response = agent.provide_final_answer(combined_prompt, images=None)
        print(f"ABSTRACT ANSWERS GENERATOR RESPONSE\n: {response}\n\n\n")
        response_json = json.loads(response)
        abstract_text = response_json["abstract_text"]

        # Updating state before end-of-node logging
        state["abstract_text"] = abstract_text
        state["abstract_qa_pairs"] = qa_pairs

        save_state_for_testing(state, "abstract_answers_generator")

        print(f"################ ABSTRACT ANSWERS GENERATOR END #################{Style.RESET_ALL}")

        return state

    except Exception as e:
        print(f"Error occurred: {e}")
        print(f"################ ABSTRACT ANSWERS GENERATOR END #################{Style.RESET_ALL}")
        raise

def section_topic_extractor(state: State) -> State:
    """
    This node extracts the topics for each section of the project from the template pdf given by the user.
    """
    print(f"{Fore.CYAN}################ SECTION TOPIC EXTRACTOR BEGIN #################")
    
    configfile = load_config_file()
    current_project_id = configfile.get_current_project_id()
    updated_paths = configfile.update_project_paths(current_project_id)

    try:
        result = query_chromadb(
            str(updated_paths['vector_db_paths']['template_db']),  # Use path from config
            updated_paths['model_settings']['SENTENCE_TRANSFORMER'],  # Use model setting from config
            "Document section titles or topics or headings."
        )
        # Format the result list into a single string
        formatted_result = "\n".join(result) if isinstance(result, list) else str(result)
        # Combine the prompt and formatted result
        combined_prompt = f"{SECTION_TOPIC_EXTRACTOR_PROMPT}\n\nContext:\n{formatted_result}"
        print(f"SECTION TOPIC EXTRACTOR PROMPT\n: {combined_prompt}\n\n\n")
        
        response = agent.provide_final_answer(combined_prompt, images=None)
        print(f"SECTION TOPIC EXTRACTOR RESPONSE\n: {response}\n\n\n")
        response_json = json.loads(response)
        section_topics_list = response_json["section_topics"]

        # Updating state before end-of-node logging
        state["section_topics_corpus"] = result
        state["section_topics"] = section_topics_list

        save_state_for_testing(state, "section_topic_extractor")

        print(f"################ SECTION TOPIC EXTRACTOR END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error occurred: {e}")
        print(f"################ SECTION TOPIC EXTRACTOR END #################{Style.RESET_ALL}")
        raise

def plan_node(state: State) -> State:
    print(f"{Fore.LIGHTYELLOW_EX}################ PLAN NODE BEGIN #################")
    
    try:
        # Construct prompt with project info
        user_prompt = f"""
        Project Title: {state["project_title"]}
        Project Description: {state["project_description"]}
        Abstract: {state["abstract_text"]}
        List of Section Titles: {state["section_topics"]}
        """
        combined_prompt = PLAN_PROMPT + "\n" + user_prompt
        print(f"PLAN NODE PROMPT\n: {combined_prompt}\n\n\n")

        # Get response from agent
        response = agent.provide_final_answer(combined_prompt, images=None)
        print(f"PLAN NODE RESPONSE\n: {response}\n\n\n")
        json_str = clean_json_response(response)
        
        plan_dict = json.loads(json_str)
        
        state["plan"] = plan_dict
        save_state_for_testing(state, "plan")
        return state
            
    except Exception as e:
        print(f"Error in plan_node: {e}")
        raise

def section_wise_question_generator(state: State) -> State:
    """
    Given the list of sections, this node creates a list of questions for each section.
    """
    print(f"{Fore.MAGENTA}################ SECTION WISE QUESTION GENERATOR BEGIN #################")

    combined_prompt = f"""{SECTION_WISE_QUESTION_GENERATOR_PROMPT}
        Project Information:
        - Title: {state["project_title"]}
        - Description: {state["project_description"]}
        - Abstract: {state["abstract_text"]}
        - Plan for entire research paper: {state["plan"]}
    """
    print(f"SECTION WISE QUESTION GENERATOR PROMPT\n: {combined_prompt}\n\n\n")
    try:
        # Get response from agent
        response = agent.provide_final_answer(combined_prompt, images=None)
        print(f"SECTION WISE QUESTION GENERATOR RESPONSE\n: {response}\n\n\n")
        json_str = clean_json_response(response)
        
        # Parse and validate JSON response
        try:
            section_wise_questions = json.loads(json_str)
            
            # Validate the structure: should be dict[str, list[str]]
            if not isinstance(section_wise_questions, dict):
                raise ValueError("Response must be a dictionary")
            
            for section, questions in section_wise_questions.items():
                if not isinstance(questions, list):
                    raise ValueError(f"Questions must be a list for section {section}")
                if not all(isinstance(q, str) for q in questions):
                    raise ValueError(f"All questions must be strings in section {section}")

            # Update state      
            state["section_questions"] = section_wise_questions
            
        except json.JSONDecodeError as je:
            print(f"JSON parsing error: {je}")
            raise
            
        # Save state and return
        save_state_for_testing(state, "section_wise_question_generator")
        print(f"################ SECTION WISE QUESTION GENERATOR END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error occurred: {e}")
        print(f"################ SECTION WISE QUESTION GENERATOR END #################{Style.RESET_ALL}")
        raise

def section_wise_answers_generator(state: State) -> State:
    """
    Generates answers for section-wise questions using the multimodal_vectordb_query tool.
    Integrates results into the 'section_answers' schema.
    """
    print(f"{Fore.GREEN}################ SECTION WISE ANSWERS GENERATOR BEGIN #################")
    
    # Dynamically load config
    configfile = load_config_file()
    current_project_id = configfile.get_current_project_id()
    updated_paths = configfile.update_project_paths(current_project_id)
    
    section_questions = state.get("section_questions")
    if not section_questions:
        error_msg = "No section questions found in state. Previous node may have failed."
        print(f"Error: {error_msg}")

    try:
        section_answers = {}

        # Define the output file path
        output_path = updated_paths['nodewise_output'] / "section_wise_answers_generator_logging.txt"

        with output_path.open("w", encoding="utf-8") as file:
            # Iterate over each section and its questions
            for section, questions in section_questions.items():
                file.write(f"\nProcessing section: {section}\n")
                section_answers[section] = []
                
                for question in questions:
                    answer_list = []
                    file.write(f"\nQuerying for question: \n{question}\n")
                    
                    # Use the multimodal_vectordb_query tool with correct parameters
                    results = query_chromadb(
                        str(updated_paths['vector_db_paths']['data_db']),
                        updated_paths['model_settings']['SENTENCE_TRANSFORMER'],
                        question
                    )
                    
                    file.write(f"Query results: {results}\n")
                    
                    # refactoring answer documents into one cohesive answer
                    answer = agent.provide_final_answer(f"Frame the following texts into one cohesive answer: {results}. The question was: {question}", images=None)
                    answer_text = answer.to_string() if hasattr(answer, 'to_string') else str(answer)
                    answer_list.append(answer_text)

                section_answers[section] = answer_list
                
                file.write(f"Completed answers for section: {section}\n")
                file.write(f"Number of answers: {len(section_answers[section])}\n")

            # end of node logging
            state["section_answers"] = section_answers

        save_state_for_testing(state, "section_wise_answers_generator")

        print(f"################ SECTION WISE ANSWERS GENERATOR END #################{Style.RESET_ALL}")
        return state

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        print(f"################ SECTION WISE ANSWERS GENERATOR END #################{Style.RESET_ALL}")
        raise

def generation_node(state: State) -> State:
    print(f"{Fore.LIGHTYELLOW_EX}################ GENERATION NODE BEGIN #################")
    
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
            print(f"GENERATION NODE PROMPT\n: {combined_prompt}\n\n\n")
            # Get response from agent
            response = agent.provide_final_answer(combined_prompt, images=None)
            print(f"Successfully generated content for {section_title}")
            print(f"GENERATION NODE RESPONSE\n: {response}\n\n\n")

            document_so_far += response
            generated_sections[section_title] = response
        
        state["generated_sections"] = generated_sections
        save_state_for_testing(state, "generation")
        
        print(f"{Fore.LIGHTYELLOW_EX}################ GENERATION NODE END #################{Style.RESET_ALL}")
        return state
            
    except Exception as e:
        print(f"Error in generation_node: {e}")
        print(f"{Fore.LIGHTYELLOW_EX}################ GENERATION NODE END #################{Style.RESET_ALL}")
        raise

def project_plan_heading_node(state: State) -> State:
    print(f"{Fore.LIGHTGREEN_EX}################ PROJECT PLAN HEADING NODE BEGIN #################")
    generated_sections = state["generated_sections"]
    # logic to decide where to add the Project Plan heading.
    project_plan_heading_prompt = f"""
    You are an expert research proposal writer. You have this list of project sections: {generated_sections.keys()}, the content for which already has been written on the document.

    This document also needs a Project Plan that will delve into how to approach a solution to the problem statement the document has described so far. You need to decide which of the existing sections would be most appropriate to add the Project Plan content into.

    Given the list of sections, return the section_name where you think the 'Project Plan' content should appear.

    Your output must be a JSON object with the following key:
    - section_name: The name of the section to add the project plan heading at.

    example:
    {{
        "section_name": "Methodology",
    }}

    Your output must be ONLY a JSON object, and nothing else. Ensure that output JSON is formatted correctly without any additional text or formatting like ```json or ```.

    Guidelines for deciding the position of the Project Plan content:
    - The Project Plan content must be added at the later stages of the document, when the problem statement has been described completely.
    - The Project Plan content CANNOT appear in the introduction, or the conclusion and bibliography sections.
    - The Project Plan content must be added at a position where it logically fits in the document.
    
    """
    
    print(f"PROJECT PLAN HEADING NODE PROMPT\n: {project_plan_heading_prompt}\n\n\n")
    response = agent.provide_final_answer(project_plan_heading_prompt, images=None)
    print(f"PROJECT PLAN HEADING NODE RESPONSE\n: {response}\n\n\n")
    response_json = json.loads(response)
    project_plan_section_name = response_json["section_name"]
    
    state["project_plan_section_name"] = project_plan_section_name
    save_state_for_testing(state, "project_plan_heading_node")

    print(f"{Fore.LIGHTGREEN_EX}################ PROJECT PLAN HEADING NODE END #################{Style.RESET_ALL}")
    return state

def project_plan_body_generator(state: State) -> State:
    print(f"{Fore.LIGHTRED_EX}################ PROJECT PLAN BODY GENERATOR NODE BEGIN #################")
    
    # Construct prompt
    combined_prompt = str(PROJECT_PLAN_BODY_GENERATOR_PROMPT) + "\n" + str(state["generated_sections"])
    print(f"PROJECT PLAN BODY GENERATOR PROMPT\n: {combined_prompt}\n\n\n")
    project_plan_section_content = agent.provide_final_answer(combined_prompt, images=None)
    print(f"PROJECT PLAN BODY GENERATOR RESPONSE\n: {project_plan_section_content}\n\n\n")

    # Find the appropriate section to add the project plan content
    target_section_name = state["project_plan_section_name"]
    generated_sections = state["generated_sections"]
    target_section_lower = target_section_name.lower().strip()
    for section_name in generated_sections.keys():
        section_lower = section_name.lower().strip()
        # Perfect match
        if section_lower == target_section_lower:
            generated_sections[section_name] = project_plan_section_content
            break

    save_state_for_testing(state, "project_plan_body_generator")

    print(f"{Fore.LIGHTRED_EX}################ PROJECT PLAN BODY GENERATOR NODE END #################{Style.RESET_ALL}")
    return state

def project_plan_schema_generator(state: State) -> State:
    print(f"{Fore.LIGHTMAGENTA_EX}################ PROJECT PLAN SCHEMA GENERATOR NODE BEGIN #################")
    # count the number of work package markers in the project plan.
    wp_count = state['generated_sections'][state['project_plan_section_name']].count('<WP')

    # create the wp_list list of input dicts to work packages.
    # once that is done, create context for each of the work packages.
    combined_prompt = str(PROJECT_PLAN_SCHEMA_GENERATOR_PROMPT.format(wp_count=wp_count)) + "\n\n" + state['generated_sections'][state['project_plan_section_name']]

    print("PROJECT_PLAN_SCHEMA_GENERATOR_PROMPT\n: ", combined_prompt)
    response = agent.provide_final_answer(combined_prompt, images=None)
    print("PROJECT_PLAN_SCHEMA_GENERATOR RESPONSE\n: ", response)
    response_json = json.loads(response)
    row_params_list = response_json['row_params_list']
    state["row_params_list"] = row_params_list

    save_state_for_testing(state, "project_plan_schema_generator_node")

    print(f"{Fore.LIGHTMAGENTA_EX}################ PROJECT PLAN SCHEMA GENERATOR NODE END #################{Style.RESET_ALL}")
    return state

def formatting_node(state: State) -> State:
    print(f"{Fore.LIGHTYELLOW_EX}################ FORMATTING NODE BEGIN #################")
    
    # Dynamically load config and get paths
    configfile = load_config_file()
    current_project_id = configfile.get_current_project_id()
    updated_paths = configfile.update_project_paths(current_project_id)
    
    base_output_path = updated_paths['workflow1_output']
    output_docx_path = base_output_path / "output.docx"
    
    # Load the existing document if it exists, otherwise create a new one
    if output_docx_path.exists():
        print(f"Loading existing template document from {output_docx_path}")
        doc = Document(output_docx_path)
        # No need to remove content as the template is already stripped of content
    else:
        print(f"No existing document found at {output_docx_path}, creating a new document")
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

    # Save the document to the same path
    doc.save(output_docx_path)
    print(f"Word document updated at: {output_docx_path}")

    # Create a temporary file path
    temp_output_path = output_docx_path.parent / "temp_output.docx"

    # Use the temporary file as output
    replace_wp_markers_preserving_format(output_docx_path, temp_output_path, state["row_params_list"])

    # Replace the original file with the temporary file
    shutil.move(temp_output_path, output_docx_path)
    print(f"Saved rendered document to {output_docx_path}")

    # Create base64 string of output.docx
    with open(output_docx_path, "rb") as file:
        encoded_docx = base64.b64encode(file.read()).decode('utf-8')

    # Update project state.json with sections and encoded docx
    state_json_path = updated_paths['project_root'] / "state.json"
    if state_json_path.exists():
        with open(state_json_path, 'r') as f:
            project_state = json.load(f)
        
        # Update state with sections and encoded docx
        project_state["sections"] = list(generated_sections.keys())
        project_state["output_docx_base64"] = encoded_docx
        
        # Save updated state
        with open(state_json_path, 'w') as f:
            json.dump(project_state, f, indent=4)

    save_state_for_testing(state, "formatting_node")

    print(f"################ FORMATTING NODE END #################{Style.RESET_ALL}")
    return state






