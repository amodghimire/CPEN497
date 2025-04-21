import os
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict

def parse_log_file(file_path):
    """Parse a log file and return dict[malicious_users] -> [accuracies]"""
    mal_acc_dict = defaultdict(list)
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith('e '):
                parts = line.split('|')
                # Extract number of malicious users
                mal_part = [p for p in parts if 'malicious users' in p][0]
                mal_users = int(mal_part.split(':')[1].strip())
                # Extract test accuracy
                acc_part = [p for p in parts if 'test acc' in p][0]
                test_acc = float(acc_part.split('test acc')[1].split()[0])
                
                if mal_users <= 12:  # Only consider up to 12 malicious users
                    mal_acc_dict[mal_users].append(test_acc)
    return mal_acc_dict

def process_run_group(base_dir, start_idx, end_idx):
    """Process a group of runs and return combined malicious user accuracy data"""
    combined_data = defaultdict(list)
    
    for i in range(start_idx, end_idx + 1):
        dir_path = os.path.join(base_dir, f"FRL~try={i}")
        file_path = os.path.join(dir_path, "output.txt")
        
        if os.path.exists(file_path):
            try:
                file_data = parse_log_file(file_path)
                for mal_users, acc_list in file_data.items():
                    combined_data[mal_users].extend(acc_list)
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
    
    print(f"\nRun Group {start_idx}-{end_idx} Statistics:")
    print(f"Total malicious user counts: {len(combined_data)}")
    print("Details (users → num_accuracy_values):")
    for mal_users in sorted(combined_data.keys()):
        print(f"{mal_users} users → {len(combined_data[mal_users])} accuracy values")
    return combined_data

def plot_malicious_users_boxplot(run_groups):
    """Create boxplots of accuracy vs malicious users for each run group"""
    plt.figure(figsize=(16, 8))  # Slightly wider to accommodate extra group
    
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']  # Added red color for new group
    labels = ['Run 1 (Their Attack)', 'Run 2 (Circular Rotation)', 
             'Run 3 (Modified Inverted Attack)', 'Run 4 (Modified Circular Rotation)']
    
    # Prepare data for plotting
    all_data = []
    positions = []
    xtick_labels = []
    
    for group_idx, (start_idx, end_idx) in enumerate(run_groups):
        group_data = process_run_group("Logs", start_idx, end_idx)
        
        # Sort by number of malicious users
        sorted_mal_users = sorted(group_data.keys())
        acc_lists = [group_data[mal] for mal in sorted_mal_users]
        
        # Store data for plotting
        all_data.append(acc_lists)
        if group_idx == 0:  # Only need labels once
            xtick_labels = [f"{mal} users" for mal in sorted_mal_users]
            positions = np.arange(len(sorted_mal_users))
    
    # Create boxplots
    width = 0.2  # Reduced width to fit all groups
    for i, acc_lists in enumerate(all_data):
        # Offset positions for each run group
        offset_positions = positions + i * width
        box = plt.boxplot(acc_lists, 
                         positions=offset_positions,
                         widths=width,
                         patch_artist=True,
                         showfliers=False)  # Hide outliers for clarity
        
        # Color the boxes
        for patch in box['boxes']:
            patch.set_facecolor(colors[i])
            patch.set_alpha(0.6)
        
        # Add median line
        for median in box['medians']:
            median.set(color='black', linewidth=1.5)
    
    # Formatting
    plt.xlabel('Number of Malicious Users', fontsize=12)
    plt.ylabel('Test Accuracy', fontsize=12)
    plt.title('Accuracy Distribution vs Malicious Users', fontsize=14, pad=20)
    
    # Set x-axis ticks and labels
    plt.xticks(positions + width * 1.5, xtick_labels, rotation=45)
    plt.grid(True, linestyle=':', alpha=0.3)
    
    # Create custom legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=colors[i], label=labels[i]) 
                      for i in range(len(run_groups))]
    plt.legend(handles=legend_elements, fontsize=10)
    
    plt.tight_layout()
    plt.savefig("boxplots.png")
    plt.show()

# Define run groups and plot
run_groups = [(0, 4), (5, 9), (10, 14), (15, 19)]  # Added new run group
plot_malicious_users_boxplot(run_groups)