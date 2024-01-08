#include <ArduinoJson.h>
#include <EEPROM.h>
#include "GravityTDS.h"
#include "DFRobot_PH.h"
#include <Wire.h>
#include <Adafruit_MAX31865.h>

#pragma region Sensor Variables
// Pin defines
#define Tds_pin A2
#define PH_pin A3
#define Lamp_shutter_pin 6
#define Lamp_disable_pin 8
#define Lamp_HP_pin 9

#define RNOMINAL 100  // Nominal resistance of the PT100 sensor in ohms
#define RREF 430.0    // Reference resistance of the reference resistor in the amplifier circuit in ohms

Adafruit_MAX31865 max31865 = Adafruit_MAX31865(10, 11, 12, 13);

GravityTDS gravityTds;
DFRobot_PH ph;
float voltage, phValue, tdsValue, temperature = 25;
float tdsFactor = 0.5;

//Variables for EC
float aRef = 5.0;
float adcRange = 1023;

#pragma endregion Sensor Variable

#pragma region MantiSpectra

long incomingByte;
long darkRef[16]; // Stores the DarkRef data
long capture[16]; // Stores the captured data
long corrected[16]; // Stores the captured data - darkref

int counter;
String JSON;

float sugar;
float alcohol;

#pragma endregion

//set interval for sending messages (milliseconds)
long interval = 30000; // Standard set to 30sec interval
unsigned long previousMillis = 0;

void setup() {
  Serial.begin(9600);

  Serial.setTimeout(5000);

  pinMode(PH_pin, INPUT);
  pinMode(Tds_pin, INPUT);
  pinMode(Lamp_disable_pin, OUTPUT);
  pinMode(Lamp_shutter_pin, OUTPUT);
  pinMode(Lamp_HP_pin, OUTPUT);
  
  turnOnLamp();
  digitalWrite(Lamp_shutter_pin, HIGH);

  gravityTds.setPin(Tds_pin);
  gravityTds.setAref(5.0);       //reference voltage on ADC, default 5.0V on Arduino UNO
  gravityTds.setAdcRange(1024);  //1024 for 10bit ADC

  gravityTds.begin();  //initialization

  max31865.begin(MAX31865_2WIRE);

  ph.begin();

  while (!Serial) {
  }

  Serial.println("Setup Complete!");
}

void loop() {

  unsigned long currentMillis = millis();

  // Capture every X second (based on interval)
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;

    Serial.println("Start of loop!");
    JSON = "";

    // Get all pheripheral sensor data
    temperature = readTemperature();
    phValue = readPH(temperature);
    tdsValue = readEC(temperature);

    turnOffLamp();

    // Capture MantiSpectra data and put it all in one data array
    captureMS();

    // Predict sugar and alcohol
    predictMS();

    // Build and send Json of temp, PH, EC, MS
    buildAndSendJson();

    // Request the interval
    requestInterval();
  }
}

void requestInterval() {
  // Print command "I" and wait for reply
  Serial.println("I");
  while (Serial.available() == 0) {
  }

  // Read the interval value
  long newInterval = Serial.parseInt();
  interval = newInterval;
}

#pragma region Pheripheral Sensors
float readTemperature() {

  float temperature = max31865.temperature(RNOMINAL, RREF);
  float newtemperature = (temperature * 0.94);   // Small correction due to ohm value

  return newtemperature;
}

float readPH(float temperature) {
  voltage = analogRead(PH_pin) / 1024.0 * 5000;  // read the voltage
  phValue = ph.readPH(voltage, temperature);     // convert voltage to pH with temperature compensation

  return phValue;
}

float readEC(float temperature) {
  gravityTds.setTemperature(temperature);  // set the temperature and execute temperature compensation
  gravityTds.update();                     // sample and calculate
  tdsValue = gravityTds.getTdsValue();     // get the value

  return tdsValue;
}

#pragma endregion

#pragma region MantiSpectra

void predictMS() {
  String dataSnippet = arrayToString(corrected,16);
  dataSnippet = "Machine_Learning" + dataSnippet; // Add "Machine_Learning" so script recognizes the command

  Serial.println(dataSnippet);

  // Wait for reply with the predicted values
  while (Serial.available() == 0) { 
  }

  String receivedData = Serial.readStringUntil('\n');
  receivedData.trim();  // Remove any whitespace etc.

  int commaIndex = receivedData.indexOf(',');

  if (commaIndex != -1) {
    // Extract the substring before the comma
    String alcoholString = receivedData.substring(0, commaIndex);
    // Extract the substring after the comma
    String sugarString = receivedData.substring(commaIndex + 1);

    // Convert the substring to floats
    alcohol = alcoholString.toFloat();
    sugar = sugarString.toFloat();

    } else {

    Serial.println("Error parsing alcohol, sugar data!");
  }
}

void captureMS() {
  // Send command to python to make MS capture and store in DarkRef array
  capturePython(darkRef);

  // Turn on lamp
  turnOnLamp();
  delay(2000);

  // Send command to python to make MS capture and store in Capture array
  capturePython(capture);

  // Turn off lamp
  turnOffLamp();

  // Correct data; capture - darkref
  MSCorrectRef();
  Serial.print("After MS Correctref: ");
  Serial.println(arrayToString(corrected, 16));
}


void capturePython(long array[]) {

  // Send "C" command and wait for reply
  Serial.println("C");

  while (Serial.available() == 0) {
  }

  counter = 0;

  while (Serial.available() > 0) {
    // Store incoming data in array
    incomingByte = Serial.parseInt(SKIP_ALL);

    if (incomingByte != 0 && counter < 16) {
      array[counter] = incomingByte;
      counter++;
    }
  }
}

// Simple method to convert array to comma seperated string
String arrayToString(long arr[], int size) {
  String result = "";
  for (int i = 0; i < size; i++) {
    result += String(arr[i]);
    if (i < size - 1) {
      result += ",";
    }
  }
  return result;
}

void turnOnLamp() {
  //Lamp on
  digitalWrite(Lamp_disable_pin, LOW);
}

void turnOffLamp() {
  //Lamp off
  digitalWrite(Lamp_disable_pin, HIGH);
}

// Correct the measurement by subtracting the darkref from the measurement
void MSCorrectRef() {
  int i;
  for (i = 0; i < 16; i++) {
    long correct = capture[i] - darkRef[i];
    corrected[i] = correct;
  }
}
#pragma endregion

#pragma region JSON
void buildAndSendJson() {
  StaticJsonDocument<400> doc;

  // Round values to 2 decimals and add to doc 
  doc["Alcohol"] = round(alcohol * 100.0) / 100.0;
  doc["Sugar"] = round(sugar * 100.0) / 100.0;
  doc["temperature"] = round(temperature * 100.0) / 100.0;
  doc["PH"] = round(phValue * 100.0) / 100.0;
  doc["EC"] = round(tdsValue * 100.0) / 100.0;
  doc["sensor"] = "Arduino Uno";

  //Serialize the doc into JSON string and print
  serializeJson(doc, JSON);
  Serial.println(JSON);
}
#pragma endregion
