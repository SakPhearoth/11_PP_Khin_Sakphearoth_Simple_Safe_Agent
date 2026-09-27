# Cafe Shop Management Agent

A small safe agent for managing a cafe shop.

Customers can search products, check stock, place orders, and reserve tables. Admins can also update product stock.

The project demonstrates a tool-using agent with an application-level safety layer that controls which tool calls are allowed to execute.

---

## Project Overview

The agent receives a user's request and decides what action is needed. When a tool is required, the application validates and controls the requested tool call before allowing it to execute.

**Core flow:**

```text
User → Agent/LLM → Tool Call → Harness → Tool → PostgreSQL → Tool Result → Agent → Final Answer
```

The LLM proposes actions, but the application Harness decides whether the requested action is allowed to execute.

The project uses LangGraph for the agent loop, Pydantic for input schemas, and PostgreSQL for storing products, orders, and reservations.

---

## Available Tools

| Tool | Description |
|---|---|
| `search_products_tool` | Search cafe products by category or product name. |
| `check_stock_tool` | Check the current stock of a product. |
| `place_order_tool` | Place a customer order and decrease product stock. |
| `reserve_table_tool` | Reserve a table for a specified date, time, and number of people. |
| `update_stock_tool` | Update the stock quantity of a product. Admin only. |

---

## Agent Loop

The agent follows a **decision → action → observation → next decision** loop.

### Example Request

> I want 2 latte.

The workflow can be:

1. **Decision** — The agent determines that it needs to find the requested product.
2. **Action** — Calls `search_products_tool`.
3. **Observation** — Receives the Latte product information and product ID.
4. **Decision** — Determines that stock needs to be checked.
5. **Action** — Calls `check_stock_tool`.
6. **Observation** — Receives the current stock.
7. **Decision** — Determines that the order can be placed.
8. **Action** — Calls `place_order_tool`.
9. **Observation** — Receives the order result.
10. **Final Answer** — The agent returns the order confirmation to the customer.

The Harness is placed between the agent's tool call and the actual tool execution:

```text
User
↓
LangGraph Agent
↓
Tool Call
↓
Harness
├── Permission Check
├── Schema Validation
├── Business Validation
└── Tool-Call Limit
↓
Tool
↓
PostgreSQL
↓
Tool Result
↓
Agent
↺
```

---

## Permission Rule

The application enforces permissions in `harness.py`, rather than relying only on the LLM prompt.

| Tool | Customer | Admin |
|---|:---:|:---:|
| `search_products_tool` | Yes | Yes |
| `check_stock_tool` | Yes | Yes |
| `place_order_tool` | Yes | No |
| `reserve_table_tool` | Yes | No |
| `update_stock_tool` | No | Yes |

For example, if a customer requests a stock update, the Harness rejects the tool call with a `PERMISSION_DENIED` error before the stock update function can modify the database.

---

## Safety

The application includes several safety controls:

- Pydantic schemas validate tool arguments.
- The Harness enforces role-based permissions.
- Product IDs must be positive integers.
- Order quantities must be between 1 and 10.
- Reservation party size must be between 1 and 20.
- Stock quantity must be between 0 and 1000.
- Invalid requests return controlled error messages.
- Tool execution errors are handled without exposing raw exceptions.
- Maximum tool calls per run: **5**.
- Maximum agent iterations: **6**.
- Reservation capacity is limited to **20 people per date/time slot**.

These checks are implemented in application code, so the LLM cannot bypass them simply by generating a different tool call.

---

## Database

The project uses PostgreSQL with three tables:

- `products` — stores product information and stock.
- `orders` — stores customer orders.
- `reservations` — stores table reservations.

Run `init.sql` to create the tables and insert the initial products.

The cafe uses a fixed capacity of 20 people per date/time slot, so a separate tables table is not required.

---

## Project Structure

```text
cafe-agent/
├── README.md
├── main.py
├── agent.py
├── tools.py
├── schemas.py
├── harness.py
├── db.py
├── requirements.txt
├── .env.example
├── .gitignore
└── init.sql
```

### Main Files

| File | Purpose |
|---|---|
| `main.py` | Starts the application and handles user interaction. |
| `agent.py` | Defines the LangGraph agent and agent workflows. |
| `tools.py` | Contains the cafe tools and database operations. |
| `schemas.py` | Defines Pydantic input schemas. |
| `harness.py` | Enforces permissions, validation, and tool-call limits. |
| `db.py` | Handles PostgreSQL database connections. |
| `init.sql` | Creates the database tables and initial product data. |

---

## Example Run

### 1. Customer Places an Order

<img width="1047" height="515" alt="image" src="https://github.com/user-attachments/assets/d97d4fd2-e98c-44d0-aa70-abf489f4b7ab" />

---

## Setup

### 1. Create the PostgreSQL Database

Create a database named:

```text
cafe_agent
```

### 2. Initialize the Database

Run `init.sql` against the `cafe_agent` database.

### 3. Configure Environment Variables

Copy:

```text
.env.example
```

to:

```text
.env
```

Example:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cafe_agent
DB_USER=postgres
DB_PASSWORD=

LLM_MODEL=llama3.2:latest
OLLAMA_BASE_URL=http://localhost:11434
MAX_ITERATIONS=6
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Make Sure Ollama Is Running

Make sure the configured Ollama model is available.

For example:

```bash
ollama list
```

### 6. Run the Application

```bash
python main.py
```

Choose either:

```text
customer
```

or:

```text
admin
```

Then enter requests in the terminal.
