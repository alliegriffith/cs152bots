import json

with open("user_report_tree.json", "r") as f:
    json_tree = json.load(f)

def traverse(node):
    while True:
        if 'warning' in node:
            print(f"\n {node['warning']}")
        
        if 'prompt' in node and node['prompt']:
            print(f"\n{node['prompt']}")
        else:
            print("\n(No prompt available here.)")

        if 'options' in node and node['options']:
            options = list(node['options'].keys())
            for idx, option in enumerate(options):
                print(f"{idx + 1}. {option}")
            
            # Get user input and validate it
            choice = input("Choose an option: ").strip()
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(options):
                    selected = options[choice_idx]
                    node = node['options'][selected]
                else:
                    print("❌ Invalid option. Try again.")
            except ValueError:
                print("❌ Please enter the number of your choice.")
        else:
            user_note = input("Leave any additional comments here: ").strip()
            print(f"Thank you, we have received your comment: {user_note}")
            # If no options, we might be at a final node
            if 'final_note' in node and node['final_note']:
                print(f"\n✅ {node['final_note']}")
            print("\nEnd of this path.")
            break

# Start traversing from the root
traverse(json_tree)