import os
import operator
from typing import Annotated, List, Optional, TypedDict
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# Use relative imports if possible, or assume src is in path
try:
    from config import DEFAULT_NEO4J_URI, DEFAULT_NEO4J_USERNAME, DEFAULT_NEO4J_PASSWORD
    from vector_query import query_vector_store
except ImportError:
    from src.config import DEFAULT_NEO4J_URI, DEFAULT_NEO4J_USERNAME, DEFAULT_NEO4J_PASSWORD
    from src.vector_query import query_vector_store

# Load environment variables
load_dotenv()

class State(TypedDict):
    query: str
    route: Optional[str]
    context: Annotated[List[str], operator.add]
    answer: Optional[str]

# LLM for routing and synthesis
# Ensure GROQ_API_KEY is in your .env
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

# Initialize Neo4j Graph
graph = Neo4jGraph(
    url=os.getenv("NEO4J_URI", DEFAULT_NEO4J_URI),
    username=os.getenv("NEO4J_USERNAME", DEFAULT_NEO4J_USERNAME),
    password=os.getenv("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD)
)

# Cypher QA Chain
cypher_chain = GraphCypherQAChain.from_llm(
    llm, graph=graph, verbose=True, allow_dangerous_requests=True
)

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
    """Query the knowledge graph."""
    try:
        res = cypher_chain.invoke({"query": state["query"]})
        graph_answer = res.get("result", "")
    except Exception as e:
        graph_answer = f"Error querying graph: {str(e)}"
    
    return {"context": [f"Graph Analysis: {graph_answer}"]}

def synthesizer_node(state: State) -> dict:
    """Generate final grounded answer."""
    full_context = "\n\n".join(state["context"])
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Answer the user query using ONLY the provided context. "
                   "If the context doesn't contain the answer, say you don't know. "
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
    
    result = None
    for output in app.stream(inputs):
        for key, value in output.items():
            if "answer" in value:
                result = value["answer"]
    return result

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
