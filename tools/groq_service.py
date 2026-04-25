from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

def load_groq(model='llama-3.3-70b-versatile', temperature=0.8):
    return ChatGroq(model=model, temperature=temperature)