import os
import operator
from typing import Annotated, List, Optional, TypedDict
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# Use relative imports if possible, or assume src is in path
try:
    from config import (
        DEFAULT_NEO4J_URI, DEFAULT_NEO4J_USERNAME, DEFAULT_NEO4J_PASSWORD,
        LLM_PROVIDER, DEFAULT_OPENAI_MODEL, DEFAULT_GEMINI_MODEL, DEFAULT_GROQ_MODEL,
        DEFAULT_OLLAMA_MODEL
    )
    from vector_query import query_vector_store
except ImportError:
    from src.config import (
        DEFAULT_NEO4J_URI, DEFAULT_NEO4J_USERNAME, DEFAULT_NEO4J_PASSWORD,
        LLM_PROVIDER, DEFAULT_OPENAI_MODEL, DEFAULT_GEMINI_MODEL, DEFAULT_GROQ_MODEL,
        DEFAULT_OLLAMA_MODEL
    )
    from src.vector_query import query_vector_store

# Load environment variables
load_dotenv()

class State(TypedDict):
    query: str
    route: Optional[str]
    context: Annotated[List[str], operator.add]
    answer: Optional[str]

# LLM for routing and synthesis
provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()

if provider == "gemini":
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("GOOGLE_MODEL", DEFAULT_GEMINI_MODEL),
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
elif provider == "groq":
    llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL),
        temperature=0
    )
elif provider == "ollama":
    llm = ChatOllama(
        model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=0
    )
else: # default to openai
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        temperature=0
    )

# Initialize Neo4j Graph
graph = Neo4jGraph(
    url=os.getenv("NEO4J_URI", DEFAULT_NEO4J_URI),
    username=os.getenv("NEO4J_USERNAME", DEFAULT_NEO4J_USERNAME),
    password=os.getenv("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD)
)

import re

# Cypher generation prompt with extremely rigid schema for small models
CYPHER_GENERATION_TEMPLATE = """Task: Generate a Cypher statement to query a Neo4j graph database.

Rules:
1. ONLY return the Cypher query. NO preamble.
2. DO NOT use curly braces {{}} for property filtering.
3. ALWAYS use the WHERE clause with the =~ operator for name searches.
4. Correct Pattern: MATCH (p:Person) WHERE p.name =~ '(?i)Emma Chen' ...

Schema:
{schema}

Example:
Question: How is Emma Chen related to the playback service?
Cypher: MATCH (p:Person)-[*1..3]-(s:Service) WHERE p.name =~ '(?i)Emma Chen' AND s.name =~ '(?i)playback.*' RETURN p.name, s.name, labels(s)

The question is:
{question}"""

def clean_cypher(text: str) -> str:
    """Strip preamble, postamble, and markdown from Cypher string."""
    # Remove markdown backticks
    text = text.replace('```cypher', '').replace('```', '')
    
    # Find the actual MATCH or RETURN part
    match = re.search(r'(MATCH|RETURN|WITH)\s+.*', text, re.IGNORECASE | re.DOTALL)
    if match:
        text = match.group(0)
    
    # Remove everything after the last semicolon or RETURN statement
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        if any(keyword in line.upper() for keyword in ['MATCH', 'WHERE', 'RETURN', 'WITH', 'UNWIND', 'LIMIT', 'SKIP', 'ORDER BY']):
            cleaned_lines.append(line)
        elif not cleaned_lines: continue
        else: break
            
    return '\n'.join(cleaned_lines).strip()

def router(state: State) -> dict:
    """Decide whether to use vector, graph, or compare."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert router. You decide whether a query should be answered using a Vector Store, a Knowledge Graph, or both.\n"
                   "Rules:\n"
                   "1. Use 'vector' for descriptive, general knowledge, or 'what is' questions that don't imply complex relationships.\n"
                   "2. Use 'graph' for questions about relationships, paths, connections, or 'how is X related to Y'.\n"
                   "3. Use 'compare' if the query involves both or requires a comprehensive answer from both sources.\n"
                   "Respond with ONLY the word 'vector', 'graph', or 'compare'."),
        ("human", "{query}")
    ])
    chain = prompt | llm
    response = chain.invoke({"query": state["query"]})
    route = response.content.strip().lower()
    
    # Validation
    if "compare" in route:
        route = "compare"
    elif "graph" in route:
        route = "graph"
    else:
        route = "vector"
        
    return {"route": route}

def vector_node(state: State) -> dict:
    """Query the vector store."""
    results = query_vector_store(state["query"])
    context = [m["document"] for m in results["matches"]]
    return {"context": context}

def graph_node(state: State) -> dict:
    """Query the knowledge graph manually with cleaning."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Neo4j expert. Generate a simple, valid Cypher query. NO text other than the query."),
        ("human", CYPHER_GENERATION_TEMPLATE)
    ])
    chain = prompt | llm
    
    try:
        # 1. Generate
        schema = graph.get_schema
        raw_cypher = chain.invoke({"question": state["query"], "schema": schema}).content
        
        # 2. Clean
        cypher = clean_cypher(raw_cypher)
        print(f"--- EXECUTING CYPHER ---\n{cypher}\n-----------------------")
        
        # 3. Execute
        results = graph.query(cypher)
        
        if not results:
            graph_answer = "No matching relationships found in the graph."
        else:
            graph_answer = f"Graph results found: {str(results)}"
            
    except Exception as e:
        graph_answer = f"Error querying graph. Check logs for details."
        print(f"DEBUG Graph Error: {str(e)}")
    
    return {"context": [f"Graph Analysis: {graph_answer}"]}

def synthesizer_node(state: State) -> dict:
    """Generate final grounded answer with citations."""
    full_context = "\n\n".join(state["context"])
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Answer the user query using ONLY the provided context. "
                   "If the context doesn't contain the answer, say you don't know. "
                   "IMPORTANT: Distinguish between 'Vector Store' context and 'Graph Analysis' context. "
                   "Cite your sources (e.g., 'According to the knowledge graph...', 'The vector documentation states...') "
                   "Provide a concise and accurate answer based on the retrieved information."),
        ("human", "Context: {context}\n\nQuery: {query}\n\nAnswer:")
    ])
    chain = prompt | llm
    response = chain.invoke({"query": state["query"], "context": full_context})
    return {"answer": response.content}

# Build the graph
workflow = StateGraph(State)

workflow.add_node("router", router)
workflow.add_node("vector_node", vector_node)
workflow.add_node("graph_node", graph_node)
workflow.add_node("synthesizer_node", synthesizer_node)

workflow.set_entry_point("router")

def route_decision(state: State):
    if state["route"] == "vector":
        return "vector_node"
    elif state["route"] == "graph":
        return "graph_node"
    else: # compare
        return "vector_node"

workflow.add_conditional_edges(
    "router",
    route_decision,
    {
        "vector_node": "vector_node",
        "graph_node": "graph_node"
    }
)

def after_vector_decision(state: State):
    if state["route"] == "compare":
        return "graph_node"
    return "synthesizer_node"

workflow.add_conditional_edges(
    "vector_node",
    after_vector_decision,
    {
        "graph_node": "graph_node",
        "synthesizer_node": "synthesizer_node"
    }
)

workflow.add_edge("graph_node", "synthesizer_node")
workflow.add_edge("synthesizer_node", END)

# Compile
app = workflow.compile()

def run_hybrid_rag(query: str):
    inputs = {"query": query, "context": []}
    
    final_answer = None
    route_taken = None
    
    for output in app.stream(inputs):
        for key, value in output.items():
            if "route" in value:
                route_taken = value["route"]
            if "answer" in value:
                final_answer = value["answer"]
    
    return {
        "answer": final_answer,
        "route": route_taken
    }

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "Who works on the audit project?"
    
    print(f"--- Querying Hybrid RAG: {query} ---")
    
    inputs = {"query": query, "context": []}
    for output in app.stream(inputs):
        for key, value in output.items():
            print(f"\n[Node: {key}]")
            if "route" in value:
                print(f"Decision: {value['route']}")
            if "answer" in value:
                print(f"Final Answer: {value['answer']}")
    print("\n--- Done ---")
