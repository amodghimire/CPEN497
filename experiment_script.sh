#!/bin/bash

RUNS=20

echo "Starting experiment..."

for ((i=1; i<=$RUNS; i++)); do
    echo "Running experiment $i..."
    
    Determine the attack type based on the run number
    if (( i <= 5 )); then
        ATTACK_TYPE="torch_sort"
    elif (( i <= 10 )); then
        ATTACK_TYPE="circular_rotation"
    elif (( i <= 15 )); then
        ATTACK_TYPE="reverse_firsthalf_rotation"
    else
        ATTACK_TYPE="reverse_first_secondhalf_rotation"
    fi
    
    # Run the Python script with the specified attack type
    python main.py --data_loc "./data/MNIST/" --config experiments/006_config_MNIST_LeNet_FRL_1000users_noniid1.0_20pmal.txt --attack_type $ATTACK_TYPE
    
    # Check if the Python script completed successfully
    if [[ $? -ne 0 ]]; then
        echo "Error: Experiment $i failed. Exiting."
        exit 1
    fi
    
    echo "Experiment $i completed with attack type: $ATTACK_TYPE"
done

echo "Experiment completed."