from langgraph.graph import MessagesState
from dotenv import load_dotenv
from typing import List, Dict, Union, Optional
from pydantic import BaseModel, Field

load_dotenv()

class Task(BaseModel):
    title: str
    description: str

class Deliverable(BaseModel):
    title: str
    month: str

class Milestone(BaseModel):
    title: str
    month: str

class Researcher(BaseModel):
    name: str
    partner: str
    qualification: str
    months: str

class WorkPackageContext(BaseModel):
    wp_leader: str
    start_date: str
    end_date: str
    objective: str
    tasks: List[Task]
    interdependence: str
    deliverables: List[Deliverable]
    milestones: List[Milestone]
    researchers: List[Researcher]

class Contributor(BaseModel):
    name: str
    efforts: List[int]

class ContributorsTable(BaseModel):
    contributors: List[Contributor]

class State(MessagesState):
    user_prompt: str
    project_title: str
    project_description: str
    abstract_questions: List[str]
    abstract_qa_pairs: List[Dict[str, str]]
    section_topics_corpus: List[str]
    abstract_text: str
    section_topics: List[str]
    section_questions: Dict[str, List[str]]  # key = section_topic, value = list of questions.
    section_answers: Dict[str, List[Dict[str, Union[str, List[str]]]]]
    plan: Dict[str, List[str]]  # key = section_topic, value = list of steps.
    draft: str
    generated_sections: Dict[str, str] = Field(
        default_factory=dict,
        description="Dictionary of written content for each section. Keys are section titles, and values are self-contained written content."
    )
    work_packages_contexts: List[WorkPackageContext]
    contributors_table: ContributorsTable
