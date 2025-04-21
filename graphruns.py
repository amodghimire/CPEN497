import os
import matplotlib.pyplot as plt
from collections import defaultdict
import numpy as np

def parse_log_file(file_path):
    """Parse a log file and return epoch -> test_acc mapping"""
    epoch_data = {}
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith('e '):
                parts = line.split('|')
                epoch = int(parts[0].strip().split()[1])  # Extract epoch
                acc_part = [p for p in parts if 'test acc' in p][0]
                test_acc = float(acc_part.split('test acc')[1].split()[0])
                epoch_data[epoch] = test_acc
    return epoch_data

def process_run_group(base_dir, start_idx, end_idx, epoch_range=(100, 2000)):
    """Process a group of runs (e.g., FRL~try=0 to FRL~try=4) and return averaged test accuracies"""
    all_epoch_data = []
    
    for i in range(start_idx, end_idx + 1):
        dir_path = os.path.join(base_dir, f"FRL~try={i}")
        file_path = os.path.join(dir_path, "output.txt")
        
        if not os.path.exists(file_path):
            print(f"Warning: {file_path} not found. Skipping.")
            continue
        
        try:
            epoch_data = parse_log_file(file_path)
            all_epoch_data.append(epoch_data)
            print(f"Processed {file_path}")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    if not all_epoch_data:
        raise ValueError(f"No valid files in group {start_idx}-{end_idx}")
    
    # Average test accuracies across files in this group
    avg_data = defaultdict(list)
    min_epoch, max_epoch = epoch_range
    
    for epoch_data in all_epoch_data:
        for epoch in range(min_epoch, max_epoch + 1):
            if epoch in epoch_data:
                avg_data[epoch].append(epoch_data[epoch])
    
    # Compute averages for each epoch
    result = {}
    for epoch in sorted(avg_data.keys()):
        result[epoch] = sum(avg_data[epoch]) / len(avg_data[epoch])
    
    return result

def plot_multiple_runs(run_groups, epoch_range=(100, 2000)):
    """Plot test accuracy vs. epoch with clearer dots"""
    plt.figure(figsize=(20, 8))  # Extra-wide figure
    
    # More distinct colors (blue, orange, green, red)
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#000000']
    labels = ['Run 1 (Their Attack)', 'Run 2 (Circular Rotation)', 
              'Run 3 (Modified Inverted Attack)', 'Run 4 (Modified Circular Rotation)']
    stride = 5  # Plot every 5th point
    
    for idx, (start_idx, end_idx) in enumerate(run_groups):
        try:
            epoch_acc_data = process_run_group("Logs", start_idx, end_idx, epoch_range)
            epochs = sorted(epoch_acc_data.keys())
            accuracies = [epoch_acc_data[e] for e in epochs]
            
            # Simple dotted lines with distinct colors
            plt.plot(epochs[::stride], accuracies[::stride], 
                    linestyle=':', linewidth=2,  # Dotted line
                    color=colors[idx], 
                    label=labels[idx],
                    alpha=0.8)
            
        except Exception as e:
            print(f"Error processing group {start_idx}-{end_idx}: {e}")
    
    plt.xlabel('Epoch', fontsize=12)
    plt.ylabel('Test Accuracy', fontsize=12)
    plt.title('Test Accuracy Comparison (Epochs 100-2000)', fontsize=14)
    plt.grid(True, linestyle=':', alpha=0.5)  # Lighter grid
    plt.legend(fontsize=10)
    
    # Custom x-axis ticks for better readability
    plt.xticks(np.arange(100, 2001, 100), rotation=45)  # Every 100 epochs
    
    plt.tight_layout()
    plt.savefig("accuracy_comparison.png")
    plt.show()

# Define the run groups (start_idx, end_idx)
run_groups = [
    (0, 4),    # Run 1: Files 0-4
    (5, 9),    # Run 2: Files 5-9
    (10, 14),  # Run 3: Files 10-14
    (15, 19)   # Run 4: Files 15-19
]

# Generate the plot
plot_multiple_runs(run_groups, epoch_range=(100, 2000))