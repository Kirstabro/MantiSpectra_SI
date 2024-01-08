import serial
import time
import paho.mqtt.client as mqtt
import re
import pandas as pd
from sklearn.cross_decomposition import PLSRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
from joblib import dump, load
import numpy as np
import os

# MQTT Broker Settings
broker_address = "test.mosquitto.org"
broker_port = 1883
mqtt_topic = "mantispectra"
mqtt_topic_interval = "mantispectra/interval"
mqtt_topic_log = "mantispectra/log"

interval = 30000  # Standard interval of 30sec

# Return the current interval to the Arduino
def request_interval(arduino_ser):
    global interval
    #Write interval to Arduino
    new_interval = str(interval).encode('utf-8')
    arduino_ser.write(new_interval) 

# Communicatie with sensor to get datacapture
def communicate_with_mantispectra(ms_ser, arduino_ser):
# Send Command to MantiSpectra
    command = b'S'
    ms_ser.write(command)

# Read the response
    response = ms_ser.read(320).decode('utf-8')  # Adjust the buffer size as needed
    clean_response = remove_ansi_escape_codes(response)
    #print(f"Response from MantiSpectra: {clean_response}", end='\n')
    
# Encode the string before writing to Arduino
    encoded_response = clean_response.encode('utf-8')
    arduino_ser.write(encoded_response)
    print("Writing data to Arduino \n")

    time.sleep(2)
# On connect method for MQTT
def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker with result code {rc}")

# On publish method for MQTT
def on_publish(client, userdata, mid):
    print(f"Message published with ID: {mid}")

# On message method for MQTT
def on_message_interval(client, userdata, msg):
    global interval
    try:
        # Set the global interval variable to the new interval
        new_interval = int(msg.payload.decode())
        interval = new_interval
        print(f"Interval updated to: {interval}")   
    except ValueError:
        print("Invalid interval value received")   

# Remove any ansi that comes from the MS sensor side
def remove_ansi_escape_codes(input_string):
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', input_string) 

# Function to train the model and save it to a file
def train_and_save_model(dataset_path='mantispectra_dataset.csv', model_path='pls_model.joblib'):
    # Load data from CSV file
    df = pd.read_csv(dataset_path)

    # Extract features (X) and target variables (y)
    X = df.iloc[:, :-2].values  # Exclude the last two columns (target variables)
    y = df.iloc[:, -2:].values  # Include only the last two columns (target variables)

    # Split the data into training and testing sets
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)

    # Create PLS model
    pls = PLSRegression(n_components=2)

    # Train the model
    pls.fit(X_train, y_train)

    # Save the trained model to a file
    dump(pls, model_path)

# Function to load the pre-trained model and make predictions
def predict_with_model(new_data_snippet, model_path='pls_model.joblib'):
    # Load the pre-trained model
    loaded_model = load(model_path)

    # Make predictions using the pre-trained model
    predicted_values = loaded_model.predict(new_data_snippet)

    # Return the predicted values
    return predicted_values[0, 0], predicted_values[0, 1]

def serial_terminal(ms_port, arduino_port, ms_baudrate=115200, arduino_baudrate=9600):
    # Create MQTT client
    mqtt_client = mqtt.Client("PythonPublisher")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_publish = on_publish
    mqtt_client.on_message = on_message_interval
    
    # Connect to the MQTT broker
    mqtt_client.connect(broker_address, broker_port)
    mqtt_client.subscribe(mqtt_topic_interval)
    mqtt_client.loop_start()
    mqtt_client.publish(mqtt_topic, "Laptop has been connected to MQTT!")

    # Open the input serial connection
    ms_ser = serial.Serial(ms_port, ms_baudrate, timeout=5)

    # Open the output serial connection
    arduino_ser = serial.Serial(arduino_port, arduino_baudrate, timeout=5)

    # Train the model only if it hasn't been trained before
    if not os.path.exists('pls_model.joblib'):
        train_and_save_model()

    try:
        while True:
            # Listen for a command or log from Arduino
            data_from_arduino = arduino_ser.readline().strip()

            try:
                data_from_arduino = data_from_arduino.decode('utf-8')
            except UnicodeDecodeError:
                # Handle non-UTF-8 data
                print("Non-UTF-8 data received from Arduino")
                continue

            # Arduino sends JSON for publishment to MQTT broker
            if "Arduino Uno" in data_from_arduino:
                print("Jsond data recieved: ")
                mqtt_client.publish(mqtt_topic, data_from_arduino)

            # If the data was not JSON, handle other cases (e.g., commands or log messages)
            elif data_from_arduino == "C":
                print("Communicating with mantispectra..")
                communicate_with_mantispectra(ms_ser, arduino_ser)

            # With command "I" the Arduino requests the current interval
            elif data_from_arduino == "I":
                print("Sending current interval to arduino")
                request_interval(arduino_ser)

            # Arduino requests Machine Learning
            elif "Machine_Learning" in data_from_arduino:
                _, data_part = data_from_arduino.split("Machine_Learning", 1)

                new_data_snippet = np.array([list(map(int, data_part.split(',')))])
                
                # Make predictions using the pre-trained modell
                alcohol_percentage, sugar_percentage = predict_with_model(new_data_snippet)

                # Write the predicted values back to Arduino
                arduino_ser.write(f"{alcohol_percentage},{sugar_percentage}\n".encode('utf-8'))
                print(f"{alcohol_percentage},{sugar_percentage}\n".encode('utf-8'))

            else:
                # This is a log message
                if data_from_arduino != "":
                    print("Log/ Arduino:", data_from_arduino)
                    mqtt_client.publish(mqtt_topic_log, data_from_arduino)

            time.sleep(3)

    except KeyboardInterrupt:
        pass
    finally:
        # Close the serial connections
        ms_ser.close()
        arduino_ser.close()
        mqtt_client.disconnect()
        mqtt_client.loop_stop()

if __name__ == "__main__":
    ms_port = input("Enter the Mantispetra serial port (e.g., COM3, /dev/ttyUSB0): ")
    # ms_baudrate = int(input("Enter the Mantispectra baud rate (default is 115200): ") or 115200)

    arduino_port = input("Enter the Arduino serial port (e.g., COM4, /dev/ttyUSB1): ")
    # arduino_baudrate = int(input("Enter the Arduino baud rate (default is 9600): ") or 9600)

    # start the serial communcations and run the main
    serial_terminal(ms_port, arduino_port)