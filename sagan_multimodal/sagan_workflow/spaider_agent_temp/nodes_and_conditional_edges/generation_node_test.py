from spaider_agent_temp.nodes_and_conditional_edges.node_utils import load_state_for_testing, print_state
from spaider_agent_temp.nodes_and_conditional_edges.nodes import generation_node

if __name__ == "__main__":
    # NOTE: load_state_for_testing("prompt_parser") for example will fetch you the state from AFTER the prompt_parser is done making changes to the state.
    init_state = load_state_for_testing("plan_node")
    # print(init_state)

    final_state = generation_node(init_state)
    print("\n\n\n\nHere's the state after GENERATION NODE\n\n\n\n")
    # print_state(final_state)