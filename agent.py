import json
import os
from typing import Any, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from harness import AgentHarness, MAX_TOOL_CALLS
from schemas import CheckStockInput, PlaceOrderInput, ReserveTableInput, SearchProductsInput, UpdateStockInput
from tools import check_stock, place_order, reserve_table, search_products, update_stock

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "qwen3:8b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "6"))


@tool(args_schema=SearchProductsInput)
def search_products_tool(category: str) -> dict:
    """Search cafe products in one category: coffee, tea, pastry, or dessert."""
    return search_products(category)


@tool(args_schema=CheckStockInput)
def check_stock_tool(product_id: int) -> dict:
    """Check the current stock of a cafe product by ID."""
    return check_stock(product_id)


@tool(args_schema=PlaceOrderInput)
def place_order_tool(customer_name: str, product_id: int, quantity: int) -> dict:
    """Place an order for a customer after stock has been checked."""
    return place_order(customer_name, product_id, quantity)


@tool(args_schema=ReserveTableInput)
def reserve_table_tool(customer_name: str, reservation_date, reservation_time, number_of_people: int) -> dict:
    """Reserve cafe seating for a date, time, and party size."""
    return reserve_table(customer_name, reservation_date, reservation_time, number_of_people)


@tool(args_schema=UpdateStockInput)
def update_stock_tool(product_id: int, quantity: int) -> dict:
    """Set a product's stock quantity. Admin only."""
    return update_stock(product_id, quantity)


TOOLS = [search_products_tool, check_stock_tool, place_order_tool, reserve_table_tool, update_stock_tool]
TOOL_BY_NAME = {tool_.name: tool_ for tool_ in TOOLS}

model = ChatOllama(model=MODEL, base_url=OLLAMA_BASE_URL, temperature=0)
bound_model = model.bind_tools(TOOLS)

SYSTEM_PROMPT = """
You are a cafe shop management assistant inside a controlled application.

Rules:
- Use tools for live product, stock, order, and reservation information.
- Never invent product IDs, stock, prices, order IDs, or reservation IDs.
- After every tool result, inspect the result and decide whether another tool is needed.
- For an order, normally search for the product, check its stock, then place the order.
- If a tool returns an error, treat it as an observation. Do not claim success.
- Never try to bypass a permission error.
- Only admins may update stock.
- Stop when the user's goal is satisfied.
- Keep answers concise.
"""


class AgentState(TypedDict, total=False):
    messages: list[AnyMessage]
    iteration: int
    tool_call_count: int
    user_role: str


def agent_node(state: AgentState) -> dict[str, Any]:
    response = bound_model.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        *state.get("messages", []),
    ])
    iteration = state.get("iteration", 0) + 1
    return {"messages": [response], "iteration": iteration}


def route_after_agent(state: AgentState) -> str:
    if state.get("iteration", 0) >= MAX_ITERATIONS:
        return END
    last = state.get("messages", [])[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "execute_tool"
    return END


def execute_tool_node(state: AgentState) -> dict[str, Any]:
    last = state.get("messages", [])[-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {"messages": [ToolMessage(content=json.dumps({"status": "error", "error_code": "NO_TOOL_CALL"}), tool_call_id="missing")]}

    call = last.tool_calls[0]
    tool_name = call["name"]
    args = call.get("args", {})
    tool_call_id = call["id"]

    harness = AgentHarness(state.get("user_role", "customer"))
    tool = TOOL_BY_NAME.get(tool_name)
    if tool is None:
        result = json.dumps({"status": "error", "error_code": "TOOL_NOT_ALLOWED", "message": "Unknown tool."})
        new_count = state.get("tool_call_count", 0) + 1
    else:
        result, new_count = harness.execute(tool, tool_name, args, state.get("tool_call_count", 0))

    return {
        "messages": [ToolMessage(content=result, tool_call_id=tool_call_id)],
        "tool_call_count": new_count,
    }


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("execute_tool", execute_tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_edge("execute_tool", "agent")
    return graph.compile()


def run_request(graph, user_input: str, role: str) -> str:
    state: AgentState = {
        "messages": [HumanMessage(content=user_input)],
        "iteration": 0,
        "tool_call_count": 0,
        "user_role": role.lower(),
    }
    result = graph.invoke(state)
    messages = result.get("messages", [])
    final = messages[-1].content if messages else "No response."
    return str(final)
