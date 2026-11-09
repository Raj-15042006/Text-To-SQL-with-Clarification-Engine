from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.modules.ambiguity import QueryAnalysis

class SQLGenerationResult(BaseModel):
    sql: str = Field(description="Executable PostgreSQL SQL query")
    explanation: str = Field(description="Explanation of how this query computes the requested answer")
    tables_used: List[str] = Field(default_factory=list, description="Tables referenced in the SQL")
    assumptions: List[str] = Field(default_factory=list, description="Any specific assumptions made")

class BaseLLMProvider(ABC):
    """
    Abstract interface for LLM providers (Gemini, OpenAI, Groq).
    Decouples LLM inference from core business logic.
    """

    @abstractmethod
    def analyze_query(
        self, 
        user_query: str, 
        schema_context: str, 
        history: Optional[List[Dict[str, str]]] = None
    ) -> QueryAnalysis:
        """
        Analyzes user query for intent, entity recognition, and ambiguity detection.
        """
        pass

    @abstractmethod
    def generate_sql(
        self, 
        resolved_query: str, 
        schema_context: str, 
        clarification_notes: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> SQLGenerationResult:
        """
        Generates PostgreSQL-compatible SQL grounded in the provided schema or formula calculations.
        """
        pass

    @abstractmethod
    def explain_results(
        self, 
        user_query: str, 
        sql: str, 
        columns: List[str], 
        sample_rows: List[Dict[str, Any]], 
        total_rows: int,
        relationships_context: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Produces an analytical, executive-grade summary of the query results and relational data paths.
        """
        pass
