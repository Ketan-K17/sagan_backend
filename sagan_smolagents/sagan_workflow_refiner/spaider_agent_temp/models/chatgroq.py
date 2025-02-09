from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

def BuildChatGroq(model: str, temperature: float):
    return ChatGroq(model=model, temperature=temperature)

def BuildChatOpenAI(model: str, temperature: float):
    return ChatOpenAI(model=model, temperature=temperature)
