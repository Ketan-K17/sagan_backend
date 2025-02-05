from langgraph.graph import MessagesState
from dotenv import load_dotenv

load_dotenv()

class State(MessagesState):
    user_prompt: str
    # word_limit: int
    # character_limit: int
    section_text: str
    modified_section_text: str
    ai_message: str
    research_needed: bool
    section_title: str
    rough_draft_path: str # path to the .md file containing the draft from first workflow
    research_queries: list[str]
    context: list[str] # answers to the queries from the vector database
    user_approval: str # yes/no response after the formatter node is done.
    section_number: int # number corresponding to the section that is being worked on
  

