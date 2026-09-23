from datetime import date, time
from db import get_connection

CAFE_MAX_CAPACITY = 20
VALID_CATEGORIES = {"coffee", "tea", "pastry", "dessert"}


def search_products(category: str) -> dict:
    category = category.strip().lower()
    if category not in VALID_CATEGORIES:
        return {"status": "error", "error_code": "INVALID_CATEGORY", "message": "Category must be coffee, tea, pastry, or dessert."}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, category, price, stock FROM products WHERE category = %s ORDER BY price ASC", (category,))
            rows = cur.fetchall()
        return {"status": "success", "products": [
            {"id": r[0], "name": r[1], "category": r[2], "price": float(r[3]), "stock": r[4]}
            for r in rows
        ]}
    finally:
        conn.close()


def check_stock(product_id: int) -> dict:
    if not isinstance(product_id, int) or product_id <= 0:
        return {"status": "error", "error_code": "INVALID_PRODUCT_ID", "message": "product_id must be a positive integer."}

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, stock FROM products WHERE id = %s", (product_id,))
            row = cur.fetchone()
        if row is None:
            return {"status": "error", "error_code": "PRODUCT_NOT_FOUND", "message": "Product not found."}
        return {"status": "success", "product_id": row[0], "product_name": row[1], "stock": row[2]}
    finally:
        conn.close()


def place_order(customer_name: str, product_id: int, quantity: int) -> dict:
    if not customer_name.strip():
        return {"status": "error", "error_code": "INVALID_CUSTOMER_NAME", "message": "Customer name is required."}
    if product_id <= 0:
        return {"status": "error", "error_code": "INVALID_PRODUCT_ID", "message": "product_id must be positive."}
    if quantity <= 0 or quantity > 10:
        return {"status": "error", "error_code": "INVALID_QUANTITY", "message": "quantity must be between 1 and 10."}

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, price, stock FROM products WHERE id = %s FOR UPDATE", (product_id,))
                row = cur.fetchone()
                if row is None:
                    return {"status": "error", "error_code": "PRODUCT_NOT_FOUND", "message": "Product not found."}
                _, name, price, stock = row
                if stock < quantity:
                    return {"status": "error", "error_code": "OUT_OF_STOCK", "message": "Not enough stock.", "available_stock": stock}
                total = float(price) * quantity
                cur.execute(
                    "INSERT INTO orders (customer_name, product_id, quantity, total_price) VALUES (%s, %s, %s, %s) RETURNING id",
                    (customer_name.strip(), product_id, quantity, total),
                )
                order_id = cur.fetchone()[0]
                cur.execute("UPDATE products SET stock = stock - %s WHERE id = %s", (quantity, product_id))
                return {"status": "success", "order_id": order_id, "product_name": name, "quantity": quantity, "total_price": total, "remaining_stock": stock - quantity}
    except Exception:
        conn.rollback()
        return {"status": "error", "error_code": "ORDER_FAILED", "message": "Order failed safely."}
    finally:
        conn.close()


def reserve_table(customer_name: str, reservation_date: date, reservation_time: time, number_of_people: int) -> dict:
    if not customer_name.strip():
        return {"status": "error", "error_code": "INVALID_CUSTOMER_NAME", "message": "Customer name is required."}
    if number_of_people <= 0 or number_of_people > CAFE_MAX_CAPACITY:
        return {"status": "error", "error_code": "INVALID_PARTY_SIZE", "message": f"Number of people must be between 1 and {CAFE_MAX_CAPACITY}."}

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(number_of_people), 0) FROM reservations WHERE reservation_date = %s AND reservation_time = %s AND status = 'confirmed' FOR UPDATE",
                    (reservation_date, reservation_time),
                )
                existing = int(cur.fetchone()[0])
                if existing + number_of_people > CAFE_MAX_CAPACITY:
                    return {"status": "error", "error_code": "TABLE_UNAVAILABLE", "message": "Not enough seating capacity for that time.", "capacity": CAFE_MAX_CAPACITY, "already_reserved": existing, "requested": number_of_people}
                cur.execute(
                    "INSERT INTO reservations (customer_name, reservation_date, reservation_time, number_of_people) VALUES (%s, %s, %s, %s) RETURNING id",
                    (customer_name.strip(), reservation_date, reservation_time, number_of_people),
                )
                reservation_id = cur.fetchone()[0]
                return {"status": "success", "reservation_id": reservation_id, "date": str(reservation_date), "time": reservation_time.strftime('%H:%M'), "number_of_people": number_of_people}
    except Exception:
        conn.rollback()
        return {"status": "error", "error_code": "RESERVATION_FAILED", "message": "Reservation failed safely."}
    finally:
        conn.close()


def update_stock(product_id: int, quantity: int) -> dict:
    if product_id <= 0:
        return {"status": "error", "error_code": "INVALID_PRODUCT_ID", "message": "product_id must be positive."}
    if quantity < 0 or quantity > 1000:
        return {"status": "error", "error_code": "INVALID_STOCK", "message": "Stock must be between 0 and 1000."}

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE products SET stock = %s WHERE id = %s RETURNING id, name, stock", (quantity, product_id))
                row = cur.fetchone()
                if row is None:
                    return {"status": "error", "error_code": "PRODUCT_NOT_FOUND", "message": "Product not found."}
                return {"status": "success", "product_id": row[0], "product_name": row[1], "new_stock": row[2]}
    except Exception:
        conn.rollback()
        return {"status": "error", "error_code": "STOCK_UPDATE_FAILED", "message": "Stock update failed safely."}
    finally:
        conn.close()
