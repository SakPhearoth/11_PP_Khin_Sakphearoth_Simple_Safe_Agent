import json
from typing import Any

MAX_TOOL_CALLS = 5

READ_TOOLS = {"search_products_tool", "check_stock_tool"}
CUSTOMER_TOOLS = READ_TOOLS | {"place_order_tool", "reserve_table_tool"}
ADMIN_TOOLS = READ_TOOLS | {"update_stock_tool"}
ALL_TOOLS = CUSTOMER_TOOLS | {"update_stock_tool"}


class AgentHarness:
    def __init__(self, role: str, max_tool_calls: int = MAX_TOOL_CALLS):
        self.role = role.lower()
        self.max_tool_calls = max_tool_calls

    def validate(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        if tool_name not in ALL_TOOLS:
            return self._error("TOOL_NOT_ALLOWED", f"Tool '{tool_name}' is not allowed.")

        allowed = CUSTOMER_TOOLS if self.role == "customer" else ADMIN_TOOLS if self.role == "admin" else set()
        if tool_name not in allowed:
            return self._error("PERMISSION_DENIED", f"Role '{self.role}' cannot use '{tool_name}'.")

        if tool_name in {"check_stock_tool", "place_order_tool", "update_stock_tool"}:
            if not isinstance(args.get("product_id"), int) or args["product_id"] <= 0:
                return self._error("INVALID_PRODUCT_ID", "product_id must be a positive integer.")

        if tool_name == "place_order_tool":
            quantity = args.get("quantity")
            if not isinstance(quantity, int) or not 1 <= quantity <= 10:
                return self._error("INVALID_QUANTITY", "quantity must be an integer from 1 to 10.")
            if not isinstance(args.get("customer_name"), str) or not args["customer_name"].strip():
                return self._error("INVALID_CUSTOMER_NAME", "customer_name is required.")

        if tool_name == "reserve_table_tool":
            if not isinstance(args.get("number_of_people"), int) or not 1 <= args["number_of_people"] <= 20:
                return self._error("INVALID_PARTY_SIZE", "number_of_people must be between 1 and 20.")
            if not isinstance(args.get("customer_name"), str) or not args["customer_name"].strip():
                return self._error("INVALID_CUSTOMER_NAME", "customer_name is required.")

        if tool_name == "update_stock_tool":
            quantity = args.get("quantity")
            if not isinstance(quantity, int) or not 0 <= quantity <= 1000:
                return self._error("INVALID_STOCK", "quantity must be an integer from 0 to 1000.")

        return None

    def execute(self, tool, tool_name: str, args: dict[str, Any], current_count: int):
        next_count = current_count + 1
        if next_count > self.max_tool_calls:
            result = self._error("TOOL_CALL_LIMIT", "Maximum tool calls reached for this run.")
            return json.dumps(result), next_count

        error = self.validate(tool_name, args)
        if error:
            return json.dumps(error), next_count

        try:
            result = tool.invoke(args)
        except Exception:
            result = self._error("TOOL_EXECUTION_FAILED", "Tool execution failed safely.")
        return json.dumps(result, ensure_ascii=False, default=str), next_count

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"status": "error", "error_code": code, "message": message}
