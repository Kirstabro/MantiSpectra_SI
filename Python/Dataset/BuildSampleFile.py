import serial
import time
import json
import paho.mqtt.client as mqtt
import re
import pandas as pd
from sklearn.cross_decomposition import PLSRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from joblib import dump, load
import numpy as np
import os


# Define the header of the CSV file
header = [f'spectrum_{i+1}' for i in range(16)] + ['alcohol_percentage', 'sugar_percentage']

# Store current darkref values
darkref_numbers = []

def set_darkref():
    global darkref_numbers  # Use the global variable
    
    # Send Command to MantiSpectra
    command = b'S'
    ms_ser.write(command)

    # Read the response
    response = ms_ser.read(320).decode('utf-8')  # Adjust the buffer size as needed
    clean_response = remove_ansi_escape_codes(response)

    # Extract the first 16 numbers and store them in the global variable
    darkref_numbers = [int(num) for num in clean_response.split()[:16]]

    print(f"Response from MantiSpectra: {clean_response}", end='\n')

    # Access and iterate over the extracted numbers
    for num in darkref_numbers:
        print(f"Number: {num}")

# Remove any ansi that comes from the MS sensor side
def remove_ansi_escape_codes(input_string):
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', input_string) 

# Make a new datacapture and correct it with the darkref
def extract_dark_ref():
    global darkref_numbers  # Use the global variable
    
    # Send Command to MantiSpectra
    command = b'S'
    ms_ser.write(command)

    # Read the response
    response = ms_ser.read(320).decode('utf-8')  # Adjust the buffer size as needed
    clean_response = remove_ansi_escape_codes(response)

    # Extract the first 16 numbers and store them in the global variable
    samples = [int(num) for num in clean_response.split()[:16]]

    print(f"Response from MantiSpectra: {clean_response}", end='\n')

    result_numbers = [new_num - extracted_num for new_num, extracted_num in zip(samples, darkref_numbers)]
    return result_numbers

# Method to take a sample
def add_sample_to_csv(alcohol_percentage, sugar_percentage):
    global df

    spectral_values = extract_dark_ref()
    print(f"Spectral values:  {spectral_values}")

    new_sample = list(spectral_values) + [alcohol_percentage, sugar_percentage]

    new_df = pd.DataFrame([new_sample], columns=header)
    
    # Add the new DataFrame to the existing one
    new_df = pd.DataFrame([new_sample], columns=header)
    
    # Check if the CSV file already exists
    file_name = 'dataset.csv'
    if os.path.exists(file_name):
        # Load the existing DataFrame from the CSV file
        df = pd.read_csv(file_name)
        # Add the new DataFrame to the existing one
        df = pd.concat([df, new_df], ignore_index=True, sort=False)  # Explicitly set sort=False
    else:
        # If the CSV file doesn't exist, create a new DataFrame
        df = pd.concat([df, new_df], ignore_index=True, sort=False)  # Explicitly set sort=False

    # Save the updated DataFrame to the CSV file
    df.to_csv(file_name, index=False)

# Initialize an empty DataFrame
df = pd.DataFrame(columns=header)

# User input-based workflow
ms_port = input("Enter the Mantispetra serial port (e.g., COM3, /dev/ttyUSB0): ")

ms_ser = serial.Serial(ms_port, 115200, timeout=5)

# Ask for user input
user_input = input("Enter a command ('Darkref', 'Sample' or 'Next'): ")

if user_input == 'Darkref':
    # Call the method for 'Darkref'
    print("Performing Darkref...")
    set_darkref()

elif user_input == 'Sample':
    # Ask for alcohol and sugar percentages
    alcohol_percentage = float(input("Enter alcohol percentage: "))
    sugar_percentage = float(input("Enter sugar percentage: "))

    # Start taking samples until 'Next' is entered
    while True:
        start_command = input("Enter 'Start' to take a sample or 'Next' to move on: ")

        if start_command == 'Start':
        	# Ask for the amount of samples that should be taken
        	sample_size = input("Enter the sample amount: ")

            # Defined amount of samples are taken and added to the csv file
            for _ in range(sample_size):
                add_sample_to_csv(alcohol_percentage, sugar_percentage)
                print("Sample taken and added to dataset.")
                time.sleep(1)
        elif start_command == 'Next':
            # Break the inner loop to go back to the main loop
            break

        else:
            print("Invalid command. Please enter 'Start' or 'Next'.")

elif user_input == 'Next':
    # Break the main loop to end the program
    print("Ending the program.")

else:
    print("Invalid command. Please enter a valid command.")

