from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageDraw, ImageFont
import time

# Setup I2C interface
serial = i2c(port=1, address=0x3C)
device = ssd1306(serial)

# Create blank image
image = Image.new("1", device.size)
draw = ImageDraw.Draw(image)

# Use a bold font with good clarity
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)

# Clear screen
draw.rectangle((0, 0, device.width, device.height), outline=0, fill=0)

# Centered text
text = "Welcome!"
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
x = (device.width - text_width) // 2
y = (device.height - text_height) // 2
draw.text((x, y), text, font=font, fill=255)

# Show it
device.display(image)
time.sleep(5)
