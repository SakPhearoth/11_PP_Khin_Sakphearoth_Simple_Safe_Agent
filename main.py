from agent import build_graph, run_request


def main():
    graph = build_graph()

    print("=" * 60)
    print("CAFE SHOP MANAGEMENT AGENT")
    print("=" * 60)
    print("Role: customer or admin")
    print("Type 'exit' to quit.")

    role = input("Role: ").strip().lower()
    if role not in {"customer", "admin"}:
        print("Invalid role. Use customer or admin.")
        return

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if not user_input:
            continue

        print("\nAgent:")
        print(run_request(graph, user_input, role))


if __name__ == "__main__":
    main()
