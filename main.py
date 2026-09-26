from agent import build_graph, run_request


def main():
    graph = build_graph()

    print("=" * 60)
    print("||               CAFE SHOP MANAGEMENT AGENT               ||")
    print("=" * 60)
    print("Role: customer or admin")
    print("Type 'exit' to quit.")

    role = input("Role: ").strip().lower()

    if role not in {"customer", "admin"}:
        print("Invalid role. Use customer or admin.")
        return

    conversation_state = None

    while True:
        user_input = input("\nYou: ").strip()

        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        if not user_input:
            continue

        print("\nAgent:")

        response, conversation_state = run_request(
            graph,
            user_input,
            role,
            conversation_state,
        )

        print(response)


if __name__ == "__main__":
    main()