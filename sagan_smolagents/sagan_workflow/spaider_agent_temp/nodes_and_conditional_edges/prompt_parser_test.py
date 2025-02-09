from sagan_workflow.spaider_agent_temp.nodes_and_conditional_edges.node_utils import load_state_for_testing, print_state
from sagan_workflow.spaider_agent_temp.nodes_and_conditional_edges.nodes import prompt_parser
from sagan_workflow.spaider_agent_temp.prompts import PROMPT_PARSER_PROMPT
from sagan_workflow.spaider_agent_temp.schemas import State

from langchain_core.messages import SystemMessage

from smolagents import ToolCallingAgent, HfApiModel
# select model
model_id = "meta-llama/Llama-3.3-70B-Instruct"
model = HfApiModel(model_id=model_id)   
agent = ToolCallingAgent(model=model, tools=[])

def modified_prompt_parser(state: State) -> State:
    system_prompt = SystemMessage(PROMPT_PARSER_PROMPT)
    state["messages"].append(system_prompt)

    try:
        # response = llm.invoke(state["messages"])
        response = agent.run(state["messages"])

        if not response or not hasattr(response, 'content'):
            raise ValueError("Invalid response from LLM.")
        
        return response
        
        # llm_with_structured_output = llm.with_structured_output(PromptParserOutput)
        # structured_response = llm_with_structured_output.invoke(response.content)

        # if not hasattr(structured_response, 'project_title') or not hasattr(structured_response, 'project_description'):
        #     raise ValueError("Project title or description not found in the structured output.")

        # updating state before end-of-node logging
    #     state["messages"].append(response)
    #     state["project_title"] = structured_response.project_title
    #     state["project_description"] = structured_response.project_description

    #     # saving state in human readable format and machine readable format under outputpdf/nodewise_output
    #     save_state_for_testing(state, "prompt_parser")

    #     print(f"################ PROMPT PARSER END #################{Style.RESET_ALL}")
    #     return state

    except Exception as e:
        print(f"Error in prompt_parser: {e}")
        raise
    

if __name__ == "__main__":
    init_state = State(messages=[SystemMessage(PROMPT_PARSER_PROMPT)])
    response = modified_prompt_parser(init_state)
    # print_state(final_state)