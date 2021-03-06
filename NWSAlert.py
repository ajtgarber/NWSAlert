# pip install pillow, dotenv, discord_webhook

import json
import requests
import time
import datetime
import os
import io
from PIL import Image
from PIL import ImageDraw
from PIL import UnidentifiedImageError

from dotenv import load_dotenv
from discord_webhook import DiscordWebhook, DiscordEmbed

load_dotenv()

WEBHOOK_URL = os.environ['WEBHOOK_URL']
GPS_COORDS = os.environ['GPS_COORDS']
RADAR_SITE = 'kiln'

webhook = DiscordWebhook(WEBHOOK_URL, rate_limit_retry=True)

known_alerts = []

def send_alert(timestamp, title, text, image):
	content = "**" + title + "**\n" + text
	#data = {
	#	"content" : content,
	#	"username" : "WXAlert"
	#}
	
	time.sleep(1)
	embed = DiscordEmbed(title=title, description=text, timestamp=timestamp)
	if image is not None:
		byte_array = io.BytesIO()
		image.save(byte_array, format='PNG')
		
		webhook.add_file(file=byte_array.getvalue(), filename="warn.png")
		embed.set_image(url="attachment://warn.png")
	
	webhook.add_embed(embed)
	response = webhook.execute()

def request_alerts():
	headers = {
		'User-Agent': '(Test Weather Alerting, ajtgarber@gmail.com)'
	}
	time.sleep(1)
	response = None
	
	for counter in range(0, 5):
		response = requests.get("https://api.weather.gov/alerts/active?point="+GPS_COORDS, headers=headers)
		
		if response.status_code != 200:
			print("Received an error from the server, assuming we've hit the rate-limit")
			print(str(response.status_code))
			time.sleep(10)
		else:
			break
	
	if response.status_code != 200:
		print("We have retried 5 times, something's wrong")
		return None

	messages = json.loads(response.text)

	warnings = messages["features"]
	return warnings
	
def generate_warning_image(warning_polygon):
	min_x =  9999
	min_y =  9999
	max_x = -9999
	max_y = -9999
	for point in warning_polygon:
		if point[0] < min_x: min_x = point[0]
		if point[0] > max_x: max_x = point[0]
		if point[1] < min_y: min_y = point[1]
		if point[1] > max_y: max_y = point[1]
	
	old_range_x = abs(max_x - min_x)
	old_range_y = abs(max_y - min_y)
	
	max_length = 2000
	
	if (old_range_x / old_range_y) < (old_range_y / old_range_x):
		new_range_x = round(max_length * (old_range_x / old_range_y))
		new_range_y = max_length
	else:
		new_range_x = max_length
		new_range_y = round(max_length * (old_range_y / old_range_x))
	#new_range_x = round(2000 * (old_range_x/old_range_y))
	#new_range_y = round(2000 * (old_range_y/old_range_x))
	transformed_polygon = []
	for point in warning_polygon:
		new_x = (((point[0] - min_x) * new_range_x) / old_range_x)
		new_y = (((point[1] - min_y) * new_range_y) / old_range_y)
		transformed_polygon.append(new_x)
		transformed_polygon.append(new_range_y - new_y)
	
	bbox = str(round(min_x, 2))+","+str(round(min_y, 2))+","+str(round(max_x, 2))+","+str(round(max_y, 2))
	reflectivity_url = f"https://opengeo.ncep.noaa.gov/geoserver/{RADAR_SITE}/ows?service=wms&version=1.3.0&request=GetMap&format=image/jpeg&LAYERS={RADAR_SITE}_bref_raw&WIDTH={new_range_x}&HEIGHT={new_range_y}&BBOX={bbox}"
	reflectivity_request = requests.get(reflectivity_url)
	print("reflectivity response: " + str(reflectivity_request.status_code))
	print("reflectivity url: " + reflectivity_url)
	if reflectivity_request.status_code >= 500 and reflectivity_request.status_code < 600:
		print("Received an internal server error")
		return None
	reflectivity_bytes = io.BytesIO(reflectivity_request.content)
	try:
		reflectivity = Image.open(reflectivity_bytes)
	except UnidentifiedImageError:
		print("Unable to parse returned reflectivity image")
		return None
	ref2 = reflectivity.copy()
	draw = ImageDraw.Draw(ref2)
	draw.polygon(transformed_polygon, fill="red", outline="red")
	
	velocity_url = f"https://opengeo.ncep.noaa.gov/geoserver/{RADAR_SITE}/ows?service=wms&version=1.3.0&request=GetMap&format=image/jpeg&LAYERS={RADAR_SITE}_bvel_raw&WIDTH={new_range_x}&HEIGHT={new_range_y}&BBOX={bbox}"
	velocity_request = requests.get(velocity_url)
	print("velocity response: " + str(velocity_request.status_code))
	print("velocity url: " + velocity_url)
	if velocity_request.status_code >= 500 and velocity_request.status_code < 600:
		print("Received an internal server error")
		return None
	velocity_bytes = io.BytesIO(velocity_request.content)
	try:
		velocity = Image.open(velocity_bytes)
	except UnidentifiedImageError:
		print("Unable to parse returned velocity image")
		return None
	vel2 = velocity.copy()
	draw = ImageDraw.Draw(vel2)
	draw.polygon(transformed_polygon, fill="red", outline="red")
	
	ref3 = Image.blend(reflectivity, ref2, 0.5)
	vel3 = Image.blend(velocity, vel2, 0.5)
	final = Image.new('RGB', (ref3.width, ref3.height+vel3.height))
	final.paste(ref3, (0, 0))
	final.paste(vel3, (0, ref3.height))
	return final

while True:	
	warnings = request_alerts()
	warning_counter = 0
	if warnings != None:
		print("[" + str(datetime.datetime.now()) + "] NWS is reporting " + str(len(warnings)) + " alerts for your area")
		for message in warnings:
			if message["properties"]["@id"] in known_alerts:
				print("We already know about alert ID: " + message["properties"]["@id"])
				continue
			
			print("------")
			print(message["properties"]["@id"])
			print(message["properties"]["headline"])
			print("MessageType " + message["properties"]["messageType"])
			print("Issued " + message["properties"]["effective"])
			print("Ends " + str(message["properties"]["ends"]))
			
			known_alerts.append(message["properties"]["@id"])
			
			description = message["properties"]["description"]
			
			initial_description = ""
			hazard_line = ""
			source_line = ""
			impact_line = ""
			
			if "HAZARD" in description:
				initial_description = description[ : description.index("HAZARD")].replace("\n", " ").strip()
				hazard_line = description[description.index("HAZARD") : description.index("SOURCE")].strip()
				source_line = description[description.index("SOURCE") : description.index("IMPACT")].strip()
				impact_line = description[description.index("IMPACT") : description.index("Locations impacted")].replace("\n", " ").strip()
			
			print("Initial: " + initial_description)
			print("Hazard: " + hazard_line)
			print("Source: " + source_line)
			print("Impact: " + impact_line)
			
			warning_polygon = None
			warning_image = None
			if "geometry" in message and message["geometry"] is not None:
				warning_polygon = message["geometry"]["coordinates"][0]
				warning_image = generate_warning_image(warning_polygon)
				#if warning_image is not None:
					#warning_image.show()
					#warning_counter += 1
					#warning_image.save(f"result{warning_counter}.png", format="png")
			
			print("------")
			print()
			body = "" + initial_description + "\n\n" + hazard_line + "\n" + source_line + "\n" + impact_line
			send_alert(message["properties"]["effective"], message["properties"]["headline"], body, warning_image)
	else:
		print("We were unable to successfully request information from the server")
		break
	time.sleep(45)
