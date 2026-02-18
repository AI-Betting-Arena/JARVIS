from langchain_google_genai import ChatGoogleGenerativeAI


def create_llm(model_name: str = "models/gemini-2.0-flash") -> ChatGoogleGenerativeAI:
    """Single entry point for LLM instantiation across all agents.

    Reads GOOGLE_API_KEY from the environment (loaded by the caller via dotenv).
    """
    return ChatGoogleGenerativeAI(model=model_name)
