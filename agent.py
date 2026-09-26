import json
import os
import re
from typing import Any, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from harness import AgentHarness
from schemas import (
    CheckStockInput,
    PlaceOrderInput,
    ReserveTableInput,
    SearchProductsInput,
    UpdateStockInput,
)
from tools import (
    check_stock,
    place_order,
    reserve_table,
    search_products,
    update_stock,
)


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "llama3.2:latest")
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434",
)
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "6"))


# ============================================================
# LANGCHAIN TOOLS
# ============================================================

@tool(args_schema=SearchProductsInput)
def search_products_tool(
    category: str | None = None,
    product_name: str | None = None,
) -> dict:
    """Search cafe products by category or product name."""
    return search_products(category, product_name)


@tool(args_schema=CheckStockInput)
def check_stock_tool(product_id: int) -> dict:
    """Check current stock for a product."""
    return check_stock(product_id)


@tool(args_schema=PlaceOrderInput)
def place_order_tool(
    customer_name: str,
    product_id: int,
    quantity: int,
) -> dict:
    """Place an order for a customer."""
    return place_order(customer_name, product_id, quantity)


@tool(args_schema=ReserveTableInput)
def reserve_table_tool(
    customer_name: str,
    reservation_date,
    reservation_time,
    number_of_people: int,
) -> dict:
    """Reserve a table for a customer."""
    return reserve_table(
        customer_name,
        reservation_date,
        reservation_time,
        number_of_people,
    )


@tool(args_schema=UpdateStockInput)
def update_stock_tool(
    product_id: int,
    quantity: int,
) -> dict:
    """Set product stock quantity. Admin only."""
    return update_stock(product_id, quantity)


TOOLS = [
    search_products_tool,
    check_stock_tool,
    place_order_tool,
    reserve_table_tool,
    update_stock_tool,
]

TOOL_BY_NAME = {
    tool_.name: tool_
    for tool_ in TOOLS
}


# ============================================================
# MODEL
# ============================================================

model = ChatOllama(
    model=MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0,
)

bound_model = model.bind_tools(TOOLS)


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are a cafe shop management assistant.

Give concise, natural answers to the customer.

IMPORTANT:
- Never show internal tool calls.
- Never show JSON parameters.
- Never explain your internal reasoning.
- Never invent product information.
- Never invent product IDs.
- Never claim an action succeeded unless the tool result says it succeeded.
- Tool errors are real results and must be respected.

PRODUCTS:
- Use search_products when the customer asks about products.
- Search by product name when they mention a specific product.
- Search by category when they ask about a category.

ORDERS:
- For ordering, the application may handle the order workflow directly.
- If you receive a tool result, use the actual result.
- Never claim an order succeeded without a successful result.

RESERVATIONS:
- Use the reservation tool when the customer wants to reserve a table.
- Ask for missing required information.

ADMIN:
- Only admins can update stock.
- Never bypass a permission error.

FINAL RESPONSE:
- Return only the useful result.
- Keep the response concise.
- Do not mention tools, JSON, parameters, or reasoning.
"""


# ============================================================
# AGENT STATE
# ============================================================

class AgentState(TypedDict, total=False):
    messages: list[AnyMessage]
    iteration: int
    tool_call_count: int
    user_role: str
    pending_order: dict[str, Any]


# ============================================================
# NORMAL LANGGRAPH AGENT
# ============================================================

def agent_node(state: AgentState):
    response = bound_model.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            *state.get("messages", []),
        ]
    )

    iteration = state.get("iteration", 0) + 1

    return {
        "messages": state.get("messages", []) + [response],
        "iteration": iteration,
    }


def route_after_agent(state: AgentState):
    iteration = state.get("iteration", 0)

    if iteration >= MAX_ITERATIONS:
        return END

    last_message = state.get("messages", [])[-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "execute_tool"

    return END


def execute_tool_node(state: AgentState):
    messages = state.get("messages", [])
    last_message = messages[-1]

    if not isinstance(last_message, AIMessage):
        return state

    if not last_message.tool_calls:
        return state

    # We process one tool call at a time.
    tool_call = last_message.tool_calls[0]

    tool_name = tool_call["name"]
    tool_args = tool_call.get("args", {})

    tool = TOOL_BY_NAME.get(tool_name)

    if tool is None:
        result = {
            "status": "error",
            "error": "UNKNOWN_TOOL",
            "message": "The requested tool does not exist.",
        }

        tool_message = ToolMessage(
            content=json.dumps(result),
            tool_call_id=tool_call["id"],
        )

        return {
            "messages": messages + [tool_message],
        }

    harness = AgentHarness(
        role=state.get("user_role", "customer"),
    )

    result_json, new_count = harness.execute(
        tool=tool,
        tool_name=tool_name,
        args=tool_args,
        current_count=state.get("tool_call_count", 0),
    )

    tool_message = ToolMessage(
        content=result_json,
        tool_call_id=tool_call["id"],
    )

    return {
        "messages": messages + [tool_message],
        "tool_call_count": new_count,
    }


def build_graph():
    graph_builder = StateGraph(AgentState)

    graph_builder.add_node("agent", agent_node)
    graph_builder.add_node("execute_tool", execute_tool_node)

    graph_builder.add_edge(START, "agent")

    graph_builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "execute_tool": "execute_tool",
            END: END,
        },
    )

    graph_builder.add_edge(
        "execute_tool",
        "agent",
    )

    return graph_builder.compile()


# ============================================================
# SIMPLE ORDER DETECTION
# ============================================================

ORDER_PRODUCTS = (
    "americano",
    "latte",
    "cappuccino",
    "green tea",
    "black tea",
    "croissant",
    "croissants",
    "chocolate muffin",
    "chocolate muffins",
    "cheesecake",
    "cheesecakes",
    "brownie",
    "brownies",
)

PRODUCT_NORMALIZATION = {
    "croissants": "croissant",
    "chocolate muffins": "chocolate muffin",
    "cheesecakes": "cheesecake",
    "brownies": "brownie",
}


def extract_order_request(text: str):
    """
    Detect common natural order requests such as:

        order 3 americano
        I want 2 latte
        give me 3 americano
        I'd like to order 2 cups of latte
    """

    product_pattern = "|".join(
        re.escape(product)
        for product in ORDER_PRODUCTS
    )

    pattern = (
        rf"\b(?:"
        rf"order|"
        rf"want|"
        rf"buy|"
        rf"get|"
        rf"give\s+me|"
        rf"i['’]d\s+like(?:\s+to\s+order)?|"
        rf"i\s+would\s+like(?:\s+to\s+order)?"
        rf")\s+"
        rf"(\d+)\s+"
        rf"(?:cups?\s+of\s+)?"
        rf"({product_pattern})\b"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    quantity = int(match.group(1))
    product_name = match.group(2).lower()

    product_name = PRODUCT_NORMALIZATION.get(
        product_name,
        product_name,
    )

    return {
        "product_name": product_name,
        "quantity": quantity,
    }


def extract_customer_name(text: str):
    """
    Detect simple customer-name statements:

        My name is Khin
        name is Khin
    """

    pattern = r"\b(?:my\s+name\s+is|name\s+is)\s+([A-Za-z][A-Za-z'-]{0,98})"

    match = re.search(
        pattern,
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return match.group(1).strip()


# ============================================================
# CONTROLLED ORDER WORKFLOW
# ============================================================

def handle_order_workflow(
    order_info: dict[str, Any],
    customer_name: str | None,
    role: str,
):
    """
    Controlled application workflow:

        Search product
             ↓
        Check stock
             ↓
        Place order

    Every action goes through the Harness.
    """

    if role != "customer":
        return (
            "Only customers can place orders.",
            None,
        )

    harness = AgentHarness(role=role)

    # --------------------------------------------------------
    # 1. Search product
    # --------------------------------------------------------

    search_result_json, count = harness.execute(
        tool=search_products_tool,
        tool_name="search_products_tool",
        args={
            "product_name": order_info["product_name"],
        },
        current_count=0,
    )

    search_result = json.loads(search_result_json)

    if search_result.get("status") == "error":
        return (
            search_result.get(
                "message",
                "I couldn't find that product.",
            ),
            None,
        )

    products = search_result.get("products", [])

    if not products:
        return (
            f"Sorry, I couldn't find {order_info['product_name']}.",
            None,
        )

    product = products[0]

    product_id = product.get("id")
    product_name = product.get(
        "name",
        order_info["product_name"],
    )

    # --------------------------------------------------------
    # 2. Check stock
    # --------------------------------------------------------

    stock_result_json, count = harness.execute(
        tool=check_stock_tool,
        tool_name="check_stock_tool",
        args={
            "product_id": product_id,
        },
        current_count=count,
    )

    stock_result = json.loads(stock_result_json)

    if stock_result.get("status") == "error":
        return (
            stock_result.get(
                "message",
                "I couldn't check the stock.",
            ),
            None,
        )

    stock = stock_result.get("stock")

    if stock is None:
        return (
            "I couldn't determine the current stock.",
            None,
        )

    quantity = order_info["quantity"]

    if quantity <= 0:
        return (
            "The quantity must be greater than 0.",
            None,
        )

    if quantity > 10:
        return (
            "You can order a maximum of 10 items at once.",
            None,
        )

    if stock < quantity:
        return (
            f"Sorry, only {stock} {product_name} "
            f"{'is' if stock == 1 else 'are'} available.",
            None,
        )

    # --------------------------------------------------------
    # 3. Place order
    # --------------------------------------------------------

    order_result_json, count = harness.execute(
        tool=place_order_tool,
        tool_name="place_order_tool",
        args={
            "customer_name": customer_name or "Guest",
            "product_id": product_id,
            "quantity": quantity,
        },
        current_count=count,
    )

    order_result = json.loads(order_result_json)

    if order_result.get("status") != "success":
        return (
            order_result.get(
                "message",
                "I couldn't place the order.",
            ),
            None,
        )

    total_price = order_result.get("total_price")
    order_id = order_result.get("order_id")

    if total_price is not None:
        response = (
            f"Order #{order_id} confirmed: "
            f"{quantity} {product_name} "
            f"{'for ' + customer_name + '. ' if customer_name else ''}"
            f"Total: ${float(total_price):.2f}."
        )
    else:
        response = (
            f"Order #{order_id} confirmed: "
            f"{quantity} {product_name} "
            f"{'for ' + customer_name + '. ' if customer_name else ''}"
        )

    return response, None


# ============================================================
# RUN REQUEST
# ============================================================

def run_request(
    graph,
    user_input: str,
    role: str,
    previous_state: AgentState | None = None,
):
    role = role.lower()

    if previous_state is None:
        state: AgentState = {
            "messages": [
                HumanMessage(content=user_input)
            ],
            "iteration": 0,
            "tool_call_count": 0,
            "user_role": role,
        }
    else:
        state = {
            **previous_state,
            "messages": previous_state.get(
                "messages",
                [],
            ) + [
                HumanMessage(content=user_input)
            ],
            "iteration": 0,
            "tool_call_count": 0,
            "user_role": role,
        }

    # ========================================================
    # HANDLE PENDING ORDER
    # ========================================================

    pending_order = state.get("pending_order")

    if pending_order:
        customer_name = extract_customer_name(user_input)

        if customer_name:
            response, new_pending = handle_order_workflow(
                pending_order,
                customer_name,
                role,
            )

            state["pending_order"] = new_pending

            state["messages"] = state.get(
                "messages",
                [],
            ) + [
                AIMessage(content=response)
            ]

            return response, state

    # ========================================================
    # DETECT NEW ORDER
    # ========================================================

    order_info = extract_order_request(user_input)

    if order_info:
        customer_name = extract_customer_name(user_input)

        response, new_pending = handle_order_workflow(
            order_info,
            customer_name,
            role,
        )

        state["pending_order"] = new_pending

        state["messages"] = state.get(
            "messages",
            [],
        ) + [
            AIMessage(content=response)
        ]

        return response, state

    # ========================================================
    # NORMAL LANGGRAPH FLOW
    # ========================================================

    result = graph.invoke(state)

    messages = result.get("messages", [])

    if not messages:
        final_response = "No response."
    else:
        final_response = str(
            messages[-1].content
        )

    return final_response, result