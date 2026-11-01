// ESP32-S3-Mini + MFRC522 (I2C) + BLE UID broadcaster
#include <Wire.h>
#include <MFRC522_I2C.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#define SDA_PIN 8
#define SCL_PIN 9
#define BUZZER_PIN 7
#define RFID_ADDRESS 0x28

#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

MFRC522_I2C rfid(RFID_ADDRESS, -1, &Wire);

BLEServer* pServer = NULL;
BLECharacteristic* pCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer*)    { deviceConnected = true;  Serial.println("Device Connected"); }
  void onDisconnect(BLEServer*) { deviceConnected = false; Serial.println("Device Disconnected"); }
};

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  rfid.PCD_Init();

  BLEDevice::init("ESP32-S3-RFID-Reader");
  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService* pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
      CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_READ |
      BLECharacteristic::PROPERTY_NOTIFY |
      BLECharacteristic::PROPERTY_WRITE);
  pCharacteristic->addDescriptor(new BLE2902());

  pService->start();

  BLEAdvertising* pAdv = BLEDevice::getAdvertising();
  pAdv->addServiceUUID(SERVICE_UUID);
  pAdv->setScanResponse(true);
  pAdv->setMinPreferred(0x06);
  pAdv->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
  Serial.println("BLE initialized, waiting for a client...");
}

void loop() {
  if (deviceConnected &&
      rfid.PICC_IsNewCardPresent() &&
      rfid.PICC_ReadCardSerial()) {

    if (rfid.uid.size <= 4) {
      uint32_t reversedUID = 0;
      for (byte i = 0; i < rfid.uid.size; i++)
        reversedUID |= ((uint32_t)rfid.uid.uidByte[i]) << (8 * i);

      String uidString = String(reversedUID);
      Serial.println("Sending UID: " + uidString);
      pCharacteristic->setValue(uidString.c_str());
      pCharacteristic->notify();

      digitalWrite(BUZZER_PIN, HIGH);
      delay(150);
      digitalWrite(BUZZER_PIN, LOW);
    }
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }

  if (!deviceConnected && oldDeviceConnected) {
    delay(500);
    pServer->startAdvertising();
    Serial.println("Re-advertising...");
    oldDeviceConnected = deviceConnected;
  }
  if (deviceConnected && !oldDeviceConnected) {
    oldDeviceConnected = deviceConnected;
  }

  delay(50);
}