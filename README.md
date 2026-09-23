# Cafe Shop Management Agent

A small safe agent for a cafe shop. Customers can search products, check stock, place orders, and reserve tables. Admins can also update stock.

## Project Overview

The project demonstrates a tool-using agent loop with application-level permission and safety controls.

Core flow:

User → Agent/LLM → Tool Call → Harness → Tool → PostgreSQL → Tool Result → Agent → Final Answer

The LLM proposes tool calls. The application harness decides whether the requested action is allowed to execute.

## Roles and Permissions

| Tool | Customer | Admin |
|---|---|---|
| search_products | Yes | Yes |
| check_stock | Yes | Yes |
| place_order | Yes | No |
| reserve_table | Yes | No |
| update_stock | No | Yes |

Permissions are enforced in `harness.py`, not only in the prompt.

## Available Tools

- `search_products(category)` — search coffee, tea, pastry, or dessert.
- `check_stock(product_id)` — check current inventory.
- `place_order(customer_name, product_id, quantity)` — place an order and decrease stock.
- `reserve_table(customer_name, reservation_date, reservation_time, number_of_people)` — reserve seating subject to the cafe capacity of 20 people per time slot.
- `update_stock(product_id, quantity)` — set product stock; admin only.

## Safety

- Pydantic input schemas validate tool arguments.
- `harness.py` enforces role permissions.
- Invalid IDs, quantities, party sizes, and categories are rejected.
- Tools return controlled error objects instead of exposing raw exceptions.
- Maximum tool calls per run: 5.
- Maximum agent iterations: 6.

## Agent Loop

Example request:

> I want 2 lattes.

Possible loop:

1. Agent calls `search_products(category="coffee")`.
2. Agent observes the latte product ID.
3. Agent calls `check_stock(product_id=2)`.
4. Agent observes the available stock.
5. Agent calls `place_order(...)`.
6. Agent observes the order result and gives the final answer.

## Permission Example

A customer may ask to update stock. The LLM can propose `update_stock_tool`, but the harness returns `PERMISSION_DENIED` before the database function executes.

## Database

Run `init.sql` in PostgreSQL to create:

- `products`
- `orders`
- `reservations`

The cafe capacity is fixed at 20 people per date/time slot, so no separate tables table is required.

## Setup

1. Create a PostgreSQL database named `cafe_agent`.
2. Run `init.sql` against that database.
3. Copy `.env.example` to `.env` and set the PostgreSQL password.
4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Make sure Ollama is running and the configured model is available.
6. Run:

```bash
python main.py
```

## Example Test Cases

Customer:

```text
I want 2 lattes.
```

Customer permission test:

```text
Increase the latte stock to 30.
```

Admin permission test:

```text
Set the latte stock to 30.
```

Reservation:

```text
My name is Dara. Reserve a table for 4 people tomorrow at 7 PM.
```
