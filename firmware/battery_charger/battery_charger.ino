/*
 * Intelligent Helmet - LiPo battery charger configuration
 * Board: Arduino MKR WAN 1310 (BQ24195 PMIC)
 *
 * Configures the on-board power management IC to charge a single-cell
 * LiPo battery at 150 mA and reports the charging state on the serial port.
 */

#include <Arduino_PMIC.h>

// Charger state
int chargeStatus = NOT_CHARGING;
bool canRunOnBattery = false;

void setup()
{
    Serial.begin(115200);
    while (!Serial);  // wait for the serial monitor

    // Initialise the power management IC
    if (!PMIC.begin()) {
        Serial.println("Critical error: PMIC initialisation failed");
        while (1);  // stop if the hardware does not respond
    }

    PMIC.disableCharge();
    PMIC.setInputCurrentLimit(0.5);      // input current limit (A)
    PMIC.setInputVoltageLimit(3.88);     // input voltage limit (V)
    PMIC.setMinimumSystemVoltage(3.6);   // minimum system voltage (V)
    PMIC.setChargeVoltage(4.2);          // LiPo charge voltage (V)
    PMIC.setChargeCurrent(0.150);        // charge current (A), 150 mA
    PMIC.enableCharge();

    Serial.println("Charge initialized");
}

void loop()
{
    // Report when the system becomes able to run on battery
    if ((!canRunOnBattery) && (PMIC.canRunOnBattery())) {
        canRunOnBattery = true;
        Serial.println("System can now run on battery");
    }

    // Report charging state transitions
    if (chargeStatus != PMIC.chargeStatus()) {
        chargeStatus = PMIC.chargeStatus();
        switch (chargeStatus) {
            case NOT_CHARGING:
                Serial.println("Charger is not charging the battery");
                break;

            case PRE_CHARGING:
                Serial.println("Charger is pre-charging the battery");
                break;

            case FAST_CHARGING:
                Serial.println("Charger is fast-charging the battery");
                break;

            case CHARGE_TERMINATION_DONE:
                Serial.println("Battery is fully charged. Disabling charger!");
                PMIC.disableCharge();
                break;
        }
    }
    delay(1000);
}
