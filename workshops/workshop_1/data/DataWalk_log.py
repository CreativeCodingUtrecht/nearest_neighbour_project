#!/usr/bin/env python3

import time
import datetime
import csv
import colorsys
import sys
import ST7735


# Setup for GPS module. ------------------------------------------------------
# Will wait for a fix and print a message every second with the current location
# and other details.
import board
import busio
import adafruit_gps
# for a computer, use the pyserial library for uart access
import serial
uart = serial.Serial("/dev/ttyUSB0", baudrate=9600, timeout=10)

# Create a GPS module instance.
gps = adafruit_gps.GPS(uart, debug=False)  # Use UART/pyserial
# gps = adafruit_gps.GPS_GtopI2C(i2c, debug=False)  # Use I2C interface

# Turn on the basic GGA and RMC info (what you typically want)
gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")

# Set update rate to once a second (1hz) which is what you typically want.
gps.send_command(b"PMTK220,1000")

last_print = time.monotonic()

# ----------------------------------------------------------------------------



try:
    # Transitional fix for breaking change in LTR559
    from ltr559 import LTR559
    ltr559 = LTR559()
except ImportError:
    import ltr559

from bme280 import BME280
from pms5003 import PMS5003, ReadTimeoutError as pmsReadTimeoutError
from enviroplus import gas
from subprocess import PIPE, Popen
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from fonts.ttf import RobotoMedium as UserFont
import logging

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("""all-in-one.py - Displays readings from all of Enviro plus' sensors

Press Ctrl+C to exit!

""")

# BME280 temperature/pressure/humidity sensor
bme280 = BME280()

# PMS5003 particulate sensor
pms5003 = PMS5003()

# Create ST7735 LCD display class
st7735 = ST7735.ST7735(
    port=0,
    cs=1,
    dc=9,
    backlight=12,
    rotation=270,
    spi_speed_hz=10000000
)

# Initialize display
st7735.begin()

WIDTH = st7735.width
HEIGHT = st7735.height

# Set up canvas and font
img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
font_size = 20
font = ImageFont.truetype(UserFont, font_size)

message = ""

# The position of the top bar
top_pos = 25


# Displays data and text on the 0.96" LCD
def display_text(variable, data, unit):
    # Maintain length of list
    values[variable] = values[variable][1:] + [data]
    # Scale the values for the variable between 0 and 1
    vmin = min(values[variable])
    vmax = max(values[variable])
    colours = [(v - vmin + 1) / (vmax - vmin + 1) for v in values[variable]]
    # Format the variable name and value
    message = "{}: {:.1f} {}".format(variable[:4], data, unit)
    logging.info(message)
    draw.rectangle((0, 0, WIDTH, HEIGHT), (255, 255, 255))
    for i in range(len(colours)):
        # Convert the values to colours from red to blue
        colour = (1.0 - colours[i]) * 0.6
        r, g, b = [int(x * 255.0) for x in colorsys.hsv_to_rgb(colour, 1.0, 1.0)]
        # Draw a 1-pixel wide rectangle of colour
        draw.rectangle((i, top_pos, i + 1, HEIGHT), (r, g, b))
        # Draw a line graph in black
        line_y = HEIGHT - (top_pos + (colours[i] * (HEIGHT - top_pos))) + top_pos
        draw.rectangle((i, line_y, i + 1, line_y + 1), (0, 0, 0))
    # Write the text at the top in black
    draw.text((0, 0), message, font=font, fill=(0, 0, 0))
    st7735.display(img)


# Get the temperature of the CPU for compensation
def get_cpu_temperature():
    process = Popen(['vcgencmd', 'measure_temp'], stdout=PIPE, universal_newlines=True)
    output, _error = process.communicate()
    return float(output[output.index('=') + 1:output.rindex("'")])


# Tuning factor for compensation. Decrease this number to adjust the
# temperature down, and increase to adjust up
factor = 12.25

cpu_temps = [get_cpu_temperature()] * 5

delay = 0.5  # Debounce the proximity tap
mode = 0     # The starting mode
last_page = 0
light = 1

# Create a values dict to store the data
variables = ["temperature",
             "pressure",
             "humidity",
             "light",
             "oxidised",
             "reduced",
             "nh3",
             "pm1",
             "pm25",
             "pm10"]

values = {}

for v in variables:
    values[v] = [1] * WIDTH

# The main loop
try:
    while True:

        # Enviro+ --------------------------------------------------------------

        proximity = ltr559.get_proximity()

        # variable = "temperature"
        temp_unit = "C"
        cpu_temp = get_cpu_temperature()
        # Smooth out with some averaging to decrease jitter
        cpu_temps = cpu_temps[1:] + [cpu_temp]
        avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
        raw_temp = bme280.get_temperature()
        temp_data = raw_temp - ((avg_cpu_temp - raw_temp) / factor)

        # variable = "pressure"
        hPa_unit = "hPa"
        hPa_data = bme280.get_pressure()

        # variable = "humidity"
        hum_unit = "%"
        hum_data = bme280.get_humidity()

        # variable = "light"
        lux_unit = "Lux"
        if proximity < 10:
            lux_data = ltr559.get_lux()
        else:
            lux_data = 1

        # variable = "oxidised"
        ox_unit = "kO"
        ox_data = gas.read_all()
        ox_data = ox_data.oxidising / 1000

        # variable = "reduced"
        red_unit = "kO"
        red_data = gas.read_all()
        red_data = red_data.reducing / 1000

        # variable = "nh3"
        nh3_unit = "kO"
        nh3_data = gas.read_all()
        nh3_data = nh3_data.nh3 / 1000

          # variable = "pm1"
        pm1_unit = "ug/m3"
        pm1_data = 0
        try:
            pm1_data = pms5003.read()
        except pmsReadTimeoutError:
            logging.warning("Failed to read PMS5003")
        else:
            pm1_data = float(pm1_data.pm_ug_per_m3(1.0))

        # variable = "pm25"
        pm25_unit = "ug/m3"
        pm25_data = 0
        try:
            pm25_data = pms5003.read()
        except pmsReadTimeoutError:
            logging.warning("Failed to read PMS5003")
        else:
            pm25_data = float(pm25_data.pm_ug_per_m3(2.5))

        # variable = "pm10"
        pm10_unit = "ug/m3"
        pm10_data = 0
        try:
            pm10_data = pms5003.read()
        except pmsReadTimeoutError:
            logging.warning("Failed to read PMS5003")
        else:
            pm10_data = float(pm10_data.pm_ug_per_m3(10))



        # If the proximity crosses the threshold, toggle the mode
        if proximity > 1500 and time.time() - last_page > delay:
            mode += 1
            mode %= len(variables)
            last_page = time.time()

        # One mode for each variable
        if mode == 0:
            display_text(variables[mode], temp_data, temp_unit)

        if mode == 1:
            display_text(variables[mode], hPa_data, hPa_unit)

        if mode == 2:
            display_text(variables[mode], hum_data, hum_unit)

        if mode == 3:
            display_text(variables[mode], lux_data, lux_unit)

        if mode == 4:
            display_text(variables[mode], ox_data, ox_unit)

        if mode == 5:
            display_text(variables[mode], red_data, red_unit)

        if mode == 6:
            display_text(variables[mode], nh3_data, nh3_unit)

        if mode == 7:
            # variable = "pm1"
            try:
                pm1_data = pms5003.read()
            except pmsReadTimeoutError:
                logging.warning("Failed to read PMS5003")
            else:
                pm1_data = float(pm1_data.pm_ug_per_m3(1.0))
                display_text(variables[mode], pm1_data, pm1_unit)

        if mode == 8:
            # variable = "pm25"
            try:
                pm25_data = pms5003.read()
            except pmsReadTimeoutError:
                logging.warning("Failed to read PMS5003")
            else:
                pm25_data = float(pm25_data.pm_ug_per_m3(2.5))
                display_text(variables[mode], pm25_data, pm25_unit)

        if mode == 9:
            # variable = "pm10"
            try:
                pm10_data = pms5003.read()
            except pmsReadTimeoutError:
                logging.warning("Failed to read PMS5003")
            else:
                pm10_data = float(pm10_data.pm_ug_per_m3(10))
                display_text(variables[mode], pm10_data, pm10_unit)

        # gps ----------------------------------------------------------

        # Make sure to call gps.update() every loop iteration and at least twice
        # as fast as data comes from the GPS unit (usually every second).
        # This returns a bool that's true if it parsed new data (you can ignore it
        # though if you don't care and instead look at the has_fix property).
        gps.update()
        # Every second print out current location details if there's a fix.
        current = time.monotonic()
        latitudeLog = 0
        longitudeLog = 0
        if current - last_print >= 1.0:
            last_print = current
            if not gps.has_fix:
                # Try again if we don't have a fix yet.
                print("Waiting for fix...")
                continue
            # We have a fix! (gps.has_fix is true)
            latitudeLog = gps.latitude
            longitudeLog = gps.longitude

            # datalog to csv ---------------------------------------------------------------
            ts = time.time()
            timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            logData = [ts, timestamp, latitudeLog, longitudeLog, temp_data, hPa_data, hum_data, lux_data, ox_data, red_data, nh3_data, pm1_data, pm25_data, pm10_data]
            print(logData)
            # Sla gegevens op in een bestand (per maand) in /usr/src/DHT_DATA_[YYYY]_[MM].csv
            DY = time.strftime("%Y")
            DM = time.strftime("%m")

            csvfile = "/home/pi/Desktop/datawalk_3_DATA_" + DY + "_" + DM + ".csv"

            # Open het csv bestand en schijf door achter de bestaande inhoud.
            with open(csvfile, "a") as output:
                writer = csv.writer(output, delimiter=";", lineterminator='\n')
                writer.writerow(logData)


# Exit cleanly
except KeyboardInterrupt:
    sys.exit(0)