import re
from collections import defaultdict

def analyze_log_file(filename):
    embed_creations = defaultdict(list)
    current_operation = None
    
    with open(filename, 'r') as f:
        for line in f:
            # Track operations
            if "Updating players for SNG" in line:
                current_operation = f"update_{line.split('SNG')[1].strip()}"
            elif "Starting refresh cycle for game" in line:
                current_operation = f"refresh_{line.split('game')[1].strip()}"
            
            # Track embed creations
            if "Created embed for game" in line:
                if current_operation:
                    embed_creations[current_operation].append(line)
            
            # End of operation
            if "Temporary 'Updating SNG status...' message deleted" in line:
                current_operation = None
    
    # Report multiple embed creations
    for operation, creations in embed_creations.items():
        if len(creations) > 1:
            print(f"\nMultiple embeds created during {operation}:")
            for creation in creations:
                print(creation.strip())

if __name__ == "__main__":
    analyze_log_file("bot.log") 